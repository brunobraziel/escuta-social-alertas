import argparse
import importlib
import json
import logging
import os
from pathlib import Path
from core.alerta import fetch_feed, identifier, send_discord
from pesquisas_eleitorais.parser import matches_poll, parse_poll, as_alert


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true", help="Envia uma única pesquisa real identificada como teste")
    parser.add_argument("--state", default="state.json")
    args = parser.parse_args()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL ou use --dry-run")
    eligible, failures = [], []
    for site in ("g1", "cnn"):
        config = importlib.import_module(f"pesquisas_eleitorais.{site}.presidente")
        try:
            articles = fetch_feed(config.FEED_URL, config.ALLOWED_HOSTS, hours=168, predicate=matches_poll, description_limit=120000)
            for article in articles:
                poll = parse_poll(article)
                if poll:
                    eligible.append((article, poll, site))
                else:
                    logging.warning("%s: notícia sobre pesquisa sem tabela/metadados suficientes; não enviada", site)
        except Exception as error:
            failures.append(site)
            logging.error("%s: coleta falhou (%s)", site, type(error).__name__)
    if not eligible:
        logging.warning("Nenhuma pesquisa elegível com tabela completa nos feeds consultados")
        if failures or args.test:
            raise SystemExit(1)
        return
    article, poll, site = max(eligible, key=lambda item: item[0]["published"])
    alert = as_alert(article, poll)
    if failures:
        alert["message"] += "\nCobertura parcial: falha em " + ", ".join(failures)
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {"sent": []}
    # Mesmo levantamento/cenário publicado por outro portal não gera novo alerta.
    key = identifier("pesquisa:" + poll["registration"] + ":presidente:BR:2:votos_totais")
    if args.dry_run:
        print(json.dumps(alert, ensure_ascii=False))
    elif args.test or key not in state["sent"]:
        send_discord(webhook, alert, site, test=args.test)
        if not args.test:
            state["sent"].append(key)
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state))
            temporary.replace(state_path)
    else:
        logging.warning("Pesquisa mais recente elegível já enviada")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
