import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient


@dataclass
class OIDCConfig:
    issuer: str
    client_id: str
    client_secret: str
    audience: str
    redirect_uri: str
    post_logout_redirect_uri: str


_CONFIG_CACHE: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str) -> Optional[dict]:
    entry = _CONFIG_CACHE.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at < time.time():
        _CONFIG_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: dict, ttl_seconds: int = 600) -> None:
    _CONFIG_CACHE[key] = (time.time() + ttl_seconds, value)


async def _fetch_openid_config(issuer: str) -> dict:
    cached = _cache_get(issuer)
    if cached:
        return cached
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    data = response.json()
    _cache_set(issuer, data)
    return data


class OIDCClient:
    def __init__(self, config: OIDCConfig) -> None:
        self._config = config
        self._jwks_client: Optional[PyJWKClient] = None
        self._token_endpoint: Optional[str] = None
        self._authorization_endpoint: Optional[str] = None
        self._end_session_endpoint: Optional[str] = None

    async def _ensure_metadata(self) -> None:
        if self._token_endpoint and self._authorization_endpoint:
            return
        metadata = await _fetch_openid_config(self._config.issuer)
        self._authorization_endpoint = metadata["authorization_endpoint"]
        self._token_endpoint = metadata["token_endpoint"]
        self._end_session_endpoint = metadata.get("end_session_endpoint")
        jwks_uri = metadata["jwks_uri"]
        self._jwks_client = PyJWKClient(jwks_uri)

    async def build_authorize_url(self, state: str, nonce: str) -> str:
        await self._ensure_metadata()
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
        }
        if self._config.audience:
            params["audience"] = self._config.audience
        return f"{self._authorization_endpoint}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        await self._ensure_metadata()
        payload = {
            "grant_type": "authorization_code",
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "redirect_uri": self._config.redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self._token_endpoint, data=payload)
        response.raise_for_status()
        return response.json()

    def verify_jwt(self, token: str, nonce: Optional[str] = None) -> dict:
        if not self._jwks_client:
            raise RuntimeError("OIDC metadata not initialized")
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        audience = self._config.audience or self._config.client_id
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=self._config.issuer,
        )
        if nonce and claims.get("nonce") != nonce:
            raise jwt.InvalidTokenError("invalid_nonce")
        return claims

    async def build_logout_url(self, id_token_hint: str) -> Optional[str]:
        await self._ensure_metadata()
        if not self._end_session_endpoint:
            return None
        params = {
            "id_token_hint": id_token_hint,
        }
        if self._config.post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = self._config.post_logout_redirect_uri
        return f"{self._end_session_endpoint}?{urllib.parse.urlencode(params)}"
