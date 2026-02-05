import importlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest


class HubStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "hub.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        for name in ["app_config", "hub_store"]:
            if name in sys.modules:
                del sys.modules[name]
        HubStore = importlib.import_module("hub_store").HubStore

        self.store = HubStore()
        self.db_path = db_path

    def tearDown(self) -> None:
        try:
            self._tmpdir.cleanup()
        except PermissionError:
            pass

    def test_fail_count_reaches_max_and_deletes_nonce(self) -> None:
        self.store.create_telegram_verification("nonce-1", "u1", time.time() + 300)
        for _ in range(4):
            result = self.store.fail_telegram_verification("nonce-1", max_attempts=5)
            self.assertEqual(result["status"], "failed")
        result = self.store.fail_telegram_verification("nonce-1", max_attempts=5)
        self.assertEqual(result["status"], "max_attempts")
        after = self.store.consume_telegram_verification("nonce-1", max_attempts=5)
        self.assertEqual(after["status"], "invalid")

    def test_expired_nonce_returns_expired_then_invalid(self) -> None:
        self.store.create_telegram_verification("nonce-expired", "u1", time.time() - 1)
        first = self.store.consume_telegram_verification("nonce-expired", max_attempts=5)
        self.assertEqual(first["status"], "expired")
        second = self.store.consume_telegram_verification("nonce-expired", max_attempts=5)
        self.assertEqual(second["status"], "invalid")

    def test_consume_nonce_success_deletes_row(self) -> None:
        self.store.create_telegram_verification("nonce-ok", "u1", time.time() + 300)
        result = self.store.consume_telegram_verification("nonce-ok", max_attempts=5)
        self.assertEqual(result["status"], "ok")
        again = self.store.consume_telegram_verification("nonce-ok", max_attempts=5)
        self.assertEqual(again["status"], "invalid")

    def test_set_telegram_id_must_be_unique(self) -> None:
        self.store.add_user("u1")
        self.store.add_user("u2")
        self.store.set_telegram_id("u1", "123456")
        with self.assertRaisesRegex(ValueError, "telegram_id_already_linked"):
            self.store.set_telegram_id("u2", "123456")

    def test_create_challenge_replaces_old_one_for_same_user(self) -> None:
        self.store.create_telegram_verification("nonce-a", "u1", time.time() + 300)
        self.store.create_telegram_verification("nonce-b", "u1", time.time() + 300)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM telegram_verifications WHERE user_id = ?",
                ("u1",),
            ).fetchone()
        self.assertEqual(int(row[0]), 1)


if __name__ == "__main__":
    unittest.main()
