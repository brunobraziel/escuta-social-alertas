"""RSS por UF e comparação regional pelo endpoint público não oficial do Explore."""
import http.cookiejar
import json
import math
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from core.alerta import clean

HEADERS = {"User-Agent": "EscutaSocialAlertas/0.1 (Google Trends reader)"}


class SourceUnavailable(RuntimeError):
    pass


def read_url(opener, url):
    try:
        with opener.open(urllib.request.Request(url, headers=HEADERS), timeout=25) as response:
            data = response.read(5_000_001)
            if len(data) > 5_000_000:
                raise SourceUnavailable("Resposta excede 5 MB")
            return data
    except urllib.error.HTTPError as error:
        # Sem rotação de IP, quebra de CAPTCHA ou retentativas em bloqueios.
        raise SourceUnavailable(f"Google Trends HTTP {error.code}") from None
    except urllib.error.URLError:
        raise SourceUnavailable("Google Trends indisponível") from None


def trending(uf):
    from tendencias_busca.estados import ESTADOS
    if uf not in ESTADOS:
        raise ValueError("UF inválida")
    url = "https://trends.google.com/trending/rss?geo=BR-" + uf
    root = ET.fromstring(read_url(urllib.request.build_opener(), url))
    # Não aceitar um redirecionamento lógico para o feed nacional.
    link = root.findtext("channel/link") or ""
    if urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("geo") != ["BR-" + uf]:
        raise SourceUnavailable("Feed não confirma a UF solicitada")
    result = []
    now = datetime.now(timezone.utc)
    for item in root.findall("channel/item"):
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "")
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            age = (now - date).total_seconds()
            if not 0 <= age <= 86400:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        title = clean(item.findtext("title"))
        if title and title.casefold() not in {t.casefold() for t in result}:
            result.append(title)
    # Preserva a ordem do feed; não interpreta como ranking por volume.
    return result


def read_json(opener, url):
    raw = read_url(opener, url).decode("utf-8")
    if raw.startswith(")]}'"):
        raw = raw.split("\n", 1)[1]
    return json.loads(raw)


def batches(terms):
    # Um termo comum permite conectar escalas relativas de lotes diferentes.
    anchor = terms[0]
    return [[anchor, *terms[i:i + 4]] for i in range(1, len(terms), 4)]


def compare_batch(opener, terms):
    request = {"comparisonItem": [{"keyword": t, "geo": "BR", "time": "now 1-d"} for t in terms], "category": 0, "property": ""}
    query = urllib.parse.urlencode({"hl": "pt-BR", "tz": 180, "req": json.dumps(request)})
    data = read_json(opener, "https://trends.google.com/trends/api/explore?" + query)
    widget = next((w for w in data.get("widgets", []) if w.get("id") == "GEO_MAP"), None)
    if not widget:
        raise SourceUnavailable("Widget regional não encontrado")
    widget_request = {**widget["request"], "resolution": "REGION"}
    query = urllib.parse.urlencode({"hl": "pt-BR", "tz": 180, "req": json.dumps(widget_request), "token": widget["token"]})
    result = read_json(opener, "https://trends.google.com/trends/api/widgetdata/comparedgeo?" + query)
    rows = result.get("default", {}).get("geoMapData")
    if not isinstance(rows, list) or not rows:
        raise SourceUnavailable("Comparação regional vazia ou formato incompatível")
    mapped = {}
    for row in rows:
        code, values = row.get("geoCode"), row.get("value")
        if not isinstance(code, str) or not code.startswith("BR-"):
            continue
        if not isinstance(values, list) or len(values) != len(terms):
            continue
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100 for v in values):
            continue
        mapped[code[3:]] = dict(zip(terms, values))
    return mapped


def merge_batches(terms, parts, states, groups=None, anchor=None):
    expected = groups or batches(terms)
    if len(parts) != len(expected):
        raise SourceUnavailable("Comparação incompleta: faltam lotes")
    output = {}
    anchor = anchor or terms[0]
    for uf in states:
        ratios = {anchor: 1.0}
        sufficient = True
        for group, part in zip(expected, parts):
            values = part.get(uf, {})
            # Zero é arredondamento/insuficiência, não ausência de buscas.
            # Sem todos os termos mensuráveis não produzimos ranking completo.
            if any(not isinstance(values.get(t), (int, float)) or not math.isfinite(values[t]) or values[t] < 0 for t in group):
                sufficient = False
                break
            if values.get(anchor, 0) <= 0:
                sufficient = False
                break
            ratios.update({t: values[t] / values[anchor] for t in group if t != anchor})
        if sufficient and set(ratios) == set(terms):
            # Zero representa valor abaixo da resolução, não zero buscas.
            # Só destacamos os quatro maiores se valores arredondados a zero
            # não puderem ultrapassar nenhum deles (limite conservador de 1).
            ordered = sorted(ratios.values(), reverse=True)
            zero_upper = max((1 / part[uf][anchor] for group, part in zip(expected, parts) if any(part[uf][t] == 0 for t in group)), default=0)
            if len(ordered) < min(4, len(terms)) or ordered[min(4, len(terms)) - 1] <= zero_upper:
                output[uf] = None
                continue
            maximum = max(ratios.values())
            output[uf] = [{"term": t, "index": round(v / maximum * 100, 1)} for t, v in sorted(ratios.items(), key=lambda x: (-x[1], x[0].casefold()))]
        else:
            output[uf] = None
    return output


def compare_all(terms, states):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    parts = [compare_batch(opener, group) for group in batches(terms)]
    return merge_batches(terms, parts, states)
