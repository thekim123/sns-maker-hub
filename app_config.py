import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is not None:
        value = value.strip()
    return value


def _get_env_bool(name: str, default: bool) -> bool:
    value = _get_env(name, None)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


DATABASE_URL = _get_env("DATABASE_URL", "sqlite:///./hub.db")
HUB_API_KEY = _get_env("HUB_API_KEY", "")
HUB_SERVICE_TOKEN = _get_env("HUB_SERVICE_TOKEN", "")
HUB_INTERNAL_API_KEY = _get_env("HUB_INTERNAL_API_KEY", "")
PUBLIC_BASE_URL = _get_env("PUBLIC_BASE_URL", "http://localhost:8000")
NAVER_AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_BLOG_WRITE_URL = "https://openapi.naver.com/blog/writePost.json"
NAVER_PROFILE_URL = "https://openapi.naver.com/v1/nid/me"

ALLOW_NEW_USERS = _get_env_bool("ALLOW_NEW_USERS", False)

NAVER_CLIENT_ID = _get_env("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = _get_env("NAVER_CLIENT_SECRET", "")
NAVER_REDIRECT_URI = _get_env("NAVER_REDIRECT_URI", "")

FRONTEND_BASE_URL = _get_env("FRONTEND_BASE_URL", "")
JWT_SECRET = _get_env("JWT_SECRET", "")
JWT_TTL_SECONDS = int(_get_env("JWT_TTL_SECONDS", "3600") or 3600)
