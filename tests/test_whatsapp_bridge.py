import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import whatsapp_bridge as bridge


class WhatsAppBridgeTests(unittest.TestCase):
    def test_disabled_does_not_create_files_or_authenticate(self):
        with patch.dict(os.environ, {"WHATSAPP_TOPIC": ""}), patch.object(bridge, "client") as client:
            bridge.mirror({"content": "hello"}, {"id": "123"})
            client.assert_not_called()

    def test_render_preserves_links_fields_and_all_embeds(self):
        text = bridge.render({"content": "**Concluído**", "embeds": [
            {"title": "Pesquisa", "description": "Resumo", "url": "https://example.com",
             "fields": [{"name": "Fonte", "value": "G1"}]}, {"description": "Detalhes"}]})
        self.assertIn("*Concluído*", text)
        self.assertIn("• *Fonte:* G1", text)
        self.assertIn("https://example.com", text)
        self.assertIn("Detalhes", text)

    def test_failed_publish_is_durable_and_retry_uses_same_event(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "WHATSAPP_TOPIC": "projects/test-project/topics/alerts", "WHATSAPP_OUTBOX": directory,
            "GITHUB_REPOSITORY": "owner/repo"}):
            with patch.object(bridge, "client", side_effect=RuntimeError("offline")):
                bridge.mirror({"content": "**Tabela A**"}, {"id": "123"})
                bridge.mirror({"content": "**Tabela A**"}, {"id": "123"})
            files = list(Path(directory).glob("*.json"))
            self.assertEqual(len(files), 1)
            event = json.loads(files[0].read_text())["event"]
            self.assertEqual(event["text"], "*Tabela A*")
            session = Mock()
            session.post.return_value.json.return_value = {"messageIds": ["456"]}
            self.assertEqual(bridge.flush(session), 0)
            self.assertFalse(files[0].exists())

    def test_missing_publication_receipt_keeps_outbox(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "WHATSAPP_TOPIC": "projects/test-project/topics/alerts", "WHATSAPP_OUTBOX": directory}):
            session = Mock()
            session.post.return_value.json.return_value = {}
            with patch.object(bridge, "client", return_value=session):
                bridge.mirror({"content": "hello"}, {"id": "123"})
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
