import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from argparse import Namespace

from tendencias_busca.clusters import collect, render, execute
from tendencias_busca.estados import ESTADOS
from tendencias_busca.google.serpapi import parse_response, compare_batch
from tendencias_busca.google.coleta import SourceUnavailable
from main import load_catalog, scheduled_entries

CONFIG = {'terms': list('ABCDEFGHIJKLMNOPQRST'), 'source_modified': '2026-10-16', 'clusters': [
    {'id': code, 'terms': terms} for code, terms in zip(
        ['1A','1B','2A','2B','2C','3A','3B','3C','3D'],
        [['A'],list('BCD'),['E'],['F'],list('GHI'),list('JK'),list('LMN'),list('OPQR'),list('ST')]) ]}


class ClusterTests(unittest.TestCase):
    def test_catalog_keeps_old_trends_and_adds_hourly_bq_alert(self):
        catalog = load_catalog()
        self.assertNotIn('noticias_mei', [entry['id'] for entry in catalog])
        entries = [e for e in catalog if e['ativo']]
        
    def test_catalog_daily_trends_hourly_news(self):
        entries = [
            {'id': 'pesquisa_presidente', 'ativo': True},
            {'id': 'escala_6x1', 'ativo': True},
            {'id': 'tendencias_por_estado', 'ativo': True, 'agenda': {
                'intervalo_horas': 24,
                'fim_exclusivo': '2026-10-25T00:00:00-03:00',
            }},
        ]
        for hour in range(24):
            selected = [e['id'] for e in scheduled_entries(entries, datetime.fromisoformat(f'2026-10-20T{hour:02d}:07:00-03:00'))]
            self.assertIn('pesquisa_presidente', selected)
            self.assertIn('escala_6x1', selected)
            self.assertEqual('tendencias_por_estado' in selected, hour == 0)
            self.assertIn('gtrends_em_alta_brasil', selected)
            self.assertNotIn('noticias_mei', selected)

    def test_catalog_keeps_serpapi_disabled_and_news_active(self):
        catalog = load_catalog()
        trends = next(e for e in catalog if e['id'] == 'tendencias_por_estado')
        self.assertFalse(trends['ativo'])
        entries = [e for e in catalog if e['ativo']]
        for hour in range(24):
            with self.subTest(hour=hour):
                now = datetime.fromisoformat(f'2026-10-20T{hour:02d}:07:00-03:00')
                selected = {e['id'] for e in scheduled_entries(entries, now)}
                self.assertNotIn('tendencias_por_estado', selected)
                self.assertIn('pesquisa_presidente', selected)
                self.assertIn('escala_6x1', selected)

    def test_nine_isolated_clusters_and_cache_on_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, path = {}, Path(tmp)/'state.json'
            with patch.dict('os.environ', {'SERPAPI_API_KEY': 'key'}), patch('tendencias_busca.clusters.compare_batch', side_effect=lambda terms,key:{'MG':dict.fromkeys(terms,10)}) as query:
                first = collect(CONFIG, state, path)
                collect(CONFIG, state, path)
                self.assertEqual(query.call_count, 9)
                self.assertEqual(query.call_args_list[0].args[0], ['A'])
                self.assertEqual(query.call_args_list[2].args[0], ['E'])
                self.assertEqual(len(first['parts']),9)

    def test_failure_not_retried_even_after_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            with patch.dict('os.environ', {'SERPAPI_API_KEY': 'key'}), patch('tendencias_busca.clusters.compare_batch', side_effect=SourceUnavailable('429')) as query:
                with self.assertRaises(SourceUnavailable):
                    collect(CONFIG, {}, path)
                with self.assertRaises(SourceUnavailable):
                    collect(CONFIG, json.loads(path.read_text()), path)
                query.assert_called_once()

    def test_single_term_uses_geo_map_zero(self):
        from urllib.parse import parse_qs, urlparse
        data = {'search_metadata':{'status':'Success'}, 'interest_by_region':[{'geo':'BR-MG','extracted_value':87}]}
        with patch('urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
            self.assertEqual(compare_batch(['A'], 'key'), {'MG':{'A':87}})
            query = parse_qs(urlparse(request.call_args.args[0].full_url).query)
            self.assertEqual(query['data_type'], ['GEO_MAP_0'])

    def test_missing_regions_and_zero_not_fabricated(self):
        data = {'search_metadata':{'status':'Success'}, 'interest_by_region':[]}
        self.assertEqual(parse_response(data,['A']), {})
        data['interest_by_region'] = [{'geo':'BR-MG','extracted_value':0}]
        self.assertEqual(parse_response(data,['A']), {'MG':{'A':0}})

    def test_full_table_contains_every_term_without_cross_cluster_ranking(self):
        general={uf:['x'] for uf in ESTADOS}
        monitored={uf:{c['id']:dict.fromkeys(c['terms'],100) for c in CONFIG['clusters']} for uf in ESTADOS}
        result=render(general,monitored,CONFIG,'date')
        self.assertEqual(len(result),2)
        self.assertLessEqual(len(result[1]['message']),2800)
        self.assertLessEqual(len(result[1]['details_message']),2800)
        for cluster in CONFIG['clusters']:
            self.assertIn(cluster['id'] + ':', result[1]['details_message'])

    def test_daily_delivery_and_no_recharge_after_send_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=Namespace(state=str(Path(tmp)/'state.json'),dry_run=False,test=False)
            with patch.dict('os.environ',{'SERPAPI_API_KEY':'key'}), patch('tendencias_busca.clusters.compare_batch',side_effect=lambda terms,key:{'MG':dict.fromkeys(terms,10)}) as api, patch('tendencias_busca.clusters.trending',return_value=['x']), patch('tendencias_busca.clusters.send_discord',side_effect=[{'id':'1'},RuntimeError('fail')]):
                with self.assertRaises(RuntimeError):
                    execute(args,CONFIG,['MG'],'hook')
                self.assertEqual(api.call_count,9)
            with patch.dict('os.environ',{'SERPAPI_API_KEY':'key'}), patch('tendencias_busca.clusters.compare_batch') as api, patch('tendencias_busca.clusters.trending',return_value=['x']), patch('tendencias_busca.clusters.send_discord',return_value={'id':'2'}) as send:
                execute(args,CONFIG,['MG'],'hook')
                execute(args,CONFIG,['MG'],'hook')
                api.assert_not_called()
                send.assert_called_once()
