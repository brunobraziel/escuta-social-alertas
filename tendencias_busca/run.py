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
from tendencias_busca.cache import snapshot, save_state, read_snapshot


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--cached", action="store_true", help="Reutiliza snapshot sem consultar qualquer fonte")
    parser.add_argument("--cache-file", help="JSON exportado da última coleta")
    parser.add_argument("--states", default=",".join(ESTADOS), help="UFs separadas por vírgulas, para diagnóstico")
    args = parser.parse_args(argv)
    if args.cached:
        saved = read_snapshot(args.state, args.cache_file)
        if args.test:
            webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
            if not webhook:
                parser.error("Configure DISCORD_WEBHOOK_URL para reenviar teste em cache")
            reports = saved.get("reports", [saved["report"]])
            for item in reports:
                report = dict(item)
                report["alert_title"] = "[CACHE] " + report.get("alert_title", "Resumo").removeprefix("[TESTE] ")
                report["footer"] = "REPRODUÇÃO DE CACHE, sem nova coleta. " + report["footer"]
                send_discord(webhook, report, "Google Trends (cache)", test=True)
        else:
            print(json.dumps(saved, ensure_ascii=False, indent=2))
        return
    states = list(dict.fromkeys(uf.strip().upper() for uf in args.states.split(",")))
    if not states or any(uf not in ESTADOS for uf in states):
        parser.error("Selecione UFs válidas")
    if expired():
        print("Período de coleta de tendências encerrado; sem consultas ou envios.")
        return
    snapshot_data = load_terms()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL")
    if snapshot_data.get("mode") == "clusters_daily":
        from tendencias_busca.clusters import execute
        return execute(args, snapshot_data, states, webhook)
    if snapshot_data.get("mode") == "filter_trending":
        from tendencias_busca.filtrado import execute
        return execute(args, snapshot_data, states, webhook)
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {"sent": []}
    now = now_local()
    slot = f"{now.date().isoformat()}T{now.hour // 3 * 3:02d}"
    if not args.dry_run and not args.test:
        if state.get("trends_attempt_slot") == slot:
            print("Coleta de tendências já tentada nesta janela de 3h; sem novas consultas.")
            return
        # Salvar a tentativa ANTES da API limita também reexecuções após falha.
        state["trends_attempt_slot"] = slot
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(path)
    # Se a comparação falhar, não publicar um resumo incompleto como se estivesse completo.
    monitored = compare_all(snapshot_data["terms"], states)
    if not any(monitored.values()):
        raise SourceUnavailable("Nenhuma UF com dados suficientes para comparar todos os termos")
    with ThreadPoolExecutor(max_workers=3) as pool:
        general = dict(zip(states, pool.map(trending, states)))
    if not any(general.values()):
        return
    report = render(general, monitored, snapshot_data, datetime.now(timezone.utc).isoformat())
    key = "tendencias_busca:" + fingerprint(general, monitored, snapshot_data["terms"])
    if not args.dry_run:
        # Salva dados normalizados antes de enviar; falha de Discord não perde coleta.
        state["trends_last_snapshot"] = snapshot(general, monitored, report, snapshot_data)
        save_state(path, state)
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False))
        return
    # Compara com a última versão, permitindo avisar se um tema reaparecer depois.
    if not args.test and state.get("latest_trends") == key:
        return
    delivery = send_discord(webhook, report, "Google Trends", test=args.test)
    state["trends_last_snapshot"]["delivery"] = {"confirmed_at": datetime.now(timezone.utc).isoformat(), "test": args.test, "message": delivery}
    state["trends_last_delivered_snapshot"] = json.loads(json.dumps(state["trends_last_snapshot"]))
    save_state(path, state)
    if not args.test:
        state["latest_trends"] = key
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(path)


if __name__ == "__main__":
    run()
