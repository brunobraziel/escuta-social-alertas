"""Lê uma mensagem já enviada pelo webhook, sem executar coleta ou enviar nada."""
import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from tendencias_busca.cache import save_state


def recover(message_url, state_path="state.json"):
    match = re.fullmatch(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)/?", message_url.strip())
    if not match:
        raise ValueError("Link de mensagem Discord inválido")
    _, thread_id, message_id = match.groups()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    parsed = urllib.parse.urlparse(webhook)
    if parsed.scheme != "https" or parsed.hostname != "discord.com" or not re.fullmatch(r"/api/webhooks/\d+/[^/]+", parsed.path):
        raise ValueError("Webhook inválido")
    query = urllib.parse.urlencode({"thread_id": thread_id})
    url = urllib.parse.urlunparse(parsed._replace(path=parsed.path + "/messages/" + message_id, query=query, fragment=""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "EscutaSocialAlertas/0.1"}), timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Discord HTTP {error.code}") from None
    except Exception:
        raise RuntimeError("Não foi possível ler a mensagem") from None
    if str(result.get("id")) != message_id:
        raise ValueError("Mensagem retornada não corresponde ao link")
    embeds = result.get("embeds", [])
    if not embeds:
        raise ValueError("Mensagem não contém resumo em embeds")
    first = embeds[0]
    published = next((f.get("value") for f in first.get("fields", []) if f.get("name") == "Publicado em"), result.get("timestamp"))
    report = {
        "title": "Mensagem original recuperada do Discord",
        "description": "", "url": first.get("url", message_url),
        "published": published,
        "alert_title": first.get("title", "Resumo de tendências"),
        "message": first.get("description", ""),
        "details_message": embeds[1].get("description", "") if len(embeds) > 1 else "",
        "footer": first.get("footer", {}).get("text", ""),
    }
    # Mantém texto real; não inventa índices ou termos ausentes do post antigo.
    cached = {
        "schema_version": 1, "origin": "mensagem_original_discord_sem_nova_coleta",
        "collected_at": published, "monitored_at": published,
        "terms_count": None, "source_version": None,
        "general": None, "monitored": None,
        "report": report,
        "delivery": {"confirmed_at": result.get("timestamp"), "test": "[TESTE]" in report["alert_title"], "message": {"id": message_id, "channel_id": thread_id}},
        "discord_message": {"url": message_url, "content": result.get("content", ""), "embeds": embeds},
    }
    path = Path(state_path)
    state = json.loads(path.read_text()) if path.exists() else {"sent": []}
    state["trends_last_snapshot"] = cached
    state["trends_last_delivered_snapshot"] = cached
    save_state(path, state)
    print("Mensagem original recuperada. Sem chamadas à SerpApi, sem novo envio e sem dados inventados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-url", required=True)
    args = parser.parse_args()
    try:
        recover(args.message_url)
    except Exception as error:
        detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print("Recuperação Discord interrompida: " + detail)
        raise SystemExit(1) from None
