import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tendencias_busca.cache import export, snapshot, save_state
from tendencias_busca.run import run
from tendencias_busca.recuperar import archive_get
from tendencias_busca.resumo import render

SOURCE = {"terms": ["Tema A", "Tema B"], "source_modified": "2026-10-16"}


class CacheTests(unittest.TestCase):
    def saved(self):
        general = {"MG": ["Tema X"]}
        monitored = {"MG": [{"term": "Tema A", "index": 100}, {"term": "Tema B", "index": 25}]}
        report = render(general, monitored, SOURCE, "2026-10-16T14:00:00Z")
        return snapshot(general, monitored, report, SOURCE)

    def test_replay_without_credentials_expiry_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.json"
            save_state(path, {"sent": ["existing"], "trends_last_snapshot": self.saved()})
            original = path.read_bytes()
            with patch("tendencias_busca.run.compare_all") as compare, patch("tendencias_busca.run.trending") as rss, patch("tendencias_busca.run.load_terms") as terms, patch("tendencias_busca.run.send_discord") as send, patch("builtins.print") as output:
                run(["--cached", "--dry-run", "--state", str(path)])
                compare.assert_not_called()
                rss.assert_not_called()
                terms.assert_not_called()
                send.assert_not_called()
                self.assertIn("25", output.call_args.args[0])
            self.assertEqual(path.read_bytes(), original)

    def test_export_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.json"
            save_state(path, {"sent": [], "trends_last_snapshot": self.saved()})
            out = Path(folder)/"dados"
            export(path, out)
            self.assertEqual(json.loads((out/"ultima_coleta.json").read_text())["terms_count"], 2)
            self.assertIn("Tema B (25)", (out/"ultima_mensagem.md").read_text())
            self.assertNotIn("source_url", (out/"ultima_coleta.json").read_text())

    def test_archive_cannot_create_new_search(self):
        with patch("urllib.request.urlopen") as request:
            with self.assertRaises(ValueError):
                archive_get("/search.json", "example")
            request.assert_not_called()

    def test_report_labels_relative_index(self):
        cached = self.saved()
        self.assertIn("0–100", cached["report"]["details_message"])
        self.assertIn("Tema A (100)", cached["report"]["details_message"])
