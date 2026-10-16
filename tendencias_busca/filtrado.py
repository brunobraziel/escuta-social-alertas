"""Execução de duas mensagens independentes, sem consultas pagas."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from core.alerta import send_discord
from tendencias_busca.cache import save_state
from tendencias_busca.filtro import filter_topics, reports
from tendencias_busca.google.coleta import trending, SourceUnavailable


def execute(args, config, states, webhook):
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {'sent': []}
    with ThreadPoolExecutor(max_workers=3) as pool:
        general = dict(zip(states, pool.map(trending, states)))
    if not any(general.values()):
        raise SourceUnavailable('Feeds sem assuntos recentes; nenhum envio')
    filtered = filter_topics(general, config)
    now = datetime.now(timezone.utc).isoformat()
    messages = reports(general, filtered, config, now)
    cached = {'schema_version': 1, 'origin': 'rss_filtrado', 'collected_at': now,
              'monitored_at': now, 'source_version': config['source_modified'],
              'terms_count': len(config['terms']), 'general': general, 'monitored': filtered,
              'reports': messages, 'report': dict(messages[0], details_message=messages[1]['message']),
              'delivery': [], 'source_tab': config.get('source_tab')}
    if args.dry_run:
        print(json.dumps(cached, ensure_ascii=False))
        return
    state['trends_last_snapshot'] = cached
    save_state(path, state)
    for kind, report in zip(('general', 'filtered'), messages):
        # Só conteúdo visível, sem timestamps ou versão: novidade independente.
        body = '\n'.join(line for line in report['message'].splitlines() if not line.startswith(("20 termos", str(len(config['terms'])) + ' termos')))
        key = hashlib.sha256(body.encode()).hexdigest()
        field = 'trends_rss_latest_' + kind
        if not args.test and state.get(field) == key:
            continue
        delivered = send_discord(webhook, report, 'Google Trends (RSS)', test=args.test)
        cached['delivery'].append({'kind': kind, 'message': delivered, 'test': args.test})
        if not args.test:
            state[field] = key
        confirmed = state.setdefault('trends_rss_delivered', {})
        confirmed[kind] = report
        confirmed_snapshot = json.loads(json.dumps(cached))
        confirmed_snapshot['reports'] = [confirmed[k] for k in ('general', 'filtered') if k in confirmed]
        state['trends_last_delivered_snapshot'] = confirmed_snapshot
        save_state(path, state)
    print(f"RSS: {len(states)} UFs; {sum(bool(r) for r in filtered.values())} com correspondências; zero consultas SerpApi.")
