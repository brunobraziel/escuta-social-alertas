"""Single-consumer Pub/Sub -> durable SQLite outbox -> local WAHA."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time



def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
        event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
        next_part INTEGER NOT NULL DEFAULT 0, receipts TEXT NOT NULL DEFAULT '[]',
        created REAL NOT NULL, updated REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS accessible_reports (
        event_id TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS report_messages (
        message_id TEXT PRIMARY KEY, event_id TEXT NOT NULL)""")
    # A crash during an HTTP request can mean it was accepted remotely.
    with db:
        db.execute("UPDATE deliveries SET status='uncertain' WHERE status='sending'")
    return db


def parts(text, limit=3500):
    result = []
    while len(text) > limit:
        split = text.rfind("\n\n", 0, limit)
        if split < limit // 2:
            split = text.rfind("\n", 0, limit)
        if split < limit // 2:
            split = limit
        result.append(text[:split])
        text = text[split:].lstrip("\n")
    if text:
        result.append(text)
    return result


def allowed_event(event):
    if event.get("source") == "brunobraziel/escuta-social-etl":
        return (event.get("kind") == "serpapi_last_token"
                and os.getenv("ALLOW_ETL_LAST_TOKEN", "false").lower() == "true")
    return event.get("source") in os.environ["ALLOWED_SOURCES"].split(",")


def accept(db, event):
    if (event.get("version") != 1 or
        not re.fullmatch(r"[a-f0-9]{64}", event.get("event_id", "")) or
        not allowed_event(event) or
        not isinstance(event.get("text"), str) or not 0 < len(event["text"]) <= 30000):
        raise ValueError("Invalid event")
    if 'destination' in event or event.get('presentation') not in (None, 'states', 'related'):
        raise ValueError('Invalid destination or presentation')
    if event.get('presentation') and event.get('source') != 'brunobraziel/escuta-social-alertas':
        raise ValueError('Media restricted to alert catalog')
    now = time.time()
    with db:
        db.execute("INSERT OR IGNORE INTO deliveries(event_id,payload,status,created,updated) VALUES (?,?,'pending',?,?)",
                   (event["event_id"], json.dumps(event), now, now))


def message_receipt(data, group):
    # NOWEB sendText returns the raw Baileys message with key.id, whereas
    # other engines expose the normalized top-level id.
    if not isinstance(data, dict):
        raise ValueError("Invalid WhatsApp response")
    receipt = data.get("id")
    if isinstance(receipt, str) and receipt:
        return receipt
    key = data.get("key")
    if (isinstance(key, dict) and key.get("fromMe") is True
            and key.get("remoteJid") == group
            and isinstance(key.get("id"), str) and key["id"]):
        return key["id"]
    raise ValueError("Missing WhatsApp receipt")


def send_one(db, session, waha, group, api_key):
    row = db.execute("SELECT event_id,payload,next_part,receipts FROM deliveries WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
    if not row:
        return False
    event_id, raw, index, receipts_raw = row
    event = json.loads(raw)
    if not allowed_event(event):
        with db:
            db.execute("UPDATE deliveries SET status='cancelled',updated=? WHERE event_id=?",
                       (time.time(), event_id))
        logging.info("WhatsApp evento cancelado por mudança de origem autorizada event=%s", event_id)
        return True
    destination = event.get('destination', group)
    if destination != group and not re.fullmatch(r'[0-9]{5,20}@(c\.us|s\.whatsapp\.net|lid)', destination):
        raise ValueError('Invalid private destination')
    image_chunks = None
    caption = None
    if event.get('presentation'):
        from cards import render_images
        image_chunks, header = render_images(event['presentation'], event['text'])
        with db:
            db.execute('INSERT OR IGNORE INTO accessible_reports VALUES (?,?,?)',
                       (event_id, event['text'], time.time()))
        # Keep summary through IA, without repeating rankings in the group.
        instruction = '\n\n♿ Reaja a esta imagem com ♿ para receber o texto completo no privado.'
        caption = header + instruction
        if len(caption) > 2000:
            raise ValueError('Caption exceeds readable limit')
    chunks = image_chunks if image_chunks is not None else parts(event["text"])
    receipts = json.loads(receipts_raw)
    # Check before changing delivery state; offline sessions leave messages pending.
    health = session.get(waha + "/api/sessions/default", headers={"X-Api-Key": api_key}, timeout=10)
    health.raise_for_status()
    if health.json().get("status") != "WORKING":
        return False
    with db:
        db.execute("UPDATE deliveries SET status='sending',updated=? WHERE event_id=?", (time.time(), event_id))
    try:
        if image_chunks is not None:
            body = {'session': 'default', 'chatId': destination,
                    'file': {'mimetype': 'image/jpeg', 'filename': event['presentation']+'.jpg',
                             'data': base64.b64encode(chunks[index]).decode()},
                    'caption': caption, 'convert': False}
            endpoint = '/api/sendImage'
        else:
            body = {'session': 'default', 'chatId': destination,
                    'text': chunks[index], 'linkPreview': False}
            endpoint = '/api/sendText'
        response = session.post(waha + endpoint, headers={"X-Api-Key": api_key},
                                json=body, timeout=60)
        response.raise_for_status()
        receipt = message_receipt(response.json(), destination)
    except Exception as exc:
        # Never blindly replay an ambiguous send. Reconciliation is manual.
        with db:
            db.execute("UPDATE deliveries SET status='uncertain',updated=? WHERE event_id=?", (time.time(), event_id))
        logging.error("WhatsApp entrega incerta event=%s erro=%s", event_id, type(exc).__name__)
        return False
    receipts.append(receipt)
    index += 1
    with db:
        if image_chunks is not None:
            for message_id in {receipt, message_key(receipt)}:
                db.execute('INSERT OR IGNORE INTO report_messages VALUES (?,?)', (message_id, event_id))
        db.execute("UPDATE deliveries SET status=?,next_part=?,receipts=?,updated=? WHERE event_id=?",
                   ("sent" if index == len(chunks) else "pending", index,
                    json.dumps(receipts), time.time(), event_id))
    logging.info("WhatsApp confirmação event=%s parte=%d/%d", event_id, index, len(chunks))
    return True


def message_key(message_id):
    # WAHA normalized ID: fromMe_chatId_engineMessageId[_participant].
    fields = str(message_id).split('_')
    return fields[2] if len(fields) >= 3 and fields[0] in ('true', 'false') else str(message_id)


def accept_reaction(db, event, group):
    """A reaction is explicit opt-in; target must be one of our actual images."""
    if event.get('event') != 'message.reaction' or event.get('session') != 'default':
        return False
    payload = event.get('payload') or {}
    reaction = payload.get('reaction') or {}
    if payload.get('fromMe') is not False or payload.get('from') != group or reaction.get('text', '').replace('\ufe0f','') != '♿':
        return False
    recipient = payload.get('participant')
    if not isinstance(recipient, str) or not re.fullmatch(r'[0-9]{5,20}@(c\.us|s\.whatsapp\.net|lid)', recipient):
        return False
    target = reaction.get('messageId', '')
    if not isinstance(target, str): return False
    row = db.execute('SELECT r.event_id,r.text FROM report_messages m JOIN accessible_reports r ON r.event_id=m.event_id WHERE m.message_id IN (?,?) LIMIT 1',
                     (target, message_key(target))).fetchone()
    if not row: return False
    report_id, full = row
    # One reply per image report and participant, even if webhook is redelivered.
    event_id = hashlib.sha256(('accessible:'+report_id+':'+recipient).encode()).hexdigest()
    reply = {'version':1, 'event_id':event_id, 'source':'brunobraziel/escuta-social-alertas',
             'kind':'accessible_reply', 'destination':recipient, 'text':full}
    now = time.time()
    with db:
        db.execute("INSERT OR IGNORE INTO deliveries(event_id,payload,status,created,updated) VALUES (?,?,'pending',?,?)",
                   (event_id,json.dumps(reply,ensure_ascii=False),now,now))
    return True


def start_reaction_server(db_path, group_file, key):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # Never log payloads or participant IDs.
        def do_POST(self):
            if self.path != '/reactions':
                self.send_error(404); return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 262144:
                self.send_error(413); return
            body = self.rfile.read(length)
            signature = hmac.new(key.encode(), body, hashlib.sha512).hexdigest()
            if not hmac.compare_digest(signature, self.headers.get('X-Webhook-Hmac', '')):
                self.send_error(403); return
            try:
                event = json.loads(body)
                if not isinstance(event, dict): raise ValueError('Invalid event')
                with sqlite3.connect(db_path, timeout=15) as incoming:
                    accept_reaction(incoming, event, group_file.read_text().strip())
            except (ValueError, TypeError, AttributeError):
                self.send_error(400); return
            except Exception:
                self.send_error(503); return  # WAHA retries; nothing sensitive in logs.
            self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
    server = ThreadingHTTPServer(('0.0.0.0',8080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def secret(name):
    # Mounted files avoid keys in container configuration and process arguments.
    return Path("/run/secrets/" + name).read_text().strip()


def notify_health(text):
    topic = os.getenv("HEALTH_TOPIC")
    if not topic:
        logging.warning("WhatsApp saúde: %s", text)
        return
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/pubsub"])
        event = {"content": text, "created_at": datetime.now(timezone.utc).isoformat()}
        encoded = base64.b64encode(json.dumps(event, ensure_ascii=False).encode()).decode()
        response = AuthorizedSession(credentials).post(
            "https://pubsub.googleapis.com/v1/" + topic + ":publish",
            json={"messages": [{"data": encoded}]}, timeout=20)
        response.raise_for_status()
    except Exception:
        logging.error("Falha ao publicar aviso de saúde")


def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    import requests
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    group_file = Path("/config/group_id")
    db_path = "/data/deliveries.sqlite"
    db = connect(db_path)
    if os.getenv('ACCESSIBLE_REACTIONS', 'false').lower() == 'true':
        start_reaction_server(db_path, group_file, secret('reaction_hmac_key'))
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/pubsub"])
    pubsub = AuthorizedSession(credentials)
    http = requests.Session()
    api_key = secret("waha_api_key")
    subscription = os.environ["PUBSUB_SUBSCRIPTION"]
    endpoint = "https://pubsub.googleapis.com/v1/" + subscription
    waha = "http://waha:3000"
    cutoff = datetime.fromisoformat(os.environ["STOP_AT"])
    last_health, previous_health, failures = 0, None, 0
    while datetime.now(timezone.utc) < cutoff:
        try:
            # Commit locally BEFORE ack: a lost ack is deduplicated by primary key.
            response = pubsub.post(endpoint + ":pull", json={"maxMessages": 10}, timeout=90)
            response.raise_for_status()
            for item in response.json().get("receivedMessages", []):
                try:
                    event = json.loads(base64.b64decode(item["message"]["data"]))
                    accept(db, event)
                except (ValueError, KeyError, TypeError):
                    logging.error("Pub/Sub evento inválido descartado")
                else:
                    logging.info("Pub/Sub evento persistido event=%s", event["event_id"])
                ack = pubsub.post(endpoint + ":acknowledge", json={"ackIds": [item["ackId"]]}, timeout=15)
                ack.raise_for_status()
            group = group_file.read_text().strip() if group_file.exists() else ""
            if re.fullmatch(r"[0-9-]+@g\.us", group):
                for _ in range(10):
                    if not send_one(db, http, waha, group, api_key):
                        break
                    time.sleep(3)
            if time.time() - last_health >= 300:
                last_health = time.time()
                health = http.get(waha + "/api/sessions/default", headers={"X-Api-Key": api_key}, timeout=10)
                health.raise_for_status()
                uncertain = db.execute("SELECT COUNT(*) FROM deliveries WHERE status='uncertain'").fetchone()[0]
                current = (health.json().get("status"), uncertain, bool(group))
                if current != previous_health:
                    if current[0] != "WORKING" or uncertain or not group:
                        notify_health("⚠️ **WhatsApp — atenção**\n• Sessão: **{}**\n• Entregas incertas: **{}**\n• Grupo configurado: **{}**\nMensagens pendentes estão preservadas.".format(*current))
                    elif previous_health is not None:
                        notify_health("✅ **WhatsApp reconectado**\n• Envio de alertas retomado.")
                    previous_health = current
            if failures >= 3:
                notify_health("✅ **WhatsApp — conexão com o serviço recuperada**")
            failures = 0
        except Exception as exc:
            failures += 1
            if failures == 3:
                notify_health("⚠️ **WhatsApp — falha de conexão**\n• Verifique o serviço e a sessão.\n• Mensagens já recebidas estão preservadas no disco.")
            logging.error("WhatsApp ciclo falhou (%s)", type(exc).__name__)
        time.sleep(5)
    logging.info("Prazo de operação encerrado")


if __name__ == "__main__":
    main()
