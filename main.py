"""Entrada genérica: carrega o catálogo e executa alertas com estado compartilhado."""
import argparse
import importlib
import json
import logging
from pathlib import Path

CATALOG = Path(__file__).with_name("alertas.json")


def load_catalog():
    entries = json.loads(CATALOG.read_text())["alertas"]
    identifiers = [entry["id"] for entry in entries]
    if len(identifiers) != len(set(identifiers)) or "all" in identifiers:
        raise ValueError("IDs do catálogo devem ser únicos e diferentes de all")
    for entry in entries:
        if not isinstance(entry["ativo"], bool):
            raise ValueError("ativo deve ser booleano")
    return entries


def execute(entries, mode, state):
    failed = []
    arguments = ["--state", state]
    if mode == "dry-run":
        arguments.append("--dry-run")
    elif mode == "test":
        arguments.append("--test")
    for entry in entries:
        logging.warning("Iniciando alerta %s (%s)", entry["id"], mode)
        try:
            module = importlib.import_module(entry["modulo"])
            module.run(arguments)
        except SystemExit as error:
            if error.code not in (0, None):
                failed.append(entry["id"])
                logging.error("Alerta %s falhou (saída %s)", entry["id"], error.code)
        except Exception as error:
            failed.append(entry["id"])
            # Não imprimir exceções potencialmente contendo credenciais.
            logging.error("Alerta %s falhou (%s)", entry["id"], type(error).__name__)
    return failed


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert", default="all", help="ID do catálogo ou all")
    parser.add_argument("--mode", choices=("dry-run", "live", "test"), default="dry-run")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    catalog = load_catalog()
    if args.list:
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return
    selected = [entry for entry in catalog if entry["ativo"] and (args.alert == "all" or entry["id"] == args.alert)]
    if not selected:
        parser.error("Alerta inexistente ou desativado")
    if args.mode == "test" and args.alert == "all":
        parser.error("No modo test, escolha um único --alert")
    failed = execute(selected, args.mode, args.state)
    if failed:
        logging.error("Alertas com falha: %s", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    run()
