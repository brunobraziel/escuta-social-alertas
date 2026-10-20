import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from validar_alertas_reais import validate


class ValidationTests(unittest.TestCase):
    def test_real_send_with_isolated_state_and_disabled_alert_skipped(self):
        sender = Mock(return_value={"id": "confirmed"})
        module = SimpleNamespace(send_discord=sender)

        def run(args):
            self.assertNotIn("--test", args)
            self.assertIn("--limit", args)
            self.assertNotEqual(args[1], "state.json")
            module.send_discord("secret", {"title": "Notícia real", "url": "https://example.org/news", "published": "2026-10-20"}, "fonte")

        module.run = run
        entries = [{"id": "escala_6x1", "modulo": "real", "ativo": True},
                   {"id": "disabled", "modulo": "never", "ativo": False}]
        with tempfile.TemporaryDirectory() as directory, patch("validar_alertas_reais.importlib.import_module", return_value=module) as imports:
            path = Path(directory) / "report.json"
            self.assertTrue(validate(entries, path))
            self.assertEqual(len(json.loads(path.read_text())), 1)
            imports.assert_called_once_with("real")
        self.assertFalse(sender.call_args.kwargs["test"])
        self.assertIn("dados reais", sender.call_args.args[1]["alert_title"])

    def test_no_eligible_data_is_not_reported_as_success(self):
        module = SimpleNamespace(send_discord=Mock(), run=Mock())
        with tempfile.TemporaryDirectory() as directory, patch("validar_alertas_reais.importlib.import_module", return_value=module):
            self.assertFalse(validate([{"id": "active", "modulo": "real", "ativo": True}], Path(directory) / "report.json"))
        module.send_discord.assert_not_called()
