import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from tendencias_bq import analise_ia as ai
from tendencias_bq.monitoramento_temas import render
from tendencias_bq.estados import render as render_states
from tendencias_bq.em_alta_brasil import STATE_NAMES


class AnalysisTests(unittest.TestCase):
    def rows(self):
        return [dict(macrotema='Benefícios', termo_base='Bolsa Família', geo_busca='BR',
                     consulta=q, lista='em alta', posicao=n) for n, q in enumerate([
                         'quem criou bolsa família', 'quem foi que criou o bolsa família',
                         'quem aumentou bolsa família', 'como consultar bolsa família',
                         'como cadastrar bolsa família'], 1)]

    def result(self, rows):
        entries = ai.related_entries(rows)
        return dict(observacao='As consultas incluem dúvidas sobre a origem do programa.',
                    interpretacao='Pode haver interesse pela história do benefício.',
                    evidencias=[entries[0]['id']], clusters=[])

    def test_groups_preserve_original_variants_without_changing_meaning(self):
        rows = self.rows()
        entries = ai.related_entries(rows)
        ids = {e['term']: e['id'] for e in entries}
        result = self.result(rows)
        result['clusters'] = [[ids[rows[0]['consulta']], ids[rows[1]['consulta']]]]
        text = render(rows, datetime.now(timezone.utc), analysis=result)['whatsapp_message']
        self.assertIn('Agrupadas: quem foi que criou o bolsa família', text)
        for row in rows:
            self.assertIn(row['consulta'], text)
        self.assertIn('*Leitura dos dados · IA*', text)
        # Mesmo se o modelo pedir, criação e aumento não podem ser fundidos.
        result['clusters'] = [[ids[rows[0]['consulta']], ids[rows[2]['consulta']]]]
        self.assertEqual(len(ai.related_groups(entries, result)), 4)
        self.assertFalse(ai.similar_questions(rows[0]['consulta'], rows[2]['consulta']))

    def test_unknown_duplicate_cross_context_or_conflicting_clusters_never_drop_terms(self):
        rows = self.rows()
        rows.append(dict(rows[0], geo_busca='BR-CE'))
        entries = ai.related_entries(rows)
        for cluster in [[entries[0]['id'], 'inventado'],
                        [entries[0]['id'], entries[0]['id']],
                        [e['id'] for e in entries]]:
            groups = ai.related_groups(entries, {'clusters': [cluster]})
            self.assertEqual(sorted(e['id'] for g in groups for e in g), sorted(e['id'] for e in entries))

    def test_cache_one_call_per_batch_and_budget_reserved_before_request(self):
        rows = self.rows(); state = {}; persist = Mock()
        def generate(payload):
            self.assertEqual(state['trends_ai_reserved_micro_usd'], 20000)
            self.assertTrue(persist.called)
            self.assertLessEqual(len(__import__('json').dumps(payload, ensure_ascii=False).encode()),40000)
            return self.result(rows), {'totalTokenCount': 123}
        with patch.dict('os.environ', {'TRENDS_AI_ENABLED':'true'}), patch.object(ai, '_generate', side_effect=generate) as call:
            for _ in range(2):
                self.assertIsNotNone(ai.analyze(rows, kind='consultas', batch_id='a', state=state, persist=persist))
            self.assertEqual(call.call_count,1)
            self.assertEqual(state['trends_ai_reserved_micro_usd'],20000)

    def test_failure_budget_and_invalid_evidence_fall_back_without_retries(self):
        rows=self.rows()
        with patch.dict('os.environ', {'TRENDS_AI_ENABLED':'true'}), patch.object(ai, '_generate', side_effect=TimeoutError) as call:
            state={}
            for _ in range(2):
                self.assertIsNone(ai.analyze(rows,kind='consultas',batch_id='a',state=state,persist=Mock()))
            self.assertEqual(call.call_count,1)
            state['trends_ai_reserved_micro_usd']=ai.BUDGET_MICRO_USD
            self.assertIsNone(ai.analyze(rows,kind='consultas',batch_id='b',state=state,persist=Mock()))
            self.assertEqual(call.call_count,1)
        result=self.result(rows); result['evidencias']=['inventado']
        with self.assertRaises(ValueError): ai.validate(result,ai.related_entries(rows))

    def test_five_ranked_terms_all_states_and_short_summary_fit_channels(self):
        rows=[dict(uf=uf,termo=f'Termo {i}',indice_vs_ancora=i,eh_ancora=False)
              for uf in STATE_NAMES for i in range(1,8)]
        analysis={'observacao':'a'*450,'interpretacao':'b'*450}
        report=render_states(rows,datetime.now(timezone.utc),analysis=analysis)
        text=report['whatsapp_message']
        self.assertEqual(text.count('5. *'),27)
        self.assertNotIn('*Termo 2*',text)
        self.assertLessEqual(len(report['message']),2700)
        self.assertLessEqual(len(report['details_message']),2700)

    def test_no_ai_calls_without_explicit_enable(self):
        with patch.dict('os.environ', {'TRENDS_AI_ENABLED':''}), patch.object(ai,'_generate') as call:
            self.assertIsNone(ai.analyze(self.rows(),kind='consultas',batch_id='a',state={},persist=Mock()))
            call.assert_not_called()

    def test_expanded_analysis_and_related_source_values(self):
        rows = self.rows()
        rows[0].update(valor='+250%', valor_num=250)
        entries = ai.related_entries(rows)
        entry = next(e for e in entries if e['term'] == rows[0]['consulta'])
        self.assertEqual((entry['list'], entry['value'], entry['numeric_value']),
                         ('em alta', '+250%', 250))
        result = self.result(rows)
        result.update(observacao='a' * 450, interpretacao='b' * 450)
        validated = ai.validate(result, entries)
        report = render(rows, datetime.now(timezone.utc), analysis=validated)
        self.assertIn(result['interpretacao'], report['whatsapp_message'])
        self.assertLessEqual(len(report['message']), 2700)
        result['interpretacao'] += 'x'
        with self.assertRaises(ValueError):
            ai.validate(result, entries)
