import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx

from app_config import NAVER_AUTHORIZE_URL, NAVER_BLOG_WRITE_URL, NAVER_TOKEN_URL


@dataclass
class NaverToken:
    access_token: str
    refresh_token: str
    expires_in: int

    def expires_at(self) -> float:
        return time.time() + max(0, int(self.expires_in) - 30)


class NaverClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def build_authorize_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{NAVER_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        state: str,
    ) -> NaverToken:
        params = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "state": state,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(NAVER_TOKEN_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return NaverToken(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def refresh_token(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> Optional[NaverToken]:
        params = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(NAVER_TOKEN_URL, params=params)
        if response.status_code >= 400:
            return None
        data = response.json()
        return NaverToken(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def write_post(
        self,
        access_token: str,
        client_id: str,
        client_secret: str,
        title: str,
        content: str,
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        payload = {
            "title": title,
            "contents": content,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(NAVER_BLOG_WRITE_URL, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()
