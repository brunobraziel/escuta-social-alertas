import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tendencias_busca.drive.termos import load_terms
from tendencias_busca.google.coleta import merge_batches, SourceUnavailable, trending
from tendencias_busca.resumo import fingerprint, render
from tendencias_busca.run import run

SNAPSHOT = {"terms": ["Tema A", "Tema B"], "source_url": "https://docs.google.com/document/d/example/edit", "source_modified": "2026-10-16"}


class TrendsTests(unittest.TestCase):
    def setUp(self):
        for target in ("tendencias_busca.run.expired", "tendencias_busca.diagnostico.expired"):
            item = patch(target, return_value=False)
            item.start()
            self.addCleanup(item.stop)

    def test_common_anchor_connects_batches(self):
        terms = list("ABCDEF")
        parts = [{"MG": {"A": 10, "B": 20, "C": 30, "D": 10, "E": 30}}, {"MG": {"A": 25, "F": 75}}]
        rows = merge_batches(terms, parts, ["MG"])["MG"]
        values = {r["term"]: r["index"] for r in rows}
        self.assertEqual(values["C"], values["F"])
        self.assertEqual(values["B"], 66.7)

    def test_zero_anchor_cannot_rank(self):
        self.assertIsNone(merge_batches(["A", "B"], [{"MG": {"A": 0, "B": 100}}], ["MG"])["MG"])

    def test_missing_term_cannot_rank(self):
        self.assertIsNone(merge_batches(["A", "B"], [{"MG": {"A": 10}}], ["MG"])["MG"])

    def test_national_feed_not_labelled_state(self):
        xml = b'<rss><channel><link>https://trends.google.com/trending/rss?geo=BR</link></channel></rss>'
        with patch("tendencias_busca.google.coleta.read_url", return_value=xml):
            with self.assertRaises(SourceUnavailable):
                trending("MG")

    def test_no_hardcoded_terms(self):
        with patch.dict("os.environ", {"ESCUTA_SOCIAL_TERMS_JSON": json.dumps(SNAPSHOT)}):
            self.assertEqual(load_terms()["terms"], SNAPSHOT["terms"])

    def test_fingerprint_ignores_score_noise_but_detects_new_topics(self):
        a = {"MG": [{"term": "A", "index": 100}]}
        b = {"MG": [{"term": "A", "index": 99}]}
        self.assertEqual(fingerprint({"MG": ["x"]}, a, ["A"]), fingerprint({"MG": ["x"]}, b, ["A"]))
        self.assertNotEqual(fingerprint({"MG": ["x"]}, a, ["A"]), fingerprint({"MG": ["y"]}, a, ["A"]))

    def test_one_message_and_no_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text('{"sent": ["existing"]}')
            with patch("tendencias_busca.run.load_terms", return_value=SNAPSHOT), patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("tendencias_busca.run.compare_all", return_value={"MG": [{"term": "Tema A", "index": 100}]}), patch("tendencias_busca.run.trending", return_value=["Tema X"]), patch("tendencias_busca.run.send_discord") as send:
                run(["--states", "MG", "--state", str(path)])
                run(["--states", "MG", "--state", str(path)])
                send.assert_called_once()
                self.assertIn("details_message", send.call_args.args[1])
            self.assertEqual(json.loads(path.read_text())["sent"], ["existing"])

    def test_failure_never_sends_partial_or_changes_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            original = '{"sent": ["existing"]}'
            path.write_text(original)
            with patch("tendencias_busca.run.load_terms", return_value=SNAPSHOT), patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("tendencias_busca.run.compare_all", side_effect=SourceUnavailable("429")), patch("tendencias_busca.run.send_discord") as send:
                with self.assertRaises(SourceUnavailable):
                    run(["--states", "MG", "--state", str(path)])
                send.assert_not_called()
            self.assertEqual(path.read_text(), original)

    def test_full_report_fits_one_discord_message(self):
        from tendencias_busca.estados import ESTADOS
        general = {uf: ["X" * 100, "Y" * 100] for uf in ESTADOS}
        monitored = {uf: [{"term": "A" * 80, "index": 100}, {"term": "B" * 80, "index": 90}] for uf in ESTADOS}
        report = render(general, monitored, SNAPSHOT, "2026-10-16")
        self.assertLessEqual(len(report["message"]), 2800)
        self.assertLessEqual(len(report["details_message"]), 2800)

    def test_two_embeds_one_http_request(self):
        from core.alerta import send_discord
        article = {"title": "Resumo", "description": "", "url": "https://trends.google.com", "published": "2026-10-16", "message": "Seção 1", "details_message": "Seção 2"}
        with patch("urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"id":"123"}'
            send_discord("https://discord.com/api/webhooks/123/example", article, "Teste")
            request.assert_called_once()
            payload = json.loads(request.call_args.args[0].data)
            self.assertEqual(len(payload["embeds"]), 2)

    def test_probe_stops_after_failure_without_printing_terms(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from tendencias_busca.diagnostico import run as probe
        output = StringIO()
        with patch("tendencias_busca.diagnostico.load_terms", return_value=SNAPSHOT), patch("tendencias_busca.diagnostico.compare_all", side_effect=SourceUnavailable("Google Trends HTTP 429")) as compare, patch("tendencias_busca.diagnostico.trending") as rss, redirect_stdout(output):
            with self.assertRaises(SystemExit):
                probe()
            compare.assert_called_once()
            rss.assert_not_called()
        self.assertIn("HTTP 429", output.getvalue())
        for term in SNAPSHOT["terms"]:
            self.assertNotIn(term, output.getvalue())

    def test_rounded_zero_does_not_invalidate_clear_highlights(self):
        result = merge_batches(["A", "B", "C"], [{"MG": {"A": 60, "B": 40, "C": 0}}], ["MG"])
        self.assertEqual([r["term"] for r in result["MG"][:2]], ["A", "B"])

    def test_unresolved_zero_limit_cannot_rank(self):
        result = merge_batches(["A", "B", "C"], [{"MG": {"A": 99, "B": 1, "C": 0}}], ["MG"])
        self.assertIsNone(result["MG"])
