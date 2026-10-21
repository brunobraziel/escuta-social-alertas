import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from tendencias_bq.bigquery import fetch_latest_ingestion
from tendencias_bq.monitoramento_temas import render, run


class MonitoramentoTemasTests(unittest.TestCase):
    def test_reads_complete_batch_with_distinct_row_timestamps(self):
        stamp = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)
        rows = [dict(ingestao_id="batch", hora_ingestao=stamp + timedelta(microseconds=n), consulta=f"q{n}") for n in range(3)]
        client = Mock()
        client.query.return_value.result.return_value = rows
        with patch("tendencias_bq.bigquery._client", return_value=client):
            result = fetch_latest_ingestion("gtrends_monitoramento_temas")
        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["hora_ingestao"], rows[-1]["hora_ingestao"])
        sql = client.query.call_args.args[0]
        self.assertIn("WHERE ingestao_id = (SELECT ingestao_id FROM latest)", sql)
        self.assertNotIn("ORDER BY uf", sql)

    def test_national_topics_do_not_invent_states_or_mix_metrics(self):
        rows = [dict(macrotema="Saúde", termo_base="sus", geo_busca="BR", consulta="consulta A", lista="top", posicao=1),
                dict(macrotema="Saúde", termo_base="sus", geo_busca="BR", consulta="consulta A", lista="em alta", posicao=2),
                dict(macrotema="Saúde", termo_base="sus", geo_busca="BR", consulta="consulta B", lista="em alta", posicao=1)]
        report = render(rows, datetime.now(timezone.utc))
        text = report["whatsapp_message"]
        self.assertIn("Brasil", text)
        self.assertIn("*Saúde*", text)
        self.assertEqual(text.count("*consulta A*"), 1)
        self.assertLess(text.index("1. *consulta B*"), text.index("2. *consulta A*"))
        self.assertNotIn("por estado", text)
        self.assertNotIn("vol.", text)

    def test_peak_day_all_23_groups_fit_and_whatsapp_preserves_topics(self):
        rows = [dict(macrotema=f"Tema {n}", termo_base="termo base", geo_busca="BR", consulta=f"Consulta {n}-{i}", lista="em alta", posicao=i) for n in range(23) for i in range(1, 5)]
        report = render(rows, datetime.now(timezone.utc))
        self.assertLessEqual(len(report["message"]), 2700)
        self.assertLessEqual(len(report["details_message"]), 2700)
        self.assertEqual(sum(report["whatsapp_message"].count(f"{n}. *Consulta") for n in range(1,5)), 92)

    def test_runner_queries_new_table_and_uses_new_state_namespace(self):
        with patch("tendencias_bq.monitoramento_temas.run_alert") as runner:
            run(["--dry-run"])
        self.assertEqual(runner.call_args.kwargs["table_id"], "gtrends_monitoramento_temas")
        self.assertEqual(runner.call_args.kwargs["alert_id"], "gtrends_monitoramento_temas")
