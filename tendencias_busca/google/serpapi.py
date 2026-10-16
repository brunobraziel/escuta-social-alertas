"""Comparação regional via SerpApi, sem registrar chave, termos ou respostas brutas."""
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from tendencias_busca.estados import ESTADOS
from tendencias_busca.google.coleta import batches, merge_batches, SourceUnavailable


def compare_batch(terms, key):
    query = urllib.parse.urlencode({
        "engine": "google_trends", "data_type": "GEO_MAP_0" if len(terms) == 1 else "GEO_MAP", "q": ",".join(terms),
        "geo": "BR", "region": "REGION", "date": "now 1-d", "tz": 180,
        "hl": "pt-BR", "include_low_search_volume": "true", "api_key": key,
    })
    request = urllib.request.Request("https://serpapi.com/search.json?" + query, headers={"User-Agent": "EscutaSocialAlertas/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise SourceUnavailable("SerpApi: resposta excede limite")
        data = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise SourceUnavailable(f"SerpApi HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise SourceUnavailable("SerpApi: falha de conexão ou formato") from None
    return parse_response(data, terms)


def parse_response(data, terms):
    if data.get("error") or data.get("search_metadata", {}).get("status") != "Success":
        raise SourceUnavailable("SerpApi: consulta sem sucesso; detalhes omitidos")
    if len(terms) == 1:
        rows = data.get("interest_by_region")
        if not isinstance(rows, list):
            raise SourceUnavailable("SerpApi: interesse regional ausente")
        mapped = {}
        for row in rows:
            geo, value = row.get("geo", ""), row.get("extracted_value")
            if not isinstance(geo, str) or not geo.startswith("BR-") or geo[3:] not in ESTADOS:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise SourceUnavailable("SerpApi: índice regional incompatível")
            mapped[geo[3:]] = {terms[0]: value}
        return mapped
    rows = data.get("compared_breakdown_by_region")
    if not isinstance(rows, list):
        raise SourceUnavailable("SerpApi: comparação regional ausente")
    mapped = {}
    for row in rows:
        geo = row.get("geo", "")
        if not isinstance(geo, str) or not geo.startswith("BR-") or geo[3:] not in ESTADOS:
            continue
        values = {}
        for entry in row.get("values", []):
            term, value = entry.get("query"), entry.get("extracted_value")
            if term not in terms or term in values or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise SourceUnavailable("SerpApi: valores regionais incompatíveis")
            values[term] = value
        if set(values) == set(terms):
            mapped[geo[3:]] = values
    return mapped


def compare_all(terms, states):
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise SourceUnavailable("Configure SERPAPI_API_KEY")
    groups = batches(terms)
    if len(groups) > 2:
        raise SourceUnavailable("Lista excede dois lotes; revise a cota antes de ampliar")
    if any("," in term for term in terms):
        raise SourceUnavailable("Termos com vírgula não são suportados")
    # O primeiro lote também escolhe a referência: evita um termo raramente
    # pesquisado que apareça como zero ao lado de nomes muito populares.
    from statistics import median
    first_group = terms[:5]
    first = compare_batch(first_group, key)
    anchor = max(first_group, key=lambda term: (
        sum(values.get(term, 0) > 0 for values in first.values()),
        median(values.get(term, 0) for values in first.values()),
    ))
    groups, parts = [first_group], [first]
    if len(terms) > 5:
        group = [anchor, *terms[5:]]
        groups.append(group)
        parts.append(compare_batch(group, key))
    # Mesmos dois pedidos máximos; a escolha da referência não usa cota extra.
    return merge_batches(terms, parts, states, groups=groups, anchor=anchor)
