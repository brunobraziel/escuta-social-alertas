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
             patch("tendencias_bq.em_alta_brasil.send_discord",return_value={"id":"message"}) as send:
            args=["--state",str(Path(temp)/"state.json")]
            run(args); run(args)
            self.assertEqual(send.call_count,1)
            Clock.current += timedelta(hours=1)
            run(args)
            self.assertEqual(send.call_count,2)
