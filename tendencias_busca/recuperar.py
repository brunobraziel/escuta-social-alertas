"""Recupera comparações arquivadas; nunca chama /search nem cria novas buscas."""
import json
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from tendencias_busca.drive.termos import load_terms
from tendencias_busca.estados import ESTADOS
from tendencias_busca.google.coleta import trending, merge_batches, SourceUnavailable
from tendencias_busca.google.serpapi import parse_response
from tendencias_busca.resumo import render
from tendencias_busca.cache import snapshot, save_state


def archive_get(path, key):
    # Caminhos fixos de histórico: nenhum endpoint de nova pesquisa permitido.
    if path != "/searches.json" and not re.fullmatch(r"/searches/[a-f0-9]{24}\.json", path):
        raise ValueError("Endpoint fora do histórico")
    request = urllib.request.Request("https://serpapi.com" + path + "?" + urllib.parse.urlencode({"api_key": key}), headers={"User-Agent": "EscutaSocialAlertas/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError("Resposta grande")
        return json.loads(raw)
    except Exception:
        raise SourceUnavailable("Histórico indisponível; nenhuma busca nova foi criada") from None


def recover(state_path="state.json"):
    source = load_terms()
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise SourceUnavailable("Chave não configurada")
    history = archive_get("/searches.json", key)
    if isinstance(history, dict):
        history = history.get("searches", history.get("data", history.get("results", [])))
    if not isinstance(history, list):
        raise SourceUnavailable("Formato do histórico incompatível")
    candidates = []
    for entry in history[:6]:
        if isinstance(entry, str):
            search_id = entry
        elif isinstance(entry, dict):
            engine = entry.get("search_parameters", {}).get("engine", entry.get("engine"))
            if engine and engine != "google_trends":
                continue
            search_id = entry.get("id", entry.get("search_metadata", {}).get("id", ""))
        else:
            continue
        if not re.fullmatch(r"[a-f0-9]{24}", str(search_id)):
            continue
        data = archive_get("/searches/" + search_id + ".json", key)
        parameters = data.get("search_parameters", {})
        if parameters.get("engine") != "google_trends" or parameters.get("data_type") != "GEO_MAP" or parameters.get("geo") != "BR":
            continue
        terms = [t.strip() for t in parameters.get("q", "").split(",")]
        if len(terms) > 5 or not set(terms) <= set(source["terms"]):
            continue
        candidates.append((terms, data))
        for old_terms, old_data in candidates[:-1]:
            common = set(terms) & set(old_terms)
            if len(common) == 1 and set(terms) | set(old_terms) == set(source["terms"]):
                parts = [parse_response(data, terms), parse_response(old_data, old_terms)]
                monitored = merge_batches(source["terms"], parts, list(ESTADOS), groups=[terms, old_terms], anchor=next(iter(common)))
                if not any(monitored.values()):
                    continue
                with ThreadPoolExecutor(max_workers=3) as pool:
                    general = dict(zip(ESTADOS, pool.map(trending, ESTADOS)))
                report = render(general, monitored, source, datetime.now(timezone.utc).isoformat())
                dates = [obj.get("search_metadata", {}).get("created_at", "não informado") for obj in (data, old_data)]
                cached = snapshot(general, monitored, report, source, origin="reconstruido_do_historico_serpapi_com_rss_atualizado", monitored_at=min(dates))
                cached["report"]["footer"] = "Reconstruído de comparações arquivadas e RSS atualizado; não é cópia literal do teste anterior. " + cached["report"]["footer"]
                path = Path(state_path)
                state = json.loads(path.read_text()) if path.exists() else {"sent": []}
                state["trends_last_snapshot"] = cached
                save_state(path, state)
                print(f"Snapshot recuperado: {sum(bool(v) for v in monitored.values())}/27 UFs. Nenhuma busca nova criada; nenhum envio ao Discord.")
                return
    raise SourceUnavailable("Não foi encontrado um par de lotes arquivados compatíveis; nenhuma busca nova criada")


if __name__ == "__main__":
    try:
        recover()
    except Exception as error:
        print("Recuperação não concluída (" + type(error).__name__ + "). Sem novas buscas.")
        raise SystemExit(1) from None
