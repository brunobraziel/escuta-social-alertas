"""Read operational events; Discord secret stays exclusively in GitHub."""
import base64
from datetime import datetime, timezone
import json
import os

import requests
from whatsapp_bridge import client


def main():
    if datetime.now(timezone.utc) >= datetime.fromisoformat("2026-10-25T03:00:00+00:00"):
        return
    session = client()
    endpoint = "https://pubsub.googleapis.com/v1/" + os.environ["WHATSAPP_HEALTH_SUBSCRIPTION"]
    response = session.post(endpoint + ":pull", json={"maxMessages": 20, "returnImmediately": True}, timeout=30)
    response.raise_for_status()
    for item in response.json().get("receivedMessages", []):
        event = json.loads(base64.b64decode(item["message"]["data"]))
        text = event["content"]
        if not isinstance(text, str) or not text or len(text) > 1800:
            raise ValueError("Invalid operational event")
        payload = {"content": text, "allowed_mentions": {"parse": []}}
        webhook = os.environ["DISCORD_WEBHOOK_URL"]
        result = requests.post(webhook, params={"wait": "true"}, json=payload, timeout=25)
        if result.status_code == 400 and result.json().get("code") == 220001:
            payload["thread_name"] = "Saúde da integração WhatsApp"
            result = requests.post(webhook, params={"wait": "true"}, json=payload, timeout=25)
        if result.status_code != 200 or not result.json().get("id"):
            raise RuntimeError("Discord did not confirm operational event")
        ack = session.post(endpoint + ":acknowledge", json={"ackIds": [item["ackId"]]}, timeout=15)
        ack.raise_for_status()
        print("Aviso operacional confirmado no Discord.")


if __name__ == "__main__":
    main()
