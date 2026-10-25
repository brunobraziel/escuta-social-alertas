"""Ranking político do RSS público: sem SerpAPI, IA ou soma de estimativas."""
import argparse
import hashlib
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from core.alerta import clean, normalize, send_discord

URL = 'https://trends.google.com.br/trending/rss?geo=BR'
NS = {'ht': 'https://trends.google.com/trending/rss'}
KEY = 'politica_trending_v3'
TRENDS_URL = 'https://trends.google.com/trending?geo=BR&category=14&hours=24&hl=pt-BR'
POLITICS = re.compile(r'\b(?:politic[ao]s?|eleic(?:ao|oes)|eleitoral|presidente|presidencial|candidat[ao]s?|governador[a]?|prefeit[ao]|senad[ao]|senador[a]?|deputad[ao]s?|congresso|camara dos deputados|stf|tse|lula|lulinha|bolsonaro|vorcaro|haddad|tarcisio|ciro gomes|joice hasselmann|joao amoedo|debate na globo)\b')
UNRELATED = re.compile(r'\b(?:loteria|sorteio|timemania|milionaria|dia de sorte|mega sena)\b')
STOP = set('a o as os de do da dos das e com no na em para por um uma hoje horario ultima ultimo'.split())


def traffic_value(value):
    value = normalize(value).replace(' ', '').replace('+', '')
    match = re.fullmatch(r'([\d.,]+)(mil|mi|k|m)?', value)
    if not match:
        return None
    number, suffix = match.groups()
    try:
        number = float(number.replace(',', '.')) if suffix else float(number.replace('.', '').replace(',', ''))
        return int(number * {'mil': 1000, 'k': 1000, 'mi': 1000000, 'm': 1000000, None: 1}[suffix])
    except ValueError:
        return None


def tokens(title):
    return frozenset(re.findall(r'\w+', normalize(title))) - STOP


def similar(a, b):
    a, b = tokens(a), tokens(b)
    # Conservador: mesmas palavras significativas, só muda ordem/acentuação.
    # Nunca fundir por compartilhar apenas pessoa, geografia ou manchete.
    return len(a) >= 2 and a == b


def parse(raw, now=None):
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(raw)
    items = root.findall('./channel/item')
    if not items:
        raise ValueError('RSS sem itens')
    topics, seen = [], set()
    for item in items:
        title = clean(item.findtext('title'))
        headlines = ' '.join(clean(n.findtext('ht:news_item_title', namespaces=NS)) for n in item.findall('ht:news_item', NS))
        if not title or UNRELATED.search(normalize(title)) or not POLITICS.search(normalize(title + ' ' + headlines)):
            continue
        if normalize(title) in seen:
            continue
        try:
            published = parsedate_to_datetime(item.findtext('pubDate') or '')
            if published.tzinfo is None or not now - timedelta(hours=48) <= published <= now + timedelta(minutes=10):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        seen.add(normalize(title))
        traffic = clean(item.findtext('ht:approx_traffic', namespaces=NS))
        topics.append({'title': title.replace('*', '').replace('`', '').replace('@', '＠'), 'traffic': traffic,
                       'value': traffic_value(traffic), 'published': published.isoformat()})
    return sorted(topics, key=lambda t: (-(t['value'] or 0), -datetime.fromisoformat(t['published']).timestamp(), normalize(t['title'])))


def parse_trending(raw, now=None):
    """Dados públicos renderizados pela página Em alta; categoria14=Política."""
    now = now or datetime.now(timezone.utc)
    text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    match = re.search(r"AF_initDataCallback\(\{key: 'ds:0'.*?data:", text)
    if not match:
        raise ValueError('Google Trends: estrutura pública ausente')
    data, _ = json.JSONDecoder().raw_decode(text[match.end():])
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        raise ValueError('Google Trends: dados inválidos')
    topics = []
    for row in data[1]:
        if not isinstance(row, list) or len(row) < 11:
            raise ValueError('Google Trends: formato de tópico mudou')
        if row[2] != 'BR' or 14 not in (row[10] or []):
            continue
        if not isinstance(row[6], (int, float)) or not isinstance(row[9], list):
            raise ValueError('Google Trends: estimativa ou termos inválidos')
        published = datetime.fromtimestamp(row[3][0], timezone.utc)
        if not now - timedelta(hours=24) <= published <= now + timedelta(minutes=10):
            continue
        title = clean(row[0]).replace('*', '').replace('`', '').replace('@', '＠')
        terms = list(dict.fromkeys(clean(t).replace('*', '').replace('`', '').replace('@', '＠') for t in [row[0], *row[9]] if isinstance(t, str) and clean(t)))
        topics.append(dict(title=title, value=row[6], traffic=f'{row[6]:,}+'.replace(',', '.'),
                           published=published.isoformat(), terms=terms, active=row[4] is None))
    if not topics:
        raise ValueError('Google Trends: nenhum tópico político; não substituir por RSS reduzido')
    return sorted(topics, key=lambda t: (-t['value'], -datetime.fromisoformat(t['published']).timestamp(), normalize(t['title'])))


def fetch():
    req = urllib.request.Request(TRENDS_URL, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'pt-BR,pt;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError('Google Trends excede limite')
    return parse_trending(raw)


def group(topics):
    if topics and 'terms' in topics[0]:
        return [[t] for t in topics[:10]]
    groups = []
    for topic in topics:
        target = next((g for g in groups if similar(g[0]['title'], topic['title'])), None)
        if target is None:
            groups.append([topic])
        else:
            target.append(topic)
    return groups[:10]


def fingerprint(topics):
    content = [[(t['title'], t['traffic'], t.get('terms', [])) for t in g] for g in group(topics)]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


def render(topics, previous=None, now=None, analysis=None):
    now = now or datetime.now(timezone.utc)
    if topics and 'terms' in topics[0]:
        return render_trending(topics, previous, now, analysis=analysis)
    groups = group(topics)
    old = group(previous['topics']) if previous else []
    stamp = now.astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
    header = f'🏛️ *Política nas buscas — Brasil · Top {len(groups)}*\nColeta: {stamp}'
    if previous:
        before = datetime.fromisoformat(previous['at']).astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
        header += f'\nComparação com: {before}'
    else:
        header += '\nPrimeira observação: sem base anterior.'
    blocks = []
    for rank, members in enumerate(groups, 1):
        names = {normalize(t['title']) for t in members}
        prior = next(((i, g) for i, g in enumerate(old, 1) if names & {normalize(t['title']) for t in g}), None)
        change = 'sem base anterior' if not previous else '🆕 entrou no recorte'
        if prior:
            delta = prior[0] - rank
            change = f'↑ subiu {delta} posição(ões)' if delta > 0 else f'↓ caiu {-delta} posição(ões)' if delta < 0 else '→ mesma posição'
        lines = [f'{rank}. *{members[0]["title"]}* · {change}', 'Termos agrupados:' if len(members) > 1 else 'Termo:']
        for term in members:
            line = f'• “{term["title"]}” — {term["traffic"] or "estimativa indisponível"}'
            base = next((t for g in old for t in g if normalize(t['title']) == normalize(term['title'])), None)
            if base:
                line += f' (antes: {base["traffic"] or "indisponível"})'
            lines.append(line)
        blocks.append('\n'.join(lines))
    footer = ('📌 Ranking pela maior estimativa individual de cada grupo; desempate por recência e termo. '
              'Estimativas não são somadas. Setas indicam posição, não crescimento das buscas; faixas iguais não comprovam estabilidade. '
              'Entrar/sair do RSS não comprova alta/queda. Recorte político por termos e contexto das notícias; buscas não indicam apoio ou voto.\nFonte: ' + URL)
    # Páginas sem cortar nenhum termo e abaixo do limite do sender Discord.
    pages, current = [], header
    for block in blocks:
        if len(block) > 3000:
            raise ValueError('Grupo excede limite; nenhum termo será omitido')
        if len(current) + len(block) + 2 > 3200:
            pages.append(current)
            current = header
        current += '\n\n' + block
    if len(current) + len(footer) + 2 > 3900:
        pages.append(current)
        current = header
    pages.append(current + '\n\n' + footer)
    return [{'title': 'Política nas buscas', 'alert_title': 'Política nas buscas — Top 10 Brasil', 'url': URL,
             'published': now.isoformat(), 'message': p + (f'\nPágina {i}/{len(pages)}' if len(pages) > 1 else ''),
             'whatsapp_message': p + (f'\nPágina {i}/{len(pages)}' if len(pages) > 1 else ''),
             'footer': 'RSS público Google Trends · estimativas por termo'} for i, p in enumerate(pages, 1)]


def render_trending(topics, previous, now, analysis=None):
    current = topics[:10]
    old = previous['topics'][:10] if previous else []
    local = lambda value: datetime.fromisoformat(value).astimezone(ZoneInfo('America/Fortaleza')).strftime('%d/%m às %H:%M')
    header = f"🏛️ *Política nas buscas — Top {len(current)} Brasil*\nColeta: {local(now.isoformat())} · janela: últimas24h"
    header += f"\nComparação com: {local(previous['at'])}" if previous else '\nPrimeira coleta desta fonte: sem base anterior.'
    footer = ('📌 Fonte: Google Trends Em alta · categoria Política. Agrupamentos fornecidos pelo Google; todos os termos listados. '
              'Estimativa pertence ao grupo, não a cada variante; valores não são somados. Setas comparam posição entre coletas, '
              'não volume. Faixas iguais não comprovam estabilidade; entrada/saída não comprova alta/queda. '
              'Consultas podem conter alegações: não confirmam sua veracidade, apoio ou voto.\n' + TRENDS_URL)
    from tendencias_bq.analise_ia import summary_block
    summary = summary_block(analysis)
    if summary:
        header += '\n\n' + summary
    blocks = []
    discord = [header]
    for rank, topic in enumerate(current, 1):
        prior = next(((i, t) for i, t in enumerate(old, 1) if normalize(t['title']) == normalize(topic['title'])), None)
        move = 'sem base anterior' if not previous else '🆕 entrou no Top10'
        if prior:
            delta = prior[0] - rank
            move = f'↑ subiu {delta} posição(ões)' if delta > 0 else f'↓ caiu {-delta} posição(ões)' if delta < 0 else '→ mesma posição'
        base = f" · antes: {prior[1]['traffic']}" if prior else ''
        label = f"{rank}. *{topic['title']}* · {move}\nEstimativa do grupo: {topic['traffic']}{base}\nExemplos de termos agrupados:"
        examples, seen_examples = [], set()
        for term in topic['terms']:
            if normalize(term) not in seen_examples:
                examples.append(term)
                seen_examples.add(normalize(term))
            if len(examples) == 5:
                break
        block = label + ''.join(f'\n• “{term}”' for term in examples)
        remaining = len(topic['terms']) - len(examples)
        if remaining:
            block += f'\n+ {remaining} outras variantes no Google.'
        blocks.append(block)
        discord.append(f"{rank}. {topic['title']} — {topic['traffic']} · {move}")
    footer = ('📌 Google Trends Em alta · Política · últimas24h. Até5termos de exemplo por tópico. '
              'Estimativa do grupo; valores não somados. Setas comparam posição, não volume. '
              'Consultas não confirmam alegações, apoio ou voto.\n' + TRENDS_URL)
    full = header + '\n\n' + '\n\n'.join(blocks) + '\n\n' + footer
    return [dict(title='Política nas buscas', alert_title='Política nas buscas — Top10 Brasil', url=TRENDS_URL,
                 published=now.isoformat(), message='\n\n'.join(discord)[:3900],
                 whatsapp_message=full, whatsapp_presentation='politics',
                 footer='Google Trends · Política · imagem acessível')]



def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(path)


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--state', default='state.json')
    args = parser.parse_args(argv)
    topics = fetch()
    now = datetime.now(timezone.utc)
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {'sent': []}
    history = state.get(KEY, {})
    previous = history.get('observed') or state.get('politica_trending_v2', {}).get('observed')
    if previous and now - datetime.fromisoformat(previous['at']) > timedelta(hours=48):
        previous = None
    if not topics:
        if not args.dry_run and not args.test:
            history['observed'] = {'at': now.isoformat(), 'topics': []}
            state[KEY] = history
            save(path, state)
        print('RSS válido sem assuntos políticos elegíveis; sem envio.')
        return
    reports = render(topics, previous, now)
    if args.dry_run:
        print('\n\n'.join(r['message'] for r in reports))
        return
    key = fingerprint(topics)
    if not args.test and history.get('delivered') == key:
        history['observed'] = {'at': now.isoformat(), 'topics': topics}
        state[KEY] = history
        save(path, state)
        print('Ranking e estimativas inalterados; sem envio.')
        return
    webhook = os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
    if not webhook or not os.environ.get('WHATSAPP_TOPIC', '').strip():
        raise RuntimeError('Destinos Discord/WhatsApp não configurados')
    # Dry-run/test não chamam IA. Live usa Vertex existente, cache e teto compartilhados.
    if not args.test and topics and 'terms' in topics[0]:
        from tendencias_bq.analise_ia import analyze
        analysis = analyze(topics, kind='politica', batch_id=key,
                           previous_rows=previous['topics'] if previous else (),
                           previous_batch_id=fingerprint(previous['topics']) if previous else None,
                           state=state, persist=lambda: save(path, state))
        reports = render(topics, previous, now, analysis=analysis)
    confirmed = history.get('pages', []) if history.get('pending') == key else []
    for index, report in enumerate(reports):
        if not args.test and index in confirmed:
            continue
        send_discord(webhook, report, 'Google Trends RSS', test=args.test)
        if not args.test:
            confirmed.append(index)
            history.update(pending=key, pages=confirmed)
            state[KEY] = history
            save(path, state)
    if not args.test:
        history.update(delivered=key, observed={'at': now.isoformat(), 'topics': topics})
        history.pop('pending', None)
        history.pop('pages', None)
        state[KEY] = history
        save(path, state)
    print('Ranking publicado com confirmação; teste sem alteração de estado.' if args.test else 'Ranking publicado; estado preservado.')


if __name__ == '__main__':
    run()
