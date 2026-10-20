"""Resumo das consultas relacionadas do Trends Monitor, sem novas buscas SerpAPI."""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .em_alta_brasil import run as run_alert, _display, BIGQUERY_URL

TABLE_ID = "gtrends_monitoramento_temas"


def render(rows, ingestion_time):
    groups = defaultdict(list)
    for row in rows:
        label = str(row.get("consulta") or "").strip()
        if label:
            groups[(row.get("macrotema") or "Outros temas", row.get("termo_base") or "", row.get("geo_busca") or "BR")].append(row)
    stamp = ingestion_time.isoformat() if hasattr(ingestion_time, "isoformat") else str(ingestion_time)
    updated = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m às %H:%M")
    blocks = ["📈 *Consultas relacionadas — Trends Monitor*", f"*Dados atualizados:* {updated} — Brasília"]
    discord_blocks = blocks.copy()
    for (theme, base, geo), items in sorted(groups.items()):
        # As posições só são comparáveis dentro de cada lista; prioriza em alta.
        items.sort(key=lambda row: (row.get("lista") != "em alta", int(row.get("posicao") or 999), str(row.get("consulta"))))
        seen = set()
        topics = []
        for item in items:
            key = " ".join(str(item["consulta"]).casefold().split())
            if key in seen:
                continue
            seen.add(key)
            topics.append("• *" + _display(item["consulta"], 90) + "*")
            if len(topics) == 4:
                break
        area = "Brasil" if geo == "BR" else _display(geo)
        blocks.append(f"*{_display(theme, 60)}* — {area}\nBusca-base: {_display(base, 70)}\n" + "\n".join(topics))
        discord_blocks.append(f"**{_display(theme, 35)} · {_display(base, 35)} · {area}**\n" + topics[0])
    blocks.append("_Até quatro consultas por tema e busca-base; prioridade para a lista em alta. Fonte: Google Trends. Não representa intenção de voto._")
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
            "whatsapp_message": text, "footer": "Fonte: BigQuery · analise_redes.gtrends_monitoramento_temas"}


def run(argv=None):
    return run_alert(argv, table_id=TABLE_ID, alert_id=TABLE_ID, renderer=render)


if __name__ == "__main__":
    run()
