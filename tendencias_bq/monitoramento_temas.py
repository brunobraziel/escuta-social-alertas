"""Resumo das consultas relacionadas do Trends Monitor, sem novas buscas SerpAPI."""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .em_alta_brasil import run as run_alert, _display, BIGQUERY_URL

TABLE_ID = "gtrends_monitoramento_temas"


def render(rows, ingestion_time, *, analysis=None):
    from .analise_ia import related_entries, related_groups, summary_block
    groups = defaultdict(list)
    for members in related_groups(related_entries(rows), analysis):
        groups[members[0]['context']].append(members)
    stamp = ingestion_time.isoformat() if hasattr(ingestion_time, "isoformat") else str(ingestion_time)
    updated = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    blocks = ["📈 *Consultas relacionadas — Trends Monitor*", f"*Dados atualizados:* {updated} — Brasília"]
    summary = summary_block(analysis)
    if summary:
        blocks.append(summary)
    discord_blocks = blocks.copy()
    for (theme, base, geo), items in sorted(groups.items()):
        topics = []
        for n, members in enumerate(items[:4], 1):
            representative = members[0]['term']
            line = f"{n}. *{_display(representative, 120)}*"
            variants = [m['term'] for m in members[1:]]
            if variants:
                line += "\n   Agrupadas: " + ' · '.join(variants)
            topics.append(line)
        area = "Brasil" if geo == "BR" else _display(geo)
        blocks.append(f"*{_display(theme, 60)}* — {area}\nBusca-base: {_display(base, 70)}\n" + "\n".join(topics))
        discord_blocks.append(f"**{_display(theme, 35)} · {_display(base, 35)} · {area}**\n" + topics[0].split("\n")[0])
    blocks.append("_Até quatro grupos por busca-base, com prioridade para consultas em alta. Variantes agrupadas permanecem visíveis; posições e índices não são somados. Fonte: Google Trends._")
    text = "\n\n".join(blocks)
    # Divide mensagens longas antes do sender; nenhum tema é descartado.
    sections = [""]
    for block in discord_blocks:
        if len(block) > 2700:
            raise ValueError("Bloco de tema excede limite")
        if len(sections[-1]) + len(block) + 2 > 2700:
            sections.append("")
        sections[-1] += ("\n\n" if sections[-1] else "") + block
    if len(sections) > 2:
        raise ValueError("Resumo excede duas seções Discord")
    return {"title": "Consultas relacionadas — Trends Monitor", "alert_title": "Consultas relacionadas por tema",
            "url": BIGQUERY_URL, "published": stamp, "message": sections[0],
            "details_message": sections[1] if len(sections) > 1 else "",
            "whatsapp_message": text, "whatsapp_presentation": "related", "footer": "Fonte: BigQuery · analise_redes.gtrends_monitoramento_temas"}


def run(argv=None):
    return run_alert(argv, table_id=TABLE_ID, alert_id=TABLE_ID, renderer=render, ai_kind="consultas")


if __name__ == "__main__":
    run()
