import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tendencias_bq import bigquery
from tendencias_bq.em_alta_brasil import render, run


class BigQueryReaderTests(unittest.TestCase):
    def test_fetch_latest_ingestion_selects_max_timestamp_and_one_batch(self):
        stamp = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
        row = {"uf": "SP", "rotulo": "Tema", "hora_ingestao": stamp, "ingestao_id": "batch-1"}
        client = Mock()
        client.query.return_value.result.return_value = [row]
        with patch("tendencias_bq.bigquery._client", return_value=client):
            result = bigquery.fetch_latest_ingestion("gtrends_em_alta_brasil")
        self.assertEqual(result["rows"], [row])
        self.assertEqual(result["hora_ingestao"], stamp)
        self.assertIn("MAX(hora_ingestao)", client.query.call_args.args[0])
        self.assertIn("INTERVAL 1 HOUR", client.query.call_args.args[0])
        self.assertIn("ORDER BY uf, aumento DESC, volume DESC", client.query.call_args.args[0])

    def test_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            bigquery.fetch_latest_ingestion("another_table")

    def test_ambiguous_ingestion_ids_at_latest_timestamp_fail(self):
        stamp = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
        client = Mock()
        client.query.return_value.result.return_value = [
            {"hora_ingestao": stamp, "ingestao_id": "batch-a"},
            {"hora_ingestao": stamp, "ingestao_id": "batch-b"},
        ]
        with patch("tendencias_bq.bigquery._client", return_value=client):
            with self.assertRaises(bigquery.BigQueryUnavailable):
                bigquery.fetch_latest_ingestion("gtrends_em_alta_brasil")


class EmAltaBrasilTests(unittest.TestCase):
    def test_render_groups_by_state_and_limits_topics(self):
        rows = [
            {"uf": "SP", "rotulo": f"Tema {index}", "volume": index, "aumento": index,
             "ativa": index == 5, "candidato": False}
            for index in range(1, 6)
        ]
        report = render(rows, datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc))
        self.assertIn("**SP:**", report["message"])
        self.assertIn("Tema 5", report["message"])
        self.assertNotIn("Tema 1", report["message"])
        self.assertIn("BigQuery", report["footer"])

    def test_whatsapp_has_separate_state_blocks_and_no_metrics(self):
        rows = [
            {"uf": "SP", "rotulo": "Tema paulista", "volume": 2000, "aumento": 1000},
            {"uf": "CE", "rotulo": "Tema cearense", "volume": 100, "aumento": 20},
        ]
        report = render(rows, datetime(2026, 10, 20, 13, 32, tzinfo=timezone.utc))
        text = report["whatsapp_message"]
        self.assertIn("📍 *Ceará (CE)*\n• *Tema cearense*", text)
        self.assertIn("\n\n📍 *São Paulo (SP)*\n• *Tema paulista*", text)
        self.assertIn("20/10 às 10:32", text)
        self.assertNotIn("vol.", text)
        self.assertNotIn("aumento", text)
        self.assertIn("vol. 2000", report["message"])
        self.assertIn("aumento 1000", report["message"])

    def test_whatsapp_keeps_only_the_same_top_four_topics(self):
        rows = [{"uf": "SP", "rotulo": f"Tema {n}", "volume": n, "aumento": n} for n in range(6)]
        report = render(rows, datetime(2026, 10, 20, 13, tzinfo=timezone.utc))
        for n in (2, 3, 4, 5):
            self.assertIn(f"• *Tema {n}*", report["whatsapp_message"])
        for n in (0, 1):
            self.assertNotIn(f"Tema {n}", report["whatsapp_message"])

    def test_run_dry_run_prints_latest_data_without_sending(self):
        stamp = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
        latest = {"rows": [{"uf": "SP", "rotulo": "Tema", "volume": 10, "aumento": 20,
                            "ativa": True, "candidato": False}],
                  "hora_ingestao": stamp, "ingestao_id": "batch-1"}
        with patch("tendencias_bq.em_alta_brasil.fetch_latest_ingestion", return_value=latest), \
             patch("tendencias_bq.em_alta_brasil.send_discord") as send, \
             patch("builtins.print") as output:
            run(["--dry-run"])
        send.assert_not_called()
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["ingestao_id"], "batch-1")
        self.assertEqual(payload["rows"], 1)

    def test_no_ingestion_in_last_hour_does_not_send(self):
        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/token"}), \
             patch("tendencias_bq.em_alta_brasil.fetch_latest_ingestion", return_value={
                 "rows": [], "hora_ingestao": None, "ingestao_id": None}), \
             patch("tendencias_bq.em_alta_brasil.send_discord") as send, \
             patch("builtins.print") as output:
            run([])
        send.assert_not_called()
        self.assertIn("Sem ingestão na última hora", output.call_args.args[0])

    def test_run_deduplicates_same_ingestion_and_preserves_shared_state(self):
        stamp = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
        latest = {"rows": [{"uf": "SP", "rotulo": "Tema", "volume": 10, "aumento": 20,
                            "ativa": True, "candidato": False}],
                  "hora_ingestao": stamp, "ingestao_id": "batch-1"}
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            state_path.write_text(json.dumps({"sent": ["old"], "other_alert": {"ok": True}}))
            with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/token"}), \
                 patch("tendencias_bq.em_alta_brasil.fetch_latest_ingestion", return_value=latest), \
                 patch("tendencias_bq.em_alta_brasil.send_discord", return_value={"id": "msg-1"}) as send:
                run(["--state", str(state_path)])
                run(["--state", str(state_path)])
            send.assert_called_once()
            saved = json.loads(state_path.read_text())
            self.assertEqual(saved["sent"], ["old"])
            self.assertEqual(saved["other_alert"], {"ok": True})
            self.assertIn("gtrends_em_alta_brasil_latest", saved)

    def test_run_sends_again_for_a_new_ingestion_even_if_content_is_unchanged(self):
        stamp = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
        rows = [{"uf": "SP", "rotulo": "Tema", "volume": 10, "aumento": 20,
                 "ativa": True, "candidato": False}]
        batches = [
            {"rows": rows, "hora_ingestao": stamp, "ingestao_id": "batch-1"},
            {"rows": rows, "hora_ingestao": stamp + timedelta(hours=1), "ingestao_id": "batch-2"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/token"}), \
                 patch("tendencias_bq.em_alta_brasil.fetch_latest_ingestion", side_effect=batches), \
                 patch("tendencias_bq.em_alta_brasil.send_discord", return_value={"id": "msg"}) as send:
                run(["--state", str(state_path)])
                run(["--state", str(state_path)])
            self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
