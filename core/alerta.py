import hashlib
import html
import json
import re
import unicodedata
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

TOPIC = re.compile(r"\b(?:escala\s+6\s*(?:x|por|[×])\s*1|fim\s+da\s+6\s*x\s*1)\b")
STEPS = ("promulg", "entra em vigor", "entrada em vigor", "vigencia", "transicao", "publicacao")


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


def matches(title, description):
    text = normalize(title + " " + description)
    return bool(TOPIC.search(normalize(title))) and any(term in text for term in STEPS)


def identifier(url):
    return hashlib.sha256(url.encode()).hexdigest()


def fetch_feed(url, allowed_hosts, hours=48, predicate=matches, description_limit=450):
    from urllib.parse import urlparse, urlunparse
    request = urllib.request.Request(url, headers={"User-Agent": "EscutaSocialAlertas/0.1 (RSS reader)", "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("Feed excede limite de 5 MB")
    tree = ET.fromstring(raw)
    now = datetime.now(timezone.utc)
    articles = []
    for item in tree.findall(".//item"):
        title = clean(item.findtext("title"))
        description = clean(item.findtext("description"))
        link = (item.findtext("link") or "").strip()
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username:
            continue
        link = urlunparse(parsed._replace(fragment=""))
        date = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(date)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age = (now - published).total_seconds()
            if age < -300 or age > hours * 3600:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        if predicate(title, description):
            articles.append({"title": title, "description": description[:description_limit], "url": link, "published": published.isoformat()})
    return sorted(articles, key=lambda x: x["published"], reverse=True)


def send_discord(webhook, article, site, test=False):
    import time
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    webhook = webhook.strip()
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or parsed.hostname != "discord.com" or not parsed.path.startswith("/api/webhooks/"):
        raise ValueError("Webhook Discord inválido")
    description = article.get("message")
    if description is None:
        description = article.get("title", "")[:250] + "\n\n" + article.get("description", "")[:450]
    payload = {"allowed_mentions": {"parse": []}, "embeds": [{
        "title": ("[TESTE] " if test else "") + article.get("alert_title", "Escala 6x1 — próximos passos"),
        "url": article["url"],
        "description": description[:4000],
        "fields": [{"name": "Fonte", "value": site}, {"name": "Publicado em", "value": article["published"]}],
        "footer": {"text": article.get("footer", "Correspondência temática; não confirma mudança legislativa.")}
    }]}
    if article.get("details_message"):
        if len(article.get("message", "")) > 2800 or len(article["details_message"]) > 2800:
            raise ValueError("Seções do resumo excedem o limite de uma mensagem")
        payload["embeds"].append({"description": article["details_message"]})
    # wait=true exige confirmação de criação da mensagem.
    query = dict(parse_qsl(parsed.query))
    query["wait"] = "true"
    endpoint = urlunparse(parsed._replace(query=urlencode(query), fragment=""))
    for attempt in range(3):
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": "EscutaSocialAlertas/0.1"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                result = json.load(response)
                if not result.get("id"):
                    raise RuntimeError("Discord não confirmou a mensagem")
                from whatsapp_bridge import mirror
                mirror(payload, result)
                return {"id": result["id"], "channel_id": result.get("channel_id")}
        except urllib.error.HTTPError as error:
            try:
                details = json.loads(error.read())
            except (ValueError, UnicodeDecodeError):
                details = {}
            if details.get("code") == 220001 and attempt < 2 and "thread_name" not in payload:
                payload["thread_name"] = (("[TESTE] " if test else "") + article.get("alert_title", "Escala 6x1") + " — " + article["title"])[:100]
                continue
            if error.code != 429 or attempt == 2:
                code = details.get("code")
                hints = {
                    50035: "Formato inválido da mensagem ou do destino.",
                    220001: "Canal de fórum exige thread_id ou thread_name.",
                    10015: "Webhook inexistente ou removido.",
                    50027: "Token do webhook inválido.",
                    50001: "Webhook sem acesso ao destino.",
                    50013: "Permissões insuficientes.",
                }
                hint = hints.get(code, "Verifique o tipo de canal e a configuração do webhook.")
                raise RuntimeError(f"Discord HTTP {error.code}; código {code if isinstance(code, int) else 'indisponível'}. {hint}") from None
            retry = details.get("retry_after", 2)
            time.sleep(min(float(retry), 30))
        except urllib.error.URLError:
            raise RuntimeError("Falha de conexão com Discord; entrega pode ser incerta") from None
