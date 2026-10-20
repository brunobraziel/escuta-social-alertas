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

    def test_queued_event_cancelled_when_source_is_no_longer_allowed(self):
        worker.accept(self.db, self.event)
        http = Mock()
        with patch.dict(os.environ, {"ALLOWED_SOURCES": "alerts/repo"}):
            self.assertTrue(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "cancelled")
        http.get.assert_not_called()
        http.post.assert_not_called()

    def test_etl_can_only_send_explicit_last_token_event(self):
        etl = dict(self.event, source="brunobraziel/escuta-social-etl")
        with patch.dict(os.environ, {"ALLOW_ETL_LAST_TOKEN": "true"}):
            with self.assertRaises(ValueError):
                worker.accept(self.db, etl)
            with self.assertRaises(ValueError):
                worker.accept(self.db, dict(etl, kind="ingestion_success"))
            worker.accept(self.db, dict(etl, kind="serpapi_last_token"))
            http = Mock()
            http.get.return_value.json.return_value = {"status": "WORKING"}
            http.post.return_value.json.return_value = {"id": "message-1"}
            self.assertTrue(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "sent")

    def test_last_token_event_fails_closed_without_explicit_enablement(self):
        with patch.dict(os.environ, {"ALLOW_ETL_LAST_TOKEN": "false"}):
            with self.assertRaises(ValueError):
                worker.accept(self.db, dict(self.event, source="brunobraziel/escuta-social-etl", kind="serpapi_last_token"))

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

    def test_noweb_raw_message_confirmation(self):
        worker.accept(self.db, self.event)
        http = Mock()
        http.get.return_value.json.return_value = {"status": "WORKING"}
        http.post.return_value.json.return_value = {
            "key": {"id": "3EB0123456", "remoteJid": "123@g.us", "fromMe": True},
            "message": {"conversation": "Alerta"}}
        self.assertTrue(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "sent")
        receipts = self.db.execute("SELECT receipts FROM deliveries").fetchone()[0]
        self.assertEqual(json.loads(receipts), ["3EB0123456"])

    def test_raw_confirmation_for_other_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            worker.message_receipt({"key": {"id": "3EB0123456", "remoteJid": "other@g.us", "fromMe": True}}, "123@g.us")

    def test_missing_receipt_remains_uncertain(self):
        worker.accept(self.db, self.event)
        http = Mock()
        http.get.return_value.json.return_value = {"status": "WORKING"}
        http.post.return_value.json.return_value = {"success": True}
        self.assertFalse(worker.send_one(self.db, http, "http://waha", "123@g.us", "secret"))
        self.assertEqual(self.status(), "uncertain")

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
