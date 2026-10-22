"""Resumo horário de interesse relativo por UF nos termos monitorados."""
import math
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .em_alta_brasil import STATE_NAMES, _display, BIGQUERY_URL, run as run_alert

from .bigquery import fetch_previous_state_ingestion

ALERT_ID = "monitoramento_estados_horario"


def comparison_key(row):
    return (str(row.get('uf') or '').strip().upper(),
            ' '.join(str(row.get('termo') or '').casefold().split()),
            row.get('grupo'), row.get('periodo'))


def movement(row, previous):
    old = previous.get(comparison_key(row))
    if old is None:
        return '— (sem base)'
    old = old.get('indice_vs_ancora')
    if old is None or not math.isfinite(float(old)) or float(old) < 0:
        return '— (sem base)'
    if float(old) == 0:
        return '↑ (base zero; sem %)'
    change = (float(row['indice_vs_ancora']) / float(old) - 1) * 100
    rounded = round(change, 1)
    if rounded == 0:
        return '→ (0,0%)'
    arrow = '↑' if rounded > 0 else '↓'
    percent = (f'{rounded:+.1f}' if abs(rounded) < 10000 else f'{rounded:+.1e}').replace('.', ',')
    return f'{arrow} ({percent}%)'


def ranked_states(rows):
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
        if current is None or float(index) > float(current['indice_vs_ancora']):
            states[uf][key] = row
    return {uf: sorted(terms.values(), key=lambda row: (-float(row['indice_vs_ancora']), str(row['termo']).casefold()))[:5]
            for uf, terms in states.items()}


def render(rows, ingestion_time, *, previous_rows=(), previous_ingestion_time=None, analysis=None):
    from .analise_ia import summary_block
    states = ranked_states(rows)
    previous = {}
    ambiguous = set()
    for row in previous_rows:
        key = comparison_key(row)
        if key in previous:
            ambiguous.add(key)
        previous[key] = row
    for key in ambiguous:
        previous.pop(key, None)
    stamp = ingestion_time.isoformat() if hasattr(ingestion_time, "isoformat") else str(ingestion_time)
    updated = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    blocks = ["📍 *Tópicos monitorados por estado*", f"*Resumo:* {now}\n*Dados coletados:* {updated} — Brasília\nAté 5 termos por estado, ordenados por interesse relativo à mesma referência."]
    if previous_ingestion_time:
        prior = previous_ingestion_time.isoformat() if hasattr(previous_ingestion_time, 'isoformat') else str(previous_ingestion_time)
        prior = datetime.fromisoformat(prior.replace('Z', '+00:00')).astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
        blocks.append(f'*Comparação:* coleta de {prior} → {updated}.\nSetas e % indicam variação do índice relativo, não da quantidade absoluta de buscas.')
    else:
        blocks.append('Sem coleta anterior comparável. Setas e % aparecerão quando houver base.')
    summary = summary_block(analysis)
    if summary:
        blocks.append(summary)
    discord_blocks = blocks.copy()
    for uf, name in sorted(STATE_NAMES.items(), key=lambda pair: pair[1]):
        terms = states.get(uf, [])
        topics = [f"{n}. *" + _display(row['termo'], 60) + "* " + movement(row, previous) for n, row in enumerate(terms, 1)]
        if not topics:
            topics = ["• Sem índice válido disponível neste lote."]
        header = f"📍 *{name} ({uf})*\n"
        blocks.append(header + "\n".join(topics))
        # Uma linha por UF no Discord; WhatsApp mantém cinco linhas numeradas.
        compact = [f"{n}." + _display(row['termo'], 12) + " " + movement(row, previous).replace('base zero; sem %', 'base 0').replace('— (sem base)', 's/base')
                   for n, row in enumerate(terms, 1)]
        discord_blocks.append(f"*{uf}* " + (' · '.join(compact) if compact else 'Sem índice válido.'))
    blocks.append("_Fonte: Google Trends / BigQuery. Ranking restrito aos termos monitorados; não mede volume absoluto nem intenção de voto. Cada lote é enviado uma única vez._")
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
            "whatsapp_presentation": "states",
            "footer": "Fonte: analise_redes.gtrends_monitoramento_cidades · recorte REGION"}


def run(argv=None):
    return run_alert(argv, table_id="gtrends_monitoramento_cidades", alert_id=ALERT_ID, renderer=render, comparison_reader=fetch_previous_state_ingestion, ai_kind="estados")


if __name__ == "__main__":
    run()
