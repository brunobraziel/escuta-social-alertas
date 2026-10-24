import argparse
import hashlib
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.alerta import clean, normalize, send_discord

URL = 'https://trends.google.com.br/trending/rss?geo=BR'
NS = {'ht': 'https://trends.google.com/trending/rss'}
POLITICS = re.compile(r'\b(?:politic[ao]s?|eleic(?:ao|oes)|eleitoral|presidente|presidencial|candidat[ao]s?|governador[a]?|prefeit[ao]|senad[ao]|senador[a]?|deputad[ao]s?|congresso|camara dos deputados|stf|tse|lula|lulinha|bolsonaro|vorcaro|haddad|tarcisio|ciro gomes|joice hasselmann|joao amoedo|debate na globo)\b')


def is_political(item):
    headlines = ' '.join(n.findtext('ht:news_item_title', default='', namespaces=NS)
                         for n in item.findall('ht:news_item', NS))
    return bool(POLITICS.search(normalize(clean(item.findtext('title')) + ' ' + clean(headlines))))



def parse(raw):
    root = ET.fromstring(raw)
    topics, seen = [], set()
    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        key = title.casefold()
        if not title or key in seen or not is_political(item):
            continue
        try:
            date = parsedate_to_datetime(item.findtext('pubDate') or '')
            if date.tzinfo is None:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        seen.add(key)
        topics.append({'title': title[:160].replace('*', '').replace('`', '').replace('@', '＠'),
                       'traffic': clean(item.findtext('ht:approx_traffic', namespaces=NS))[:30],
                       'published': date.isoformat()})
    # Mais recentes primeiro; empates preservam a ordem original do RSS.
    topics.sort(key=lambda t: datetime.fromisoformat(t['published']), reverse=True)
    return topics[:5]


def fetch():
    request = urllib.request.Request(URL, headers={'User-Agent': 'EscutaSocialAlertas/1.0', 'Accept': 'application/rss+xml, text/xml'})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError('RSS excede 5 MB')
    topics = parse(raw)
    if not ET.fromstring(raw).findall('./channel/item'):
        raise ValueError('RSS sem itens; não publicar resumo vazio')
    return topics


def fingerprint(topics):
    # Datas não mudam o conteúdo da lista; mudanças de ordem/estimativa mudam.
    content = [(t['title'].casefold(), t['traffic']) for t in topics]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


def render(topics):
    stamp = datetime.now(timezone.utc)
    local = stamp.astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
    lines = ['🔎 *Política — assuntos recentes no Google · Brasil*', f'Consulta: {local}', '']
    for i, topic in enumerate(topics, 1):
        estimate = f" — {topic['traffic']} buscas" if topic['traffic'] else ''
        lines.append(f"{i}. *{topic['title']}*{estimate}")
    lines += ['', '📊 Estimativas informadas pelo Google. Recorte político por termos e manchetes do RSS. Ordem de recência, não de volume; não indica apoio ou intenção de voto.', '🔗 Fonte: Google Trends', URL]
    text = '\n'.join(lines)
    return {'title': 'Política — assuntos recentes no Google · Brasil', 'alert_title': 'Política — assuntos recentes no Google · Brasil',
            'url': URL, 'published': stamp.isoformat(), 'message': text, 'whatsapp_message': text,
            'footer': 'RSS público do Google Trends · Brasil'}


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--state', default='state.json')
    args = parser.parse_args(argv)
    topics = fetch()
    if not topics:
        print('Sem assuntos políticos identificados no RSS; sem envio.')
        return
    report = render(topics)
    if args.dry_run:
        print(report['whatsapp_message'])
        return
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {'sent': []}
    key = fingerprint(topics)
    if state.get('latest_google_trends_rss') == key:
        print('Lista inalterada; sem novo envio.')
        return
    webhook = os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
    if not webhook or not os.environ.get('WHATSAPP_TOPIC', '').strip():
        raise RuntimeError('Configure Discord e o destino WhatsApp antes de publicar')
    send_discord(webhook, report, 'Google Trends RSS')
    state['latest_google_trends_rss'] = key
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(path)
    print('Resumo publicado; estado atualizado.')


if __name__ == '__main__':
    run()
