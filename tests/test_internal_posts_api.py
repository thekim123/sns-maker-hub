import importlib
import os
import sys
import tempfile
import unittest

import jwt
from fastapi.testclient import TestClient


def _load_main_module(db_path: str):
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["HUB_API_KEY"] = "test-api-key"
    os.environ["HUB_SERVICE_TOKEN"] = "svc-token"
    os.environ["HUB_INTERNAL_API_KEY"] = "internal-key"
    os.environ["ALLOW_NEW_USERS"] = "true"
    for name in ["app_config", "hub_store", "main"]:
        if name in sys.modules:
            del sys.modules[name]
    return importlib.import_module("main")


class InternalPostsApiTest(unittest.TestCase):
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

    def _user_headers(self, user_id: str) -> dict[str, str]:
        token = jwt.encode({"sub": user_id}, "test-secret", algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def test_internal_posts_accepts_service_token(self) -> None:
        res = self.client.post(
            "/internal/posts",
            headers={"Authorization": "Bearer svc-token"},
            json={"user_id": "u1", "title": "t", "content": "c"},
        )
        self.assertEqual(res.status_code, 200)
        latest = self.main.store.get_latest_post("u1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["title"], "t")

    def test_internal_posts_accepts_internal_api_key(self) -> None:
        res = self.client.post(
            "/internal/posts",
            headers={"X-Internal-API-Key": "internal-key"},
            json={"user_id": "u1", "title": "t2", "content": "c2"},
        )
        self.assertEqual(res.status_code, 200)
        latest = self.main.store.get_latest_post("u1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["title"], "t2")

    def test_internal_posts_requires_service_auth(self) -> None:
        res = self.client.post(
            "/internal/posts",
            json={"user_id": "u1", "title": "t", "content": "c"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "service_auth_required")

    def test_posts_requires_user_login(self) -> None:
        res = self.client.post("/posts", json={"user_id": "u1", "title": "t", "content": "c"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "login_required")

    def test_posts_forbidden_when_user_id_does_not_match_token(self) -> None:
        res = self.client.post(
            "/posts",
            headers=self._user_headers("u2"),
            json={"user_id": "u1", "title": "t", "content": "c"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "forbidden")


if __name__ == "__main__":
    unittest.main()
