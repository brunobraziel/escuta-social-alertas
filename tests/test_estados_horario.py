import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from tendencias_bq import bigquery
from tendencias_bq.estados import render, run
from tendencias_bq.em_alta_brasil import STATE_NAMES


class StateHourlyTests(unittest.TestCase):
    def test_reads_full_region_batch_not_city_batch_or_last_row(self):
        stamp = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)
        rows = [dict(ingestao_id="region-batch", hora_ingestao=stamp + timedelta(microseconds=i), uf="CE") for i in range(3)]
        client = Mock()
        client.query.return_value.result.return_value = rows
        with patch("tendencias_bq.bigquery._client", return_value=client):
            actual = bigquery.fetch_latest_ingestion("gtrends_monitoramento_cidades")
        self.assertEqual(actual["rows"], rows)
        sql = client.query.call_args.args[0]
        self.assertEqual(sql.count("resolucao = 'REGION'"), 2)
        self.assertEqual(sql.count("job = 'estados'"), 2)
        self.assertIn("WHERE ingestao_id = (SELECT ingestao_id FROM latest)", sql)

    def test_groups_states_deduplicates_and_excludes_anchor_and_invalid_values(self):
        rows = [dict(uf="CE", termo=t, indice_vs_ancora=i, eh_ancora=a) for t,i,a in
                [("SUS",50,False),("sus",40,False),("Referência",100,True),("Sem índice",None,False),("Zero",0,False)]]
        report = render(rows, datetime(2026, 10, 20, 14, tzinfo=timezone.utc))
        text = report["whatsapp_message"]
        self.assertIn("📍 *Ceará (CE)*\n• *SUS*", text)
        self.assertEqual(text.count("• *SUS*"), 1)
        self.assertNotIn("• *Referência*", text)
        self.assertNotIn("• *Zero*", text)
        self.assertIn("20/10 às 11:00", text)
        self.assertEqual(text.count("📍 *"), 28) # title plus 27 states
        self.assertIn("Sem índice válido disponível neste lote", text)

    def test_all_states_and_long_topics_fit_discord_and_keep_whatsapp_blocks(self):
        rows = [dict(uf=uf, termo=f"Termo de busca bastante longo numero {i}", indice_vs_ancora=10+i, eh_ancora=False) for uf in STATE_NAMES for i in range(4)]
        report = render(rows, datetime.now(timezone.utc))
        self.assertLessEqual(len(report["message"]),2700)
        self.assertLessEqual(len(report["details_message"]),2700)
        self.assertEqual(report["whatsapp_message"].count("• *"),108)

    def test_same_batch_repeats_next_hour_but_not_within_same_hour(self):
        class Clock(datetime):
            current = datetime(2026,10,20,15,tzinfo=timezone.utc)
            @classmethod
            def now(cls, tz=None):
                return cls.current
        latest = {"rows":[dict(uf="CE",termo="SUS",indice_vs_ancora=50,eh_ancora=False)],
                  "hora_ingestao":datetime(2026,10,20,14,tzinfo=timezone.utc),"ingestao_id":"batch"}
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ",{"DISCORD_WEBHOOK_URL":"hook"}), \
             patch("tendencias_bq.em_alta_brasil.fetch_latest_ingestion",return_value=latest), \
             patch("tendencias_bq.em_alta_brasil.datetime",Clock), \
             patch("tendencias_bq.estados.fetch_previous_state_ingestion", return_value={"rows":[],"hora_ingestao":None}), \
             patch("tendencias_bq.em_alta_brasil.send_discord",return_value={"id":"message"}) as send:
            args=["--state",str(Path(temp)/"state.json")]
            run(args); run(args)
            self.assertEqual(send.call_count,1)
            Clock.current += timedelta(hours=1)
            run(args)
            self.assertEqual(send.call_count,2)


class MovementTests(unittest.TestCase):
    def row(self, value, **extra):
        return dict(uf="CE",termo="SUS",grupo="SAUDE",periodo="now 7-d",indice_vs_ancora=value,eh_ancora=False,**extra)

    def test_increase_decrease_and_flat_are_index_changes(self):
        from tendencias_bq.estados import movement, comparison_key
        previous = {comparison_key(self.row(20)):self.row(20)}
        self.assertEqual(movement(self.row(25),previous),'↑ (+25,0%)')
        self.assertEqual(movement(self.row(15),previous),'↓ (-25,0%)')
        self.assertEqual(movement(self.row(20),previous),'→ (0,0%)')

    def test_missing_zero_and_wrong_state_group_period_do_not_invent_percent(self):
        from tendencias_bq.estados import movement, comparison_key
        current = self.row(25)
        self.assertIn('sem base',movement(current,{}))
        self.assertIn('base zero',movement(current,{comparison_key(current):self.row(0)}))
        for field,value in [('uf','SP'),('grupo','OUTRO'),('periodo','now 1-d')]:
            previous = self.row(20);previous[field]=value
            self.assertIn('sem base',movement(current,{comparison_key(previous):previous}))

    def test_render_compares_against_full_previous_batch_not_only_old_top_four(self):
        current=self.row(25);previous=self.row(20)
        now=datetime(2026,10,21,14,tzinfo=timezone.utc)
        report=render([current],now,previous_rows=[previous],previous_ingestion_time=now-timedelta(hours=3))
        self.assertIn('• *SUS* ↑ (+25,0%)',report['whatsapp_message'])
        self.assertIn('21/10 às 08:00',report['whatsapp_message'])
        self.assertIn('não da quantidade absoluta',report['whatsapp_message'])
        self.assertIn('↑ (+25,0%)',report['message']+report['details_message'])

    def test_reader_selects_previous_batch_with_parameters_and_region_only(self):
        stamp=datetime(2026,10,21,14,tzinfo=timezone.utc)
        client=Mock(); client.query.return_value.result.return_value=[dict(ingestao_id='old',hora_ingestao=stamp-timedelta(hours=3))]
        with patch('tendencias_bq.bigquery._client',return_value=client):
            result=bigquery.fetch_previous_state_ingestion({'ingestao_id':'new','hora_ingestao':stamp})
        self.assertEqual(result['ingestao_id'],'old')
        sql=client.query.call_args.args[0]
        self.assertIn('MAX(hora_ingestao) < @current_time',sql)
        self.assertIn("resolucao = 'REGION'",sql)
        self.assertIn('ingestao_id != @current_id',sql)
        self.assertEqual(client.query.call_args.kwargs['job_config'].query_parameters[0].value,'new')


class LargeMovementMessageTests(unittest.TestCase):
    def test_all_states_with_zero_baseline_fit_without_omitting_topics(self):
        rows=[dict(uf=uf,termo=f'Termo de busca bastante longo numero {i}',indice_vs_ancora=10+i,eh_ancora=False,grupo='a',periodo='now 7-d') for uf in STATE_NAMES for i in range(4)]
        now=datetime.now(timezone.utc)
        report=render(rows,now,previous_rows=[dict(r,indice_vs_ancora=0) for r in rows],previous_ingestion_time=now-timedelta(hours=3))
        self.assertEqual(report['whatsapp_message'].count('base zero; sem %'),108)
        self.assertLessEqual(len(report['message']),2700)
        self.assertLessEqual(len(report['details_message']),2700)
