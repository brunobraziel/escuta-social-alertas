import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.alerta import matches, fetch_feed
import acompanhamento_legislativo.run as main

class AlertTests(unittest.TestCase):
    def test_filter(self):
        self.assertTrue(matches("Fim da escala 6X1", "Veja quando entra em vigor"))
        self.assertTrue(matches("Escala 6 por 1", "Promulgação e transição"))
        self.assertFalse(matches("Escala 6x1", "Veja a votação"))
        self.assertFalse(matches("Bolsa Família", "Calendário de publicação"))
        self.assertFalse(matches("Nova proposta de tarifa zero", "Em publicação sobre o fim da escala 6x1"))

    def test_recent_feed_and_host(self):
        from datetime import datetime, timezone
        from email.utils import format_datetime
        date = format_datetime(datetime.now(timezone.utc))
        xml = f"<rss><channel><item><title>Escala 6x1: promulgação</title><link>https://g1.globo.com/a</link><pubDate>{date}</pubDate></item><item><title>Escala 6x1: vigência</title><link>https://evil.example/a</link><pubDate>{date}</pubDate></item></channel></rss>"
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = xml.encode()
            self.assertEqual(len(fetch_feed("https://example.org", ["g1.globo.com"])), 1)

    def test_confirmed_delivery_deduplicated(self):
        article = {"title": "Escala 6x1", "description": "Transição", "url": "https://g1.globo.com/a", "published": "2026-10-15"}
        with tempfile.TemporaryDirectory() as folder:
            state = str(Path(folder)/"state.json")
            Path(state).write_text(json.dumps({"sent": [], "latest_trends": "preserve"}))
            with patch("sys.argv", ["main", "--site", "g1", "--state", state]), patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("acompanhamento_legislativo.run.fetch_feed", return_value=[article]), patch("acompanhamento_legislativo.run.send_discord") as send:
                main.run()
                main.run()
                self.assertEqual(send.call_count, 1)
                self.assertEqual(len(json.loads(Path(state).read_text())["sent"]), 1)
                self.assertEqual(json.loads(Path(state).read_text())["latest_trends"], "preserve")

    def test_failed_delivery_not_recorded(self):
        article = {"url": "https://g1.globo.com/a"}
        with tempfile.TemporaryDirectory() as folder:
            state = str(Path(folder)/"state.json")
            with patch("sys.argv", ["main", "--site", "g1", "--state", state]), patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("acompanhamento_legislativo.run.fetch_feed", return_value=[article]), patch("acompanhamento_legislativo.run.send_discord", side_effect=RuntimeError("failure")):
                with self.assertRaises(RuntimeError):
                    main.run()
                self.assertFalse(Path(state).exists())

    def test_webhook_preserves_thread(self):
        from core.alerta import send_discord
        article = {"title": "Teste", "description": "Teste", "url": "https://example.com", "published": "2026-10-15"}
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"123"}'
            send_discord("https://discord.com/api/webhooks/123/token?thread_id=456", article, "Teste")
            self.assertIn("thread_id=456", urlopen.call_args.args[0].full_url)
            self.assertIn("wait=true", urlopen.call_args.args[0].full_url)

    def test_webhook_accepts_custom_message_without_article_description(self):
        from core.alerta import send_discord
        report = {
            "title": "Tendências BQ",
            "alert_title": "Assuntos em alta por estado",
            "message": "Relatório preparado no BigQuery",
            "url": "https://console.cloud.google.com/bigquery?project=comite-tecnologia",
            "published": "2026-10-18T18:27:35+00:00",
        }
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"id":"123"}'
            send_discord("https://discord.com/api/webhooks/123/token", report, "BigQuery", test=True)
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["embeds"][0]["description"], "Relatório preparado no BigQuery")

    def test_forum_creates_topic_after_rejection(self):
        import io
        import urllib.error
        from unittest.mock import MagicMock
        from core.alerta import send_discord
        article = {"title": "Teste", "description": "Teste", "url": "https://example.com", "published": "2026-10-15"}
        error = urllib.error.HTTPError("https://discord.com", 400, "Bad Request", {}, io.BytesIO(b'{"code":220001}'))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"123"}'
        with patch("urllib.request.urlopen", side_effect=[error, response]) as urlopen:
            send_discord("https://discord.com/api/webhooks/123/token", article, "Teste", test=True)
            self.assertEqual(urlopen.call_count, 2)
            payload = json.loads(urlopen.call_args.args[0].data)
            self.assertTrue(payload["thread_name"].startswith("[TESTE]"))

    def test_empty_feed_does_not_notify_or_change_state(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            original = '{"sent": ["existing"]}'
            state.write_text(original)
            with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("acompanhamento_legislativo.run.fetch_feed", return_value=[]), patch("acompanhamento_legislativo.run.send_discord") as send:
                main.run(["--state", str(state)])
                send.assert_not_called()
            self.assertEqual(state.read_text(), original)
