import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("whatsapp_worker", Path(__file__).parents[1] / "infra/whatsapp/worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WhatsAppWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = worker.connect(str(Path(self.directory.name) / "delivery.sqlite"))
        self.event = {"version": 1, "event_id": "a" * 64,
                      "source": "owner/repo", "text": "*Alerta*\nResumo"}
        self.env = patch.dict(os.environ, {"ALLOWED_SOURCES": "owner/repo"})
        self.env.start()

    def tearDown(self):
        self.db.close()
        self.env.stop()
        self.directory.cleanup()

    def status(self):
        return self.db.execute("SELECT status FROM deliveries").fetchone()[0]

    def test_pubsub_redelivery_is_persisted_once(self):
        worker.accept(self.db, self.event)
        worker.accept(self.db, self.event)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 1)

    def test_unapproved_source_rejected(self):
        with self.assertRaises(ValueError):
            worker.accept(self.db, dict(self.event, source="other/repo"))

    def test_offline_session_preserves_pending(self):
        worker.accept(self.db, self.event)
        http = Mock()
        http.get.return_value.json.return_value = {"status": "SCAN_QR_CODE"}
        self.assertFalse(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "pending")
        http.post.assert_not_called()

    def test_delivery_confirmation_prevents_resending(self):
        worker.accept(self.db, self.event)
        http = Mock()
        http.get.return_value.json.return_value = {"status": "WORKING"}
        http.post.return_value.json.return_value = {"id": "waha-message-1"}
        self.assertTrue(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        worker.accept(self.db, self.event)
        self.assertFalse(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "sent")
        self.assertEqual(http.post.call_count, 1)

    def test_timeout_marks_uncertain_without_blind_resend(self):
        worker.accept(self.db, self.event)
        http = Mock()
        http.get.return_value.json.return_value = {"status": "WORKING"}
        http.post.side_effect = TimeoutError()
        worker.send_one(self.db, http, "http://waha", "123@g.us", "secret")
        worker.send_one(self.db, http, "http://waha", "123@g.us", "secret")
        self.assertEqual(self.status(), "uncertain")
        self.assertEqual(http.post.call_count, 1)

    def test_restart_after_interrupted_send_is_uncertain(self):
        worker.accept(self.db, self.event)
        with self.db:
            self.db.execute("UPDATE deliveries SET status='sending'")
        self.db.close()
        self.db = worker.connect(str(Path(self.directory.name) / "delivery.sqlite"))
        self.assertEqual(self.status(), "uncertain")

    def test_long_text_preserved_in_order(self):
        text = "a" * 4000 + "\n" + "b" * 4000
        chunks = worker.parts(text)
        self.assertTrue(all(len(x) <= 3500 for x in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), text.replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
