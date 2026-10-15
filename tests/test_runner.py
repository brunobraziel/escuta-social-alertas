import unittest
from unittest.mock import patch, Mock
import main


class RunnerTests(unittest.TestCase):
    def test_failure_does_not_stop_next_alert(self):
        broken = Mock()
        broken.run.side_effect = SystemExit(1)
        working = Mock()
        entries = [{"id": "broken", "modulo": "a"}, {"id": "working", "modulo": "b"}]
        with patch("main.importlib.import_module", side_effect=[broken, working]):
            self.assertEqual(main.execute(entries, "live", "shared.json"), ["broken"])
        working.run.assert_called_once_with(["--state", "shared.json"])

    def test_test_requires_single_alert(self):
        with patch("main.execute") as execute:
            with self.assertRaises(SystemExit) as error:
                main.run(["--mode", "test"])
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()

    def test_disabled_alert_cannot_run(self):
        with patch("main.load_catalog", return_value=[{"id": "off", "ativo": False}]), patch("main.execute") as execute:
            with self.assertRaises(SystemExit):
                main.run(["--alert", "off"])
            execute.assert_not_called()

    def test_scope_selection(self):
        with patch("main.execute", return_value=[]) as execute:
            main.run(["--alert", "pesquisa_presidente", "--mode", "dry-run"])
            entries, mode, state = execute.call_args.args
            self.assertEqual([entry["id"] for entry in entries], ["pesquisa_presidente"])
            self.assertEqual(mode, "dry-run")
            self.assertEqual(state, "state.json")

    def test_shared_state_preserves_existing_deliveries(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        def scope_run(args):
            path = Path(args[1])
            state = json.loads(path.read_text())
            state["sent"].append("new")
            path.write_text(json.dumps(state))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_text(json.dumps({"sent": ["existing"]}))
            with patch("main.importlib.import_module", return_value=SimpleNamespace(run=scope_run)):
                main.execute([{"id": "scope", "modulo": "scope.run"}], "live", str(path))
            self.assertEqual(json.loads(path.read_text())["sent"], ["existing", "new"])
