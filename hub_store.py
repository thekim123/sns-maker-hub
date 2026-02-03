import sqlite3
import time
from typing import Optional

from app_config import DATABASE_URL


def _sqlite_path() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.replace("sqlite:///", "")
    return "hub.db"


class HubStore:
    def __init__(self) -> None:
        self._path = _sqlite_path()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hub_users (
                    user_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oidc_states (
                    state TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS naver_accounts (
                    user_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    client_secret TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    token_expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    post_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def add_user(self, user_id: str) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO hub_users (user_id, created_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.commit()

    def is_user(self, user_id: str) -> bool:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT user_id FROM hub_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row is not None

    def count_users(self) -> int:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM hub_users").fetchone()
        return int(row[0]) if row else 0

    def save_oauth_state(self, state: str, user_id: str) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO oauth_states (state, user_id, created_at) VALUES (?, ?, ?)",
                (state, user_id, now),
            )
            conn.commit()

    def pop_oauth_state(self, state: str) -> Optional[str]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT user_id FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
                conn.commit()
                return str(row[0])
        return None

    def save_oidc_state(self, state: str, nonce: str) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO oidc_states (state, nonce, created_at) VALUES (?, ?, ?)",
                (state, nonce, now),
            )
            conn.commit()

    def pop_oidc_state(self, state: str) -> Optional[str]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT nonce FROM oidc_states WHERE state = ?",
                (state,),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM oidc_states WHERE state = ?", (state,))
                conn.commit()
                return str(row[0])
        return None

    def upsert_naver_account(
        self,
        user_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: float,
    ) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO naver_accounts (
                    user_id, client_id, client_secret, redirect_uri,
                    access_token, refresh_token, token_expires_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    client_id = excluded.client_id,
                    client_secret = excluded.client_secret,
                    redirect_uri = excluded.redirect_uri,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    token_expires_at = excluded.token_expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    client_id,
                    client_secret,
                    redirect_uri,
                    access_token,
                    refresh_token,
                    token_expires_at,
                    now,
                ),
            )
            conn.commit()

    def get_naver_account(self, user_id: str) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT client_id, client_secret, redirect_uri, access_token, refresh_token, token_expires_at
                FROM naver_accounts WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "client_id": row[0],
            "client_secret": row[1],
            "redirect_uri": row[2],
            "access_token": row[3],
            "refresh_token": row[4],
            "token_expires_at": float(row[5]),
        }

    def count_naver_accounts(self) -> int:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM naver_accounts").fetchone()
        return int(row[0]) if row else 0

    def create_job(self, job_id: str, user_id: str, payload: str) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, user_id, status, payload, result, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, user_id, "queued", payload, "", now, now),
            )
            conn.commit()

    def fetch_next_job(self) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT job_id, user_id, payload FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE jobs SET status = 'processing', updated_at = ? WHERE job_id = ?",
                (time.time(), row[0]),
            )
            conn.commit()
        return {"job_id": row[0], "user_id": row[1], "payload": row[2]}

    def complete_job(self, job_id: str, result: str) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE jobs SET status = 'done', result = ?, updated_at = ? WHERE job_id = ?",
                (result, time.time(), job_id),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT job_id, user_id, status, payload, result, created_at, updated_at FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "job_id": row[0],
            "user_id": row[1],
            "status": row[2],
            "payload": row[3],
            "result": row[4],
            "created_at": float(row[5]),
            "updated_at": float(row[6]),
        }

    def count_jobs_by_status(self, status: str) -> int:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()
        return int(row[0]) if row else 0

    def list_recent_jobs(self, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT job_id, user_id, status, updated_at
                FROM jobs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "job_id": str(row[0]),
                "user_id": str(row[1]),
                "status": str(row[2]),
                "updated_at": float(row[3]),
            }
            for row in rows
        ]

    def create_post(self, post_id: str, user_id: str, title: str, content: str) -> None:
        now = time.time()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO posts (post_id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (post_id, user_id, title, content, now),
            )
            conn.commit()

    def get_latest_post(self, user_id: str) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT post_id, title, content, created_at FROM posts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "post_id": row[0],
            "title": row[1],
            "content": row[2],
            "created_at": float(row[3]),
        }

    def get_post(self, post_id: str) -> Optional[dict]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT post_id, user_id, title, content, created_at FROM posts
                WHERE post_id = ?
                """,
                (post_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "post_id": row[0],
            "user_id": row[1],
            "title": row[2],
            "content": row[3],
            "created_at": float(row[4]),
        }

    def list_latest_posts(self, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT post_id, user_id, title, created_at
                FROM posts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "post_id": str(row[0]),
                "user_id": str(row[1]),
                "title": str(row[2]),
                "created_at": float(row[3]),
            }
            for row in rows
        ]
