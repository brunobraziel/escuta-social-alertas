"""Single-consumer Pub/Sub -> durable SQLite outbox -> local WAHA."""
import base64
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
    # A crash during an HTTP request can mean it was accepted remotely.
    with db:
        db.execute("UPDATE deliveries SET status='uncertain' WHERE status='sending'")
    return db


def parts(text, limit=3500):
    result = []
    while len(text) > limit:
        split = text.rfind("\n", 0, limit)
        if split < limit // 2:
            split = limit
        result.append(text[:split])
        text = text[split:].lstrip("\n")
    if text:
        result.append(text)
    return result


def accept(db, event):
    if (event.get("version") != 1 or
        not re.fullmatch(r"[a-f0-9]{64}", event.get("event_id", "")) or
        event.get("source") not in os.environ["ALLOWED_SOURCES"].split(",") or
        not isinstance(event.get("text"), str) or not 0 < len(event["text"]) <= 30000):
        raise ValueError("Invalid event")
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
    chunks = parts(json.loads(raw)["text"])
    receipts = json.loads(receipts_raw)
    # Check before changing delivery state; offline sessions leave messages pending.
    health = session.get(waha + "/api/sessions/default", headers={"X-Api-Key": api_key}, timeout=10)
    health.raise_for_status()
    if health.json().get("status") != "WORKING":
        return False
    with db:
        db.execute("UPDATE deliveries SET status='sending',updated=? WHERE event_id=?", (time.time(), event_id))
    try:
        response = session.post(waha + "/api/sendText", headers={"X-Api-Key": api_key},
                                json={"session": "default", "chatId": group,
                                      "text": chunks[index], "linkPreview": False}, timeout=45)
        response.raise_for_status()
        receipt = message_receipt(response.json(), group)
    except Exception as exc:
        # Never blindly replay an ambiguous send. Reconciliation is manual.
        with db:
            db.execute("UPDATE deliveries SET status='uncertain',updated=? WHERE event_id=?", (time.time(), event_id))
        logging.error("WhatsApp entrega incerta event=%s erro=%s", event_id, type(exc).__name__)
        return False
    receipts.append(receipt)
    index += 1
    with db:
        db.execute("UPDATE deliveries SET status=?,next_part=?,receipts=?,updated=? WHERE event_id=?",
                   ("sent" if index == len(chunks) else "pending", index,
                    json.dumps(receipts), time.time(), event_id))
    logging.info("WhatsApp confirmação event=%s parte=%d/%d", event_id, index, len(chunks))
    return True


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
    db = connect("/data/deliveries.sqlite")
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
