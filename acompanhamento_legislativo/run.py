import argparse
import importlib
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from core.alerta import fetch_feed, identifier, send_discord

SITES = ("g1", "cnn")


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=(*SITES, "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true", help="Envia um exemplo fictício marcado como teste")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20:
        parser.error("--limit deve estar entre 1 e 20")
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL ou use --dry-run")
    if args.test:
        sample = {"title": "Exemplo fictício: próximos passos da escala 6x1", "description": "Mensagem de teste da integração. Não representa uma notícia real.", "url": "https://www.senado.leg.br/", "published": datetime.now(timezone.utc).isoformat()}
        if args.dry_run:
            print(json.dumps(sample, ensure_ascii=False))
        else:
            send_discord(webhook, sample, "Teste controlado", test=True, whatsapp=False)
        return
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {"sent": []}
    seen = set(state["sent"])
    failed = 0
    sent = 0
    for site in SITES if args.site == "all" else (args.site,):
        config = importlib.import_module(f"acompanhamento_legislativo.{site}.escala_6x1")
        try:
            articles = fetch_feed(config.FEED_URL, config.ALLOWED_HOSTS)
        except Exception as error:
            logging.error("%s: coleta falhou (%s)", site, type(error).__name__)
            failed += 1
            continue
        logging.warning("%s: %s correspondências recentes", site, len(articles))
        for article in articles:
            key = identifier(article["url"])
            if key in seen or sent >= args.limit:
                continue
            if args.dry_run:
                print(json.dumps({"site": site, **article}, ensure_ascii=False))
            else:
                send_discord(webhook, article, site, whatsapp=False)
                seen.add(key)
                # Persistir a cada confirmação permite salvar entregas mesmo após falha posterior.
                temporary = state_path.with_suffix(".tmp")
                state["sent"] = sorted(seen)
                temporary.write_text(json.dumps(state))
                temporary.replace(state_path)
            sent += 1
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
