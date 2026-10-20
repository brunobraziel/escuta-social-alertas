"""Mirror confirmed Discord messages to Pub/Sub without sharing BigQuery credentials.

Pending publications survive in an outbox; workflows retry and archive that file.
No-op until WHATSAPP_TOPIC is configured. Canonical copy: escuta-social-alertas.
"""
import argparse
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from datetime import datetime, timezone


def render(payload):
    blocks = [payload.get("content", "")]
    for embed in payload.get("embeds", []):
        if embed.get("title"):
            blocks.append("**" + embed["title"] + "**")
        blocks.append(embed.get("description", ""))
        blocks.extend("• **{}:** {}".format(f["name"], f["value"])
                      for f in embed.get("fields", []))
        blocks.append(embed.get("url", ""))
        blocks.append(embed.get("footer", {}).get("text", ""))
    text = "\n\n".join(block for block in blocks if block)
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.S)


def outbox():
    return Path(os.getenv("WHATSAPP_OUTBOX", ".whatsapp-outbox"))


def client():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials_path = os.environ["WHATSAPP_GOOGLE_APPLICATION_CREDENTIALS"]
    credentials, _ = google.auth.load_credentials_from_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/pubsub"])
    return AuthorizedSession(credentials)


def flush(session=None):
    directory = outbox()
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    if not files:
        return 0
    try:
        session = session or client()
        for path in files:
            record = json.loads(path.read_text())
            topic = record["topic"]
            if not re.fullmatch(r"projects/[a-z][a-z0-9-]+/topics/[A-Za-z][A-Za-z0-9._~+%-]+", topic):
                raise ValueError("Invalid topic")
            data = base64.b64encode(json.dumps(record["event"], ensure_ascii=False).encode()).decode()
            response = session.post("https://pubsub.googleapis.com/v1/" + topic + ":publish",
                                    json={"messages": [{"data": data}]}, timeout=20)
            response.raise_for_status()
            if not response.json().get("messageIds"):
                raise RuntimeError("Publication was not confirmed")
            path.unlink()
    except Exception as exc:
        # Never print response bodies, credentials or the message content.
        logging.warning("WhatsApp: publicação pendente (%s); outbox preservado.", type(exc).__name__)
    return len(list(directory.glob("*.json")))


def mirror(payload, receipt, *, kind=None):
    source = os.getenv("GITHUB_REPOSITORY", "local")
    topic = os.getenv("WHATSAPP_TOPIC", "")
    if source == "brunobraziel/escuta-social-etl":
        if kind != "serpapi_last_token":
            return
        topic = os.getenv("WHATSAPP_LAST_TOKEN_TOPIC", "")
    if not topic:
        return
    try:
        message_id = receipt.get("id") if isinstance(receipt, dict) else None
        if not message_id:
            raise ValueError("Discord receipt missing")
        event_id = hashlib.sha256((source + ":discord:" + str(message_id)).encode()).hexdigest()
        event = {"version": 1, "event_id": event_id, "source": source,
                 "discord_message_id": str(message_id), "text": render(payload),
                 "created_at": datetime.now(timezone.utc).isoformat()}
        if kind:
            event["kind"] = kind
        directory = outbox()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / (event_id + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"topic": topic, "event": event}, ensure_ascii=False))
        temporary.replace(target)
        flush()
    except Exception as exc:
        logging.error("WhatsApp: falha ao preparar espelhamento (%s).", type(exc).__name__)
        # A separate workflow step reports this without retrying a confirmed Discord send.
        outbox().mkdir(mode=0o700, parents=True, exist_ok=True)
        (outbox() / "ERROR").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--flush", action="store_true")
    parser.parse_args()
    remaining = flush()
    raise SystemExit(1 if remaining or (outbox() / "ERROR").exists() else 0)
