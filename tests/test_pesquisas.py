import unittest
from pesquisas_eleitorais.parser import matches_poll, parse_poll, as_alert


def article():
    return {"title": "Datafolha, 2º turno: Candidata A, 47%; Candidato B, 45%", "url": "https://g1.globo.com/presidente", "published": "2026-10-15T20:00:00+00:00", "description": "Pesquisa Datafolha. Veja os números - votos totais: Candidata A (AA): 47% (eram 49%) Candidato B (BB): 45% (eram 45%) Em branco/nulo/nenhum: 6% Indecisos: 2% Datafolha: votos válidos. A margem de erro é de dois pontos percentuais. O nível de confiança é de 95%. O Datafolha ouviu 2.520 pessoas, entre os dias 13 e 14 de outubro. Registro BR-12345/2026. Rejeição: 80%."}


class PollTests(unittest.TestCase):
    def test_explicit_table_only(self):
        poll = parse_poll(article())
        self.assertIsNotNone(poll)
        self.assertEqual([r["percent"] for r in poll["results"]], [47, 45])
        self.assertEqual(poll["registration"], "BR-12345/2026")
        self.assertIn("47%", as_alert(article(), poll)["message"])

    def test_rejection_not_eligible(self):
        self.assertFalse(matches_poll("Datafolha: rejeição de candidato é 46%", ""))
        self.assertFalse(matches_poll("Datafolha: 50% desaprovam governo", ""))

    def test_missing_metadata_not_published(self):
        item = article()
        item["description"] = item["description"].replace("BR-12345/2026", "")
        self.assertIsNone(parse_poll(item))

    def test_no_mixing_valid_votes(self):
        item = article()
        item["description"] = item["description"].replace("votos totais:", "votos válidos:")
        self.assertIsNone(parse_poll(item))

    def test_incomplete_candidates_rejected(self):
        item = article()
        item["description"] = item["description"].replace("Candidato B (BB): 45%", "Candidato B: 45%")
        self.assertIsNone(parse_poll(item))

    def test_first_round_rejected(self):
        item = article()
        item["title"] = item["title"].replace("2º", "1º")
        self.assertIsNone(parse_poll(item))

    def test_no_eligible_poll_does_not_notify(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from pesquisas_eleitorais.run import run
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            original = '{"sent": ["existing"]}'
            state.write_text(original)
            with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("pesquisas_eleitorais.run.fetch_feed", return_value=[]), patch("pesquisas_eleitorais.run.send_discord") as send:
                run(["--state", str(state)])
                send.assert_not_called()
            self.assertEqual(state.read_text(), original)

    def test_already_sent_poll_does_not_notify_for_new_url(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from core.alerta import identifier
        from pesquisas_eleitorais.run import run
        item = article()
        item["url"] = "https://g1.globo.com/presidente-outra-url"
        key = identifier("pesquisa:BR-12345/2026:presidente:BR:2:votos_totais")
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            original = json.dumps({"sent": [key, "existing"]})
            state.write_text(original)
            with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "test"}), patch("pesquisas_eleitorais.run.fetch_feed", return_value=[item]), patch("pesquisas_eleitorais.run.send_discord") as send:
                run(["--state", str(state)])
                send.assert_not_called()
            self.assertEqual(state.read_text(), original)
