import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from core.alerta import send_discord
from tendencias_busca.drive.termos import load_terms
from tendencias_busca.estados import ESTADOS
from tendencias_busca.google.coleta import trending, SourceUnavailable
from tendencias_busca.google.serpapi import compare_all
from tendencias_busca.janela import expired, now_local
from tendencias_busca.resumo import fingerprint, render


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--states", default=",".join(ESTADOS), help="UFs separadas por vírgulas, para diagnóstico")
    args = parser.parse_args(argv)
    states = list(dict.fromkeys(uf.strip().upper() for uf in args.states.split(",")))
    if not states or any(uf not in ESTADOS for uf in states):
        parser.error("Selecione UFs válidas")
    if expired():
        print("Período de coleta de tendências encerrado; sem consultas ou envios.")
        return
    snapshot = load_terms()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL")
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {"sent": []}
    day = now_local().date().isoformat()
    if not args.dry_run and not args.test:
        if state.get("trends_attempt_date") == day:
            print("Coleta de tendências já tentada hoje; sem novas consultas.")
            return
        # Salvar a tentativa ANTES da API limita também reexecuções após falha.
        state["trends_attempt_date"] = day
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(path)
    # Se a comparação falhar, não publicar um resumo incompleto como se estivesse completo.
    monitored = compare_all(snapshot["terms"], states)
    if not any(monitored.values()):
        raise SourceUnavailable("Nenhuma UF com dados suficientes para comparar todos os termos")
    with ThreadPoolExecutor(max_workers=3) as pool:
        general = dict(zip(states, pool.map(trending, states)))
    if not any(general.values()):
        return
    report = render(general, monitored, snapshot, datetime.now(timezone.utc).isoformat())
    key = "tendencias_busca:" + fingerprint(general, monitored, snapshot["terms"])
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False))
        return
    # Compara com a última versão, permitindo avisar se um tema reaparecer depois.
    if not args.test and state.get("latest_trends") == key:
        return
    send_discord(webhook, report, "Google Trends", test=args.test)
    if not args.test:
        state["latest_trends"] = key
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(path)


if __name__ == "__main__":
    run()
