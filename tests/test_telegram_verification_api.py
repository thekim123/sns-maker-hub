import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from typing import Any

import jwt
from fastapi.testclient import TestClient


def _load_main_module(db_path: str):
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["HUB_API_KEY"] = "test-api-key"
    os.environ["ALLOW_NEW_USERS"] = "true"
    for name in ["app_config", "hub_store", "main"]:
        if name in sys.modules:
            del sys.modules[name]
    return importlib.import_module("main")


class TelegramVerificationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "hub.db")
        self.main = _load_main_module(self.db_path)
        self.client = TestClient(self.main.app)
        self.main.store.add_user("u1")
        self.main.store.add_user("u2")

    def tearDown(self) -> None:
        self.client.close()
        try:
            self._tmpdir.cleanup()
        except PermissionError:
            pass

    def _auth_headers(self, user_id: str) -> dict[str, str]:
        token = jwt.encode({"sub": user_id}, "test-secret", algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def _api_key_headers(self) -> dict[str, str]:
        return {"X-API-KEY": "test-api-key"}

    def _challenge(self, user_id: str) -> dict[str, Any]:
        res = self.client.post(
            "/profile/telegram/challenge",
            headers=self._auth_headers(user_id),
            json={"bot_username": "mybot"},
        )
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_challenge_requires_login(self) -> None:
        res = self.client.post("/profile/telegram/challenge", json={})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "login_required")

    def test_challenge_response_contains_nonce_and_start_command(self) -> None:
        data = self._challenge("u1")
        self.assertTrue(data["nonce"])
        self.assertEqual(data["expires_in"], 300)
        self.assertTrue(data["start_command"].startswith("/start "))
        self.assertIn("https://t.me/mybot?start=", data["bot_link"])

    def test_verify_complete_success_updates_profile(self) -> None:
        data = self._challenge("u1")
        nonce = data["nonce"]
        res = self.client.post(
            "/telegram/verify/complete",
            headers=self._api_key_headers(),
            json={
                "nonce": nonce,
                "telegram_user_id": "123456789",
                "telegram_username": "user_name",
            },
        )
        self.assertEqual(res.status_code, 200)
        profile = self.client.get("/profile", headers=self._auth_headers("u1")).json()["profile"]
        self.assertEqual(profile["telegram_id"], "123456789")

    def test_invalid_telegram_user_id_fails_and_after_5_returns_max_attempts(self) -> None:
        data = self._challenge("u1")
        nonce = data["nonce"]
        for _ in range(4):
            res = self.client.post(
                "/telegram/verify/complete",
                headers=self._api_key_headers(),
                json={"nonce": nonce, "telegram_user_id": "not-a-number"},
            )
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["detail"], "invalid_telegram_user_id")
        res = self.client.post(
            "/telegram/verify/complete",
            headers=self._api_key_headers(),
            json={"nonce": nonce, "telegram_user_id": "still-invalid"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "max_attempts_reached")

    def test_expired_nonce_returns_expired_nonce(self) -> None:
        data = self._challenge("u1")
        nonce = data["nonce"]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE telegram_verifications SET expires_at = 0 WHERE nonce = ?",
                (nonce,),
            )
            conn.commit()
        res = self.client.post(
            "/telegram/verify/complete",
            headers=self._api_key_headers(),
            json={"nonce": nonce, "telegram_user_id": "123456789"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "expired_nonce")

    def test_same_telegram_id_cannot_link_two_users(self) -> None:
        first = self._challenge("u1")["nonce"]
        second = self._challenge("u2")["nonce"]
        ok = self.client.post(
            "/telegram/verify/complete",
            headers=self._api_key_headers(),
            json={"nonce": first, "telegram_user_id": "55555"},
        )
        self.assertEqual(ok.status_code, 200)
        conflict = self.client.post(
            "/telegram/verify/complete",
            headers=self._api_key_headers(),
            json={"nonce": second, "telegram_user_id": "55555"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "telegram_id_already_linked")

    def test_patch_profile_requires_verification(self) -> None:
        res = self.client.patch(
            "/profile",
            headers=self._auth_headers("u1"),
            json={"telegram_id": "@myname"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "telegram_verification_required")


if __name__ == "__main__":
    unittest.main()
