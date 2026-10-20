"""Manual transport test; does not collect data or access BigQuery."""
from datetime import datetime
import os
import time
from zoneinfo import ZoneInfo

import requests
from whatsapp_bridge import mirror, flush, outbox


def main():
    if not os.getenv("WHATSAPP_TOPIC"):
        raise RuntimeError("Configure WHATSAPP_TOPIC before testing")
    repository = os.environ["GITHUB_REPOSITORY"]
    url = "https://github.com/" + repository + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]
    payload = {"content": "🧪 **TESTE — integração WhatsApp**\n"
               + "• **Origem:** " + repository + "\n"
               + "• **Grupo:** Alerta de tendencias\n"
               + "• **Horário:** " + datetime.now(ZoneInfo("America/Fortaleza")).strftime("%d/%m/%Y %H:%M:%S") + "\n"
               + "• **Validação:** envio Discord → fila → WhatsApp.\n"
               + "• Esta mensagem não representa uma coleta ou ingestão real.\n" + url,
               "allowed_mentions": {"parse": []}}
    webhook = os.environ["TEST_DISCORD_WEBHOOK"]
    for attempt in range(4):
        response = requests.post(webhook, params={"wait": "true"}, json=payload, timeout=25)
        if response.status_code == 400 and response.json().get("code") == 220001 and "thread_name" not in payload:
            payload["thread_name"] = "TESTE — integração WhatsApp"
            continue
        if response.status_code == 429 and attempt < 3:
            time.sleep(min(30, max(1, float(response.json().get("retry_after", 2)))))
            continue
        if response.status_code != 200:
            raise RuntimeError("Discord HTTP " + str(response.status_code))
        receipt = response.json()
        if not receipt.get("id"):
            raise RuntimeError("Discord receipt missing")
        mirror(payload, receipt)
        if flush() or (outbox() / "ERROR").exists():
            raise RuntimeError("WhatsApp publication pending; outbox preserved")
        print("Teste publicado; recibo Discord:", receipt["id"])
        return
    raise RuntimeError("Discord attempts exhausted")


if __name__ == "__main__":
    main()
