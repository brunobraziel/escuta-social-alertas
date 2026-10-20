"""Resumo horário de interesse relativo por UF nos termos monitorados."""
import math
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .em_alta_brasil import STATE_NAMES, _display, BIGQUERY_URL, run as run_alert

ALERT_ID = "monitoramento_estados_horario"


def render(rows, ingestion_time):
    states = defaultdict(dict)
    for row in rows:
        uf = str(row.get("uf") or "").strip().upper()
        term = " ".join(str(row.get("termo") or "").split())
        index = row.get("indice_vs_ancora")
        if uf not in STATE_NAMES or not term or row.get("eh_ancora") is not False:
            continue
        if index is None or not math.isfinite(float(index)) or float(index) <= 0:
            continue
        key = term.casefold()
        current = states[uf].get(key)
        if current is None or float(index) > current[0]:
            states[uf][key] = (float(index), term)
    stamp = ingestion_time.isoformat() if hasattr(ingestion_time, "isoformat") else str(ingestion_time)
    updated = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    blocks = ["📍 *Tópicos monitorados por estado*", f"*Resumo:* {now}\n*Dados coletados:* {updated} — Brasília\nAté 4 termos por estado, ordenados por interesse relativo à mesma referência."]
    discord_blocks = blocks.copy()
    for uf, name in sorted(STATE_NAMES.items(), key=lambda pair: pair[1]):
        terms = sorted(states[uf].values(), key=lambda pair: (-pair[0], pair[1].casefold()))[:4]
        topics = ["• *" + _display(term, 40) + "*" for _, term in terms]
        if not topics:
            topics = ["• Sem índice válido disponível neste lote."]
        header = f"📍 *{name} ({uf})*\n"
        blocks.append(header + "\n".join(topics))
        compact = ["• *" + _display(term, 24) + "*" for _, term in terms] if terms else topics
        discord_blocks.append(header + "\n".join(compact))
    blocks.append("_Fonte: Google Trends / BigQuery. Ranking restrito aos termos monitorados; não mede crescimento, volume absoluto ou intenção de voto. O envio horário pode reutilizar o último lote._")
    discord_blocks.append(blocks[-1])
    sections = [""]
    for block in discord_blocks:
        if len(sections[-1]) + len(block) + 2 > 2700:
            sections.append("")
        sections[-1] += ("\n\n" if sections[-1] else "") + block
    if len(sections) > 2:
        raise ValueError("Resumo excede duas seções Discord")
    return {"title": "Tópicos monitorados por estado", "alert_title": "Resumo horário por estado",
            "url": BIGQUERY_URL, "published": stamp, "message": sections[0],
            "details_message": sections[1] if len(sections) > 1 else "",
            "whatsapp_message": "\n\n".join(blocks),
            "footer": "Fonte: analise_redes.gtrends_monitoramento_cidades · recorte REGION"}


def run(argv=None):
    return run_alert(argv, table_id="gtrends_monitoramento_cidades", alert_id=ALERT_ID, renderer=render, hourly=True)


if __name__ == "__main__":
    run()
