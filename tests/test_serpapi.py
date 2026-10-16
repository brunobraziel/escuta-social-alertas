import json
import unittest
from datetime import datetime
from unittest.mock import patch

from main import scheduled_entries
from tendencias_busca.google.serpapi import compare_batch, compare_all
from tendencias_busca.google.coleta import SourceUnavailable
from tendencias_busca.janela import expired


class SerpTests(unittest.TestCase):
    def test_provider_region_and_secret_not_logged(self):
        data = {"search_metadata": {"status": "Success"}, "compared_breakdown_by_region": [{"geo": "BR-MG", "values": [{"query": "A", "extracted_value": 40}, {"query": "B", "extracted_value": 60}]}]}
        with patch("urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
            self.assertEqual(compare_batch(["A", "B"], "test-key"), {"MG": {"A": 40, "B": 60}})
            from urllib.parse import parse_qs, urlparse
            parameters = parse_qs(urlparse(request.call_args.args[0].full_url).query)
            self.assertEqual(parameters["region"], ["REGION"])
            self.assertEqual(parameters["geo"], ["BR"])

    def test_nine_terms_only_two_requests_for_all_states(self):
        terms = list("ABCDEFGHI")
        def response(group, key):
            return {"MG": dict.fromkeys(group, 10)}
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test"}), patch("tendencias_busca.google.serpapi.compare_batch", side_effect=response) as request:
            compare_all(terms, ["MG", "SP"])
            self.assertEqual(request.call_count, 2)

    def test_failure_not_retried(self):
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test"}), patch("tendencias_busca.google.serpapi.compare_batch", side_effect=SourceUnavailable("429")) as request:
            with self.assertRaises(SourceUnavailable):
                compare_all(list("ABCDEFGHI"), ["MG"])
            request.assert_called_once()

    def test_larger_list_blocked_before_charging(self):
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test"}), patch("tendencias_busca.google.serpapi.compare_batch") as request:
            with self.assertRaises(SourceUnavailable):
                compare_all(list("ABCDEFGHIJ"), ["MG"])
            request.assert_not_called()

    def test_hourly_news_and_two_hourly_trends(self):
        entries = [{"id": "news"}, {"id": "trends", "agenda": {"intervalo_horas": 2, "fim_exclusivo": "2026-10-25T00:00:00-03:00"}}]
        for hour, ids in [(10, ["news", "trends"]), (11, ["news"])]:
            now = datetime.fromisoformat(f"2026-10-24T{hour}:07:00-03:00")
            self.assertEqual([e["id"] for e in scheduled_entries(entries, now)], ids)
        now = datetime.fromisoformat("2026-10-25T00:07:00-03:00")
        self.assertEqual([e["id"] for e in scheduled_entries(entries, now)], ["news"])

    def test_cutoff_in_fortaleza(self):
        self.assertFalse(expired(datetime.fromisoformat("2026-10-24T23:59:59-03:00")))
        self.assertTrue(expired(datetime.fromisoformat("2026-10-25T03:00:00+00:00")))

    def test_expired_run_never_reads_terms_or_calls_api(self):
        from tendencias_busca.run import run
        with patch("tendencias_busca.run.expired", return_value=True), patch("tendencias_busca.run.load_terms") as terms, patch("tendencias_busca.run.compare_all") as compare:
            run(["--dry-run"])
            terms.assert_not_called()
            compare.assert_not_called()

    def test_anchor_selected_without_extra_request(self):
        terms = list("ABCDEFGHI")
        calls = []
        def response(group, key):
            calls.append(group)
            return {"MG": {term: (90 if term == "D" else 0 if term == "A" else 10) for term in group}}
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test"}), patch("tendencias_busca.google.serpapi.compare_batch", side_effect=response):
            result = compare_all(terms, ["MG"])
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1][0], "D")
            self.assertIsNotNone(result["MG"])

    def test_daily_agenda(self):
        entries = [{"id": "trends", "agenda": {"intervalo_horas": 24}}]
        self.assertEqual(scheduled_entries(entries, datetime.fromisoformat("2026-10-20T00:07:00-03:00")), entries)
        self.assertEqual(scheduled_entries(entries, datetime.fromisoformat("2026-10-20T02:07:00-03:00")), [])

    def test_four_hour_agenda(self):
        entries = [{"id": "trends", "agenda": {"intervalo_horas": 4}}]
        for hour in range(24):
            now = datetime.fromisoformat(f"2026-10-20T{hour:02d}:07:00-03:00")
            self.assertEqual(bool(scheduled_entries(entries, now)), hour in (0, 4, 8, 12, 16, 20))
