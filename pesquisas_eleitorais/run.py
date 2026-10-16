import argparse
import importlib
import json
import logging
import os
from pathlib import Path
from core.alerta import fetch_feed, identifier, send_discord
from pesquisas_eleitorais.parser import matches_poll, parse_poll, parse_notice, as_alert
from pesquisas_eleitorais.web import discover, enrich


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true", help="Envia uma única pesquisa real identificada como teste")
    parser.add_argument("--state", default="state.json")
    args = parser.parse_args(argv)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL ou use --dry-run")
    eligible, failures = [], []
    for site in ("g1", "cnn", "poder360"):
        config = importlib.import_module(f"pesquisas_eleitorais.{site}.presidente")
        try:
            if hasattr(config, "INDEX_URL"):
                articles = discover(config.INDEX_URL, config.ALLOWED_HOSTS)
            else:
                articles = fetch_feed(config.FEED_URL, config.ALLOWED_HOSTS, hours=168, predicate=matches_poll, description_limit=120000)
            logging.warning("%s: %s notícias candidatas", site, len(articles))
            for article in articles[:6]:
                poll = parse_poll(article)
                if not poll and not hasattr(config, "INDEX_URL"):
                    try:
                        expanded = enrich(article, config.ALLOWED_HOSTS)
                    except Exception as error:
                        logging.warning("%s: HTML indisponível (%s)", site, type(error).__name__)
                        expanded = None
                    if expanded:
                        article = expanded
                        poll = parse_poll(article)
                if not poll:
                    poll = parse_notice(article)
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
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {"sent": []}
    unique = {}
    for article, poll, site in sorted(eligible, key=lambda item: (not item[1].get("notice", False), item[0]["published"]), reverse=True):
        # Preserva a chave histórica dos votos totais. Bases distintas não se misturam.
        key = identifier("pesquisa:" + poll["registration"] + ":presidente:BR:2:" + poll.get("base", "votos_totais"))
        covered = any(item[1]["registration"] == poll["registration"] for item in unique.values())
        if poll.get("notice"):
            covered = covered or any(identifier("pesquisa:" + poll["registration"] + ":presidente:BR:2:" + base) in state["sent"] for base in ("votos_totais", "votos_validos"))
        if not covered and key not in unique and (args.test or key not in state["sent"]):
            unique[key] = (article, poll, site)
    pending = list(unique.items())[:1 if args.test else 5]
    if not pending:
        logging.warning("Pesquisas elegíveis já enviadas")
    for key, (article, poll, site) in pending:
        alert = as_alert(article, poll)
        if failures:
            alert["message"] += "\nCobertura parcial: falha em " + ", ".join(failures)
        if args.dry_run:
            print(json.dumps(alert, ensure_ascii=False))
        else:
            delivery = send_discord(webhook, alert, site, test=args.test)
            if not args.test:
                state["sent"].append(key)
                state["poll_last_delivery"] = {"article": alert, "poll": poll, "delivery": delivery}
                temporary = state_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, ensure_ascii=False))
                temporary.replace(state_path)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
