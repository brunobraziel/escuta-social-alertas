import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tendencias_busca.filtro import filter_topics, reports
from tendencias_busca.filtrado import execute
from tendencias_busca.drive.termos import load_terms
from tendencias_busca.estados import ESTADOS

CONFIG = {'mode': 'filter_trending', 'source_modified': '2026-10-16',
          'source_url': 'https://docs.google.com/document/d/example/edit',
          'terms': ['SUS', 'Posto de Saúde'],
          'clusters': [{'id': '1A', 'terms': ['SUS']}, {'id': '1B', 'terms': ['Posto de Saúde']}]}


class FilterTests(unittest.TestCase):
    def test_accents_boundaries_and_all_matching_clusters(self):
        rows = filter_topics({'MG': ['Jesus', 'suspeito preso', 'POSTO DE SAUDE e SUS', 'quem criou o sus']}, CONFIG)['MG']
        self.assertEqual(len(rows), 2)
        self.assertEqual({m['cluster'] for m in rows[0]['matches']}, {'1A', '1B'})

    def test_config_must_cover_all_terms_and_reject_duplicate_clusters(self):
        bad = dict(CONFIG, clusters=[{'id': '1A', 'terms': ['SUS']}])
        with patch.dict('os.environ', {'ESCUTA_SOCIAL_TERMS_JSON': json.dumps(bad)}):
            with self.assertRaises(ValueError):
                load_terms()

    def test_two_messages_fit_with_27_states_and_four_long_topics(self):
        general = {uf: ['X' * 200] * 4 for uf in ESTADOS}
        filtered = {uf: [{'topic': 'Y' * 200, 'matches': []}] * 4 for uf in ESTADOS}
        result = reports(general, filtered, CONFIG, 'now')
        self.assertEqual(len(result), 2)
        self.assertTrue(all(len(r['message']) <= 2800 for r in result))
        self.assertTrue(all('details_message' not in r for r in result))

    def test_no_paid_requests_and_dedup_independent_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(state=str(Path(tmp) / 'state.json'), dry_run=False, test=False)
            with patch('tendencias_busca.filtrado.trending', return_value=['SUS', 'futebol']), patch('tendencias_busca.filtrado.send_discord', return_value={'id': '1'}) as send, patch('tendencias_busca.google.serpapi.compare_batch') as api:
                execute(args, CONFIG, ['MG'], 'webhook')
                self.assertEqual(send.call_count, 2)
                execute(args, CONFIG, ['MG'], 'webhook')
                self.assertEqual(send.call_count, 2)
                with patch('tendencias_busca.filtrado.trending', return_value=['SUS', 'chuva']):
                    execute(args, CONFIG, ['MG'], 'webhook')
                self.assertEqual(send.call_count, 3)
                api.assert_not_called()

    def test_failure_second_message_preserves_first_and_retries_only_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(state=str(Path(tmp) / 'state.json'), dry_run=False, test=False)
            with patch('tendencias_busca.filtrado.trending', return_value=['SUS']), patch('tendencias_busca.filtrado.send_discord', side_effect=[{'id': '1'}, RuntimeError('fail')]):
                with self.assertRaises(RuntimeError):
                    execute(args, CONFIG, ['MG'], 'webhook')
            state = json.loads(Path(args.state).read_text())
            self.assertEqual(len(state['trends_last_delivered_snapshot']['reports']), 1)
            with patch('tendencias_busca.filtrado.trending', return_value=['SUS']), patch('tendencias_busca.filtrado.send_discord', return_value={'id': '2'}) as send:
                execute(args, CONFIG, ['MG'], 'webhook')
                send.assert_called_once()

    def test_run_routes_to_filter_without_paid_comparison(self):
        from tendencias_busca.run import run
        with patch('tendencias_busca.run.expired', return_value=False), patch('tendencias_busca.run.load_terms', return_value=CONFIG), patch('tendencias_busca.filtrado.execute') as execute_mock, patch('tendencias_busca.run.compare_all') as paid:
            run(['--dry-run', '--states', 'MG'])
            execute_mock.assert_called_once()
            paid.assert_not_called()
