"""Alerta horário de assuntos em alta por UF, a partir do BigQuery."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from core.alerta import send_discord
from tendencias_bq.bigquery import fetch_latest_ingestion


ALERT_ID = "gtrends_em_alta_brasil"
MAX_TOPICS_PER_UF = 4
MAX_LINE_LENGTH = 2700
BIGQUERY_URL = "https://console.cloud.google.com/bigquery?project=comite-tecnologia"


STATE_NAMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AM': 'Amazonas', 'AP': 'Amapá',
    'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo',
    'GO': 'Goiás', 'MA': 'Maranhão', 'MG': 'Minas Gerais', 'MS': 'Mato Grosso do Sul',
    'MT': 'Mato Grosso', 'PA': 'Pará', 'PB': 'Paraíba', 'PE': 'Pernambuco',
    'PI': 'Piauí', 'PR': 'Paraná', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RO': 'Rondônia', 'RR': 'Roraima', 'RS': 'Rio Grande do Sul', 'SC': 'Santa Catarina',
    'SE': 'Sergipe', 'SP': 'São Paulo', 'TO': 'Tocantins',
}


def render_whatsapp(by_state, timestamp):
    stamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    updated = stamp.astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
    blocks = ['📈 *Assuntos em alta por estado*',
              f'*Dados atualizados:* {updated} — Brasília\nAté 4 assuntos por estado.']
    for uf in sorted(by_state):
        header = f'📍 *{STATE_NAMES.get(uf, uf)} ({uf})*'
        topics = ['• *' + (_display(row.get('rotulo'), 60) or 'Assunto sem rótulo') + '*'
                  for row in by_state[uf][:MAX_TOPICS_PER_UF]]
        blocks.append(header + '\n' + '\n'.join(topics))
    if not by_state:
        blocks.append('Nenhum assunto disponível nesta ingestão.')
    blocks.append('_Fonte: Google Trends. Tendências de busca não representam intenção de voto._')
    return '\n\n'.join(blocks)


def _display(value, limit=24):
    text = " ".join(str(value or "").split())
    text = text.replace("*", "").replace("`", "").replace("@", "＠")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _topic_line(row):
    label = _display(row.get("rotulo"), 30) or "Assunto sem rótulo"
    volume = row.get("volume")
    increase = row.get("aumento")
    metrics = []
    if volume is not None:
        metrics.append(f"vol. {volume}")
    if increase is not None:
        metrics.append(f"aumento {increase}")
    if row.get("ativa"):
        metrics.append("ativa")
    if row.get("candidato"):
        metrics.append("candidato")
    suffix = f" ({'; '.join(metrics)})" if metrics else ""
    return f"{label}{suffix}"


def _sort_number(row, field):
    value = row.get(field)
    try:
        return float(value) if value is not None else float("-inf")
    except (TypeError, ValueError):
        return float("-inf")


def render(rows, ingestion_time):
    """Monta uma mensagem compacta, dividida em duas seções do embed."""
    by_state = {}
    for row in rows:
        uf = str(row.get("uf") or "").strip().upper()
        if len(uf) != 2:
            continue
        by_state.setdefault(uf, []).append(row)
    for topics in by_state.values():
        topics.sort(key=lambda row: (
            -_sort_number(row, "aumento"),
            -_sort_number(row, "volume"),
            str(row.get("rotulo") or "").casefold(),
        ))

    timestamp = ingestion_time.isoformat() if hasattr(ingestion_time, "isoformat") else str(ingestion_time)
    lines = [
        "**Assuntos em alta por estado**",
        f"Ingestão mais recente: {timestamp}",
        "Até quatro assuntos por UF, ordenados por aumento e volume.",
        "",
    ]
    for uf in sorted(by_state):
        topics = by_state[uf][:MAX_TOPICS_PER_UF]
        lines.append(f"**{uf}:** " + (", ".join(_topic_line(topic) for topic in topics) or "sem assuntos"))

    if not by_state:
        lines.append("Nenhum assunto disponível na última ingestão.")

    # O Discord aceita duas descrições no sender compartilhado; distribui as UFs
    # entre elas respeitando o limite conservador de caracteres por seção.
    sections = [[], []]
    current = 0
    for line in lines:
        target = sections[current]
        if target and len("\n".join(target + [line])) > MAX_LINE_LENGTH:
            current += 1
            if current >= len(sections):
                raise ValueError("Resumo excede o limite de duas seções do Discord")
            target = sections[current]
        target.append(line)

    return {
        "title": "Google Trends em alta por estado",
        "url": BIGQUERY_URL,
        "published": timestamp,
        "alert_title": "Assuntos em alta por estado — BigQuery",
        "whatsapp_message": render_whatsapp(by_state, timestamp),
        "message": "\n".join(sections[0]),
        "details_message": "\n".join(sections[1]) if sections[1] else "",
        "footer": "Fonte: BigQuery · analise_redes.gtrends_em_alta_brasil. Ordenação por aumento e volume; dados da última hora_ingestao. Valores não representam intenção de voto.",
    }


def _timestamp(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--state", default="state.json")
    args = parser.parse_args(argv)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL ou use --dry-run")

    latest = fetch_latest_ingestion("gtrends_em_alta_brasil")
    rows = latest["rows"]
    if not rows:
        if args.dry_run:
            print(json.dumps({"alert": ALERT_ID, "rows": [], "hora_ingestao": None}, ensure_ascii=False, indent=2))
        else:
            print("Sem ingestão na última hora para gtrends_em_alta_brasil; nenhum alerta enviado.")
        return

    report = render(rows, latest["hora_ingestao"])
    ingestion_fingerprint = hashlib.sha256(
        f"{_timestamp(latest['hora_ingestao'])}:{latest['ingestao_id']}".encode("utf-8")
    ).hexdigest()
    if args.dry_run:
        print(json.dumps({
            "alert": ALERT_ID,
            "hora_ingestao": _timestamp(latest["hora_ingestao"]),
            "ingestao_id": latest["ingestao_id"],
            "rows": len(rows),
            "report": report,
        }, ensure_ascii=False, indent=2))
        return

    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {"sent": []}
    if not args.test and state.get(f"{ALERT_ID}_latest") == ingestion_fingerprint:
        return

    delivery = send_discord(webhook, report, "BigQuery · analise_redes", test=args.test)
    if args.test:
        return

    state[f"{ALERT_ID}_latest"] = ingestion_fingerprint
    state[f"{ALERT_ID}_delivered_at"] = datetime.now(timezone.utc).isoformat()
    state[f"{ALERT_ID}_message"] = delivery
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(path)


if __name__ == "__main__":
    run()
