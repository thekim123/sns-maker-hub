import time
from datetime import datetime, timezone
import json
import secrets
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import jwt

from app_config import (
    ALLOW_NEW_USERS,
    HUB_API_KEY,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_REDIRECT_URI,
    OIDC_AUDIENCE,
    OIDC_CLIENT_ID,
    OIDC_CLIENT_SECRET,
    OIDC_ISSUER,
    OIDC_POST_LOGOUT_REDIRECT_URI,
    OIDC_REDIRECT_URI,
    PUBLIC_BASE_URL,
)
from hub_store import HubStore
from naver_client import NaverClient
from oidc_client import OIDCClient, OIDCConfig

app = FastAPI(title="SNS Maker Hub")
store = HubStore()
naver_client = NaverClient()
server_start = time.time()

oidc_client: Optional[OIDCClient] = None
if OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and OIDC_REDIRECT_URI:
    oidc_client = OIDCClient(
        OIDCConfig(
            issuer=OIDC_ISSUER,
            client_id=OIDC_CLIENT_ID,
            client_secret=OIDC_CLIENT_SECRET,
            audience=OIDC_AUDIENCE,
            redirect_uri=OIDC_REDIRECT_URI,
            post_logout_redirect_uri=OIDC_POST_LOGOUT_REDIRECT_URI,
        )
    )


class JobRequest(BaseModel):
    user_id: str
    payload: dict


class JobResultRequest(BaseModel):
    result: str


class NaverSetRequest(BaseModel):
    user_id: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None


class PublishRequest(BaseModel):
    user_id: str
    title: Optional[str] = None
    post_id: Optional[str] = None


class RegisterRequest(BaseModel):
    user_id: str


class PostRecord(BaseModel):
    user_id: str
    title: str
    content: str


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


def _require_auth(api_key: Optional[str], authorization: Optional[str]) -> Optional[dict]:
    if HUB_API_KEY and api_key == HUB_API_KEY:
        return {"auth": "api_key"}
    if oidc_client and authorization:
        token = _extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            return oidc_client.verify_jwt(token)
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="unauthorized") from None
    if not HUB_API_KEY and not oidc_client:
        return {"auth": "none"}
    raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


def _format_ts(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


@app.get("/api/status")
async def status():
    now = time.time()
    return {
        "ok": True,
        "server_time": _format_ts(now),
        "uptime_seconds": int(now - server_start),
        "users": {"registered": store.count_users()},
        "jobs": {
            "queued": store.count_jobs_by_status("queued"),
            "processing": store.count_jobs_by_status("processing"),
            "done": store.count_jobs_by_status("done"),
            "recent": [
                {
                    "job_id": row["job_id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "updated_at": _format_ts(row["updated_at"]),
                }
                for row in store.list_recent_jobs(limit=5)
            ],
        },
        "naver": {"linked_accounts": store.count_naver_accounts()},
        "latest_posts": [
            {
                "post_id": row["post_id"],
                "user_id": row["user_id"],
                "title": row["title"],
                "created_at": _format_ts(row["created_at"]),
            }
            for row in store.list_latest_posts(limit=5)
        ],
    }


@app.get("/auth/login")
async def auth_login():
    if not oidc_client:
        raise HTTPException(status_code=400, detail="oidc_not_configured")
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    store.save_oidc_state(state, nonce)
    url = await oidc_client.build_authorize_url(state, nonce)
    return RedirectResponse(url)


@app.get("/auth/callback")
async def auth_callback(code: str = "", state: str = ""):
    if not oidc_client:
        raise HTTPException(status_code=400, detail="oidc_not_configured")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code_or_state")
    nonce = store.pop_oidc_state(state)
    if not nonce:
        raise HTTPException(status_code=400, detail="invalid_state")
    tokens = await oidc_client.exchange_code(code)
    id_token = tokens.get("id_token", "")
    if not id_token:
        raise HTTPException(status_code=400, detail="missing_id_token")
    oidc_client.verify_jwt(id_token, nonce=nonce)
    return {
        "ok": True,
        "access_token": tokens.get("access_token", ""),
        "id_token": id_token,
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in", 0),
    }

@app.post("/register")
async def register(
    request: RegisterRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    if not ALLOW_NEW_USERS and not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="registration_closed")
    store.add_user(request.user_id)
    return {"ok": True}


@app.post("/jobs")
async def create_job(
    request: JobRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    if not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    job_id = secrets.token_urlsafe(12)
    store.create_job(job_id, request.user_id, json.dumps(request.payload, ensure_ascii=False))
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/next")
async def next_job(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    job = store.fetch_next_job()
    if not job:
        return {"ok": True, "job": None}
    payload = json.loads(job["payload"])
    return {"ok": True, "job": {"job_id": job["job_id"], "user_id": job["user_id"], "payload": payload}}

@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "job": job}


@app.post("/jobs/{job_id}/result")
async def complete_job(
    job_id: str,
    request: JobResultRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    store.complete_job(job_id, request.result)
    return {"ok": True}


@app.post("/posts")
async def save_post(
    request: PostRecord,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    store.create_post(secrets.token_urlsafe(12), request.user_id, request.title, request.content)
    return {"ok": True}


@app.get("/posts/latest")
async def latest_post(
    user_id: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    post = store.get_latest_post(user_id)
    if not post:
        return {"ok": True, "post": None}
    return {"ok": True, "post": post}

@app.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    post = store.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "post": post}


@app.post("/naver/set")
async def naver_set(
    request: NaverSetRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    if not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    client_id = (request.client_id or NAVER_CLIENT_ID or "").strip()
    client_secret = (request.client_secret or NAVER_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="missing_client_info")
    if request.redirect_uri:
        redirect_uri = request.redirect_uri
    elif NAVER_REDIRECT_URI:
        redirect_uri = NAVER_REDIRECT_URI
    else:
        redirect_uri = f"{PUBLIC_BASE_URL.rstrip('/')}/naver/callback"
    store.upsert_naver_account(
        user_id=request.user_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        access_token="",
        refresh_token="",
        token_expires_at=0.0,
    )
    return {"ok": True, "redirect_uri": redirect_uri}


@app.get("/naver/link")
async def naver_link(
    user_id: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    if not store.is_user(user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    account = store.get_naver_account(user_id)
    if not account:
        raise HTTPException(status_code=400, detail="missing_client_info")
    state = secrets.token_urlsafe(16)
    store.save_oauth_state(state, user_id)
    url = naver_client.build_authorize_url(
        client_id=account["client_id"],
        redirect_uri=account["redirect_uri"],
        state=state,
    )
    return {"ok": True, "authorize_url": url}


@app.get("/naver/callback")
async def naver_callback(code: str = "", state: str = ""):
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code_or_state")
    user_id = store.pop_oauth_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="invalid_state")
    account = store.get_naver_account(user_id)
    if not account:
        raise HTTPException(status_code=400, detail="missing_client_info")
    token = await naver_client.exchange_code(
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        redirect_uri=account["redirect_uri"],
        code=code,
        state=state,
    )
    store.upsert_naver_account(
        user_id=user_id,
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        redirect_uri=account["redirect_uri"],
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_expires_at=token.expires_at(),
    )
    return {"ok": True}


@app.post("/naver/publish")
async def naver_publish(
    request: PublishRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _require_auth(x_api_key, authorization)
    account = store.get_naver_account(request.user_id)
    if not account or not account.get("access_token"):
        raise HTTPException(status_code=400, detail="naver_not_linked")
    title = request.title
    post = None
    if request.post_id:
        post = store.get_post(request.post_id)
        if not post:
            raise HTTPException(status_code=404, detail="not_found")
        if post["user_id"] != request.user_id:
            raise HTTPException(status_code=403, detail="forbidden")
    else:
        post = store.get_latest_post(request.user_id)
    if not title:
        if not post:
            raise HTTPException(status_code=400, detail="no_post")
        title = post["title"]
    content = post["content"] if post else ""
    if not content:
        raise HTTPException(status_code=400, detail="no_post")

    access_token = account["access_token"]
    now = time.time()
    if account["token_expires_at"] <= now:
        refreshed = await naver_client.refresh_token(
            client_id=account["client_id"],
            client_secret=account["client_secret"],
            refresh_token=account["refresh_token"],
        )
        if not refreshed:
            raise HTTPException(status_code=400, detail="refresh_failed")
        access_token = refreshed.access_token
        store.upsert_naver_account(
            user_id=request.user_id,
            client_id=account["client_id"],
            client_secret=account["client_secret"],
            redirect_uri=account["redirect_uri"],
            access_token=refreshed.access_token,
            refresh_token=refreshed.refresh_token,
            token_expires_at=refreshed.expires_at(),
        )

    response = await naver_client.write_post(
        access_token=access_token,
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        title=title,
        content=content,
    )
    return {"ok": True, "response": response}
