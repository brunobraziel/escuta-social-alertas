"""Consulta diária dos clusters independentes, com limite antes de cada pedido."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from core.alerta import send_discord
from tendencias_busca.cache import save_state
from tendencias_busca.filtro import reports as rss_reports
from tendencias_busca.google.coleta import trending, SourceUnavailable
from tendencias_busca.google.serpapi import compare_batch
from tendencias_busca.janela import now_local


def collect(config, state, path, dry_run=False):
    key = os.environ.get('SERPAPI_API_KEY', '').strip()
    if not key:
        raise SourceUnavailable('Configure SERPAPI_API_KEY')
    signature = hashlib.sha256(json.dumps(config['clusters'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    day = now_local().date().isoformat()
    daily = state.get('trends_clusters_day')
    if daily and daily['day'] == day:
        if daily['signature'] != signature:
            raise SourceUnavailable('Configuração mudou após coleta de hoje; use cache ou aguarde amanhã')
    else:
        daily = {'day': day, 'signature': signature, 'attempted': [], 'parts': {}, 'collected_at': None}
        if not dry_run:
            state['trends_clusters_day'] = daily
    for cluster in config['clusters']:
        code = cluster['id']
        if code in daily['parts']:
            continue
        if code in daily['attempted']:
            raise SourceUnavailable('Cluster já tentado hoje e sem resultado; sem novas consultas')
        daily['attempted'].append(code)
        if not dry_run:
            save_state(path, state)
        # A tentativa é persistida antes da API; falhas não consomem novamente.
        daily['parts'][code] = compare_batch(cluster['terms'], key)
        if not dry_run:
            save_state(path, state)
    if not daily['collected_at']:
        daily['collected_at'] = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        save_state(path, state)
    return daily


def render(general, monitored, config, now):
    first = rss_reports(general, {uf: [] for uf in general}, config, now)[0]
    legend = ['**Escuta Social — todos os termos por UF**', 'Valores na ordem dos termos de cada cluster:']
    from tendencias_busca.resumo import short
    for cluster in config['clusters']:
        legend.append(f"**{cluster['id']}:** " + ' / '.join(short(t, 80) for t in cluster['terms']))
    legend += ['', '1A, 2A, 2B: índice geográfico (0–100). Demais: participação relativa (%) dentro do cluster na UF.', 'n/d = dado indisponível; 0 = abaixo da resolução. Sem volume absoluto ou comparação entre clusters.', '']
    lines = []
    for uf in general:
        cells = []
        for cluster in config['clusters']:
            values = monitored[uf][cluster['id']]
            numbers = '/'.join(f'{values[t]:g}' for t in cluster['terms']) if values else 'n/d'
            cells.append(f"{cluster['id']}:{numbers}")
        lines.append(f"**{uf}:** " + ' · '.join(cells))
    body = '\n'.join(legend + lines[:12])
    details = '\n'.join(lines[12:]) or 'Fim do resumo.'
    if max(len(body), len(details)) > 2800:
        raise ValueError('Tabela excede limite; revise tamanho da configuração')
    second = dict(first, alert_title='Escuta Social diária — grupos 1, 2 e 3', message=body, details_message=details,
                  footer='Google Trends · últimas 24h · todos os termos consultados em clusters independentes. Não mede intenção de voto. Valores podem ser arredondados.')
    return [first, second]


def execute(args, config, states, webhook):
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {'sent': []}
    daily = collect(config, state, path, args.dry_run)
    monitored = {uf: {c['id']: daily['parts'][c['id']].get(uf) for c in config['clusters']} for uf in states}
    if not any(v for clusters in monitored.values() for v in clusters.values()):
        raise SourceUnavailable('Nenhuma UF com dados disponíveis; sem enviar comparação')
    with ThreadPoolExecutor(max_workers=3) as pool:
        general = dict(zip(states, pool.map(trending, states)))
    messages = render(general, monitored, config, daily['collected_at'])
    cached = {'schema_version': 1, 'origin': 'serpapi_clusters_daily', 'collected_at': datetime.now(timezone.utc).isoformat(),
              'monitored_at': daily['collected_at'], 'source_version': config['source_modified'], 'terms_count': len(config['terms']),
              'general': general, 'monitored': monitored, 'reports': messages,
              'report': messages[0], 'delivery': [], 'clusters': config['clusters']}
    if args.dry_run:
        print(json.dumps(cached, ensure_ascii=False))
        return
    state['trends_last_snapshot'] = cached
    save_state(path, state)
    for kind, report in zip(('general', 'clusters'), messages):
        content = report['message'] + report.get('details_message', '')
        fingerprint = hashlib.sha256(content.encode()).hexdigest()
        field = 'trends_daily_latest_' + kind
        delivery_field = 'trends_daily_sent_' + kind
        if not args.test and (state.get(delivery_field) == daily['day'] or state.get(field) == fingerprint):
            continue
        delivered = send_discord(webhook, report, 'Google Trends', test=args.test)
        cached['delivery'].append({'kind': kind, 'message': delivered, 'test': args.test})
        if not args.test:
            state[field] = fingerprint
            state[delivery_field] = daily['day']
        confirmed = state.setdefault('trends_daily_delivered', {})
        confirmed[kind] = report
        saved = json.loads(json.dumps(cached))
        saved['reports'] = [confirmed[k] for k in ('general', 'clusters') if k in confirmed]
        state['trends_last_delivered_snapshot'] = saved
        save_state(path, state)
    print(f"Coleta diária: {len(config['clusters'])} clusters; {len(states)} UFs; cache preservado; sem nova consulta de cluster já tentado hoje.")
