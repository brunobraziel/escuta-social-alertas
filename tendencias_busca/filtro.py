"""Correspondência textual nos assuntos em alta; não estima interesse ou volume."""
import re
import unicodedata


def normalized(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


def filter_topics(general, config):
    result = {}
    for uf, topics in general.items():
        result[uf] = []
        for topic in topics:
            matches = []
            for cluster in config['clusters']:
                for term in cluster['terms']:
                    pattern = r'(?<!\w)' + re.escape(normalized(term)) + r'(?!\w)'
                    if re.search(pattern, normalized(topic)):
                        matches.append({'cluster': cluster['id'], 'term': term})
            if matches:
                result[uf].append({'topic': topic, 'matches': matches})
    return result


def reports(general, filtered, config, now):
    from tendencias_busca.resumo import short
    base = {'title': 'Google Trends por estado', 'description': '',
            'url': 'https://trends.google.com/trending?geo=BR', 'published': now,
            'footer': 'Feed Google Trends · últimas 24h · ordem do RSS, sem ranking absoluto ou intenção de voto.'}
    first = ['**Assuntos em alta — geral**', 'Até quatro destaques por UF.', '']
    second = ['**Escuta Social — assuntos em alta filtrados**',
              f"20 termos dos grupos 1–3 · versão {config['source_modified'][:10]}" if len(config['terms']) == 20 else f"{len(config['terms'])} termos · versão {config['source_modified'][:10]}",
              'Até quatro correspondências por UF; sem contagem de buscas.', '']
    for uf, topics in general.items():
        first.append(f"**{uf}:** " + (', '.join(short(t, 18) for t in topics[:4]) if topics else 'feed sem assuntos disponíveis'))
        rows = filtered[uf]
        second.append(f"**{uf}:** " + (', '.join(short(r['topic'], 18) for r in rows[:4]) if rows else ('nenhuma correspondência' if topics else 'feed sem assuntos disponíveis')))
    first_report = dict(base, alert_title='Assuntos em alta por estado', message='\n'.join(first))
    second_report = dict(base, alert_title='Escuta Social por estado — grupos 1, 2 e 3', message='\n'.join(second))
    second_report['footer'] = 'Filtro textual sem acentos, com palavras completas. Ausência no feed não significa ausência de buscas. Temas completos e clusters no JSON salvo.'
    if any(len(r['message']) > 2800 for r in (first_report, second_report)):
        raise ValueError('Resumo excede limite de mensagem')
    return [first_report, second_report]
