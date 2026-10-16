import hashlib
import json
from tendencias_busca.estados import ESTADOS


def short(text, limit=35):
    # Escapar marcação recebida das consultas sem alterar o fingerprint original.
    text = " ".join(text.split()).replace("*", "").replace("`", "").replace("@", "＠")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def fingerprint(general, monitored, terms):
    # Somente o conteúdo exibido é novidade; timestamps não provocam reenvio.
    data = {"general": {uf: rows[:2] for uf, rows in general.items()}, "monitored": {uf: [{"term": r["term"]} for r in (rows or [])[:2]] for uf, rows in monitored.items()}, "terms": terms}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def render(general, monitored, snapshot, now):
    first = ["**Assuntos em alta — últimas 24 horas**", "Até dois destaques por UF, na ordem dos feeds.", ""]
    second = ["**Escuta Social — comparação de todos os termos**", f"Lista: {len(snapshot['terms'])} termos · versão {snapshot['source_modified'][:10]}", "Até dois destaques; índice relativo entre monitorados.", ""]
    for uf in general:
        label = ESTADOS[uf]
        rows = general[uf]
        first.append(f"**{label}:** " + (", ".join(short(t) for t in rows[:2]) if rows else "sem tendências disponíveis"))
        values = monitored[uf]
        second.append(f"**{label}:** " + (", ".join(short(r['term'], 30) for r in values[:2]) if values else "dados insuficientes"))
    second += ["", "Todos os termos foram consultados; o post mostra dois por UF. Comparações entre lotes usam um termo comum; amostragem e arredondamento afetam a ordem."]
    body, details = "\n".join(first), "\n".join(second)
    if len(body) > 2800 or len(details) > 2800:
        raise ValueError("Resumo excede o limite de uma mensagem; reduza os destaques")
    return {"title": "Tendências de busca por estado", "description": "", "url": "https://trends.google.com/trending?geo=BR", "published": now, "alert_title": "Buscas por estado — resumo consolidado", "message": body, "details_message": details, "footer": "Google Trends: interesse relativo, não volume absoluto, opinião ou intenção de voto. Lista do Drive é uma versão revisada, sem sincronização automática."}
