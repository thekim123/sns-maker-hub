import time
from datetime import datetime, timezone
import json
import secrets
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import jwt
from pydantic import BaseModel
from app_config import (
    ALLOW_NEW_USERS,
    HUB_API_KEY,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_REDIRECT_URI,
    PUBLIC_BASE_URL,
    FRONTEND_BASE_URL,
    JWT_SECRET,
    JWT_TTL_SECONDS,
)
from hub_store import HubStore
from naver_client import NaverClient

app = FastAPI(title="SNS Maker Hub")
store = HubStore()
naver_client = NaverClient()
server_start = time.time()


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
    telegram_id: Optional[str] = None


class PostRecord(BaseModel):
    user_id: str
    title: str
    content: str


def _require_key(api_key: Optional[str]) -> None:
    if not HUB_API_KEY:
        return
    if api_key != HUB_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


def _verify_token(authorization: Optional[str]) -> Optional[str]:
    token = _extract_bearer(authorization)
    if not token:
        return None
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="jwt_not_configured")
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="unauthorized") from None
    return str(claims.get("sub", ""))


def _require_dashboard_auth(request: Request, api_key: Optional[str]) -> str:
    if HUB_API_KEY and api_key == HUB_API_KEY:
        return "api_key"
    user_id = _verify_token(request.headers.get("Authorization"))
    if user_id:
        return user_id
    if HUB_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")
    raise HTTPException(status_code=401, detail="login_required")


@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


def _format_ts(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


@app.get("/api/status")
async def status(request: Request, x_api_key: Optional[str] = Header(None)):
    _require_dashboard_auth(request, x_api_key)
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


@app.get("/auth/status")
async def auth_status(request: Request):
    user_id = _verify_token(request.headers.get("Authorization"))
    if not user_id:
        return {"ok": False}
    return {"ok": True, "user_id": user_id}


@app.post("/auth/logout")
async def auth_logout():
    return {"ok": True}


@app.get("/auth/naver/login")
async def auth_naver_login():
    state = secrets.token_urlsafe(16)
    store.save_oauth_state(state, "", "login")
    client_id = (NAVER_CLIENT_ID or "").strip()
    client_secret = (NAVER_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="missing_client_info")
    if NAVER_REDIRECT_URI:
        redirect_uri = NAVER_REDIRECT_URI
    else:
        redirect_uri = f"{PUBLIC_BASE_URL.rstrip('/')}/naver/callback"
    url = naver_client.build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
    )
    return RedirectResponse(url)



@app.post("/register")
async def register(
    request: RegisterRequest,
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    if not ALLOW_NEW_USERS and not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="registration_closed")
    store.add_user(request.user_id)
    if request.telegram_id:
        store.set_telegram_id(request.user_id, request.telegram_id)
    return {"ok": True}


@app.post("/jobs")
async def create_job(
    request: JobRequest,
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    if not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    job_id = secrets.token_urlsafe(12)
    store.create_job(job_id, request.user_id, json.dumps(request.payload, ensure_ascii=False))
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/next")
async def next_job(
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    job = store.fetch_next_job()
    if not job:
        return {"ok": True, "job": None}
    payload = json.loads(job["payload"])
    return {"ok": True, "job": {"job_id": job["job_id"], "user_id": job["user_id"], "payload": payload}}

@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "job": job}


@app.post("/jobs/{job_id}/result")
async def complete_job(
    job_id: str,
    request: JobResultRequest,
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    store.complete_job(job_id, request.result)
    return {"ok": True}


@app.post("/posts")
async def save_post(
    request: PostRecord,
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
    store.create_post(secrets.token_urlsafe(12), request.user_id, request.title, request.content)
    return {"ok": True}


@app.get("/posts/latest")
async def latest_post(
    user_id: str,
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
    post = store.get_latest_post(user_id)
    if not post:
        return {"ok": True, "post": None}
    return {"ok": True, "post": post}

@app.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
    post = store.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="not_found")
    return {"ok": True, "post": post}


@app.post("/naver/set")
async def naver_set(
    request: NaverSetRequest,
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
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
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
    if not store.is_user(user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    account = store.get_naver_account(user_id)
    if not account:
        raise HTTPException(status_code=400, detail="missing_client_info")
    state = secrets.token_urlsafe(16)
    store.save_oauth_state(state, user_id, "link")
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
    state_info = store.pop_oauth_state(state)
    if not state_info:
        raise HTTPException(status_code=400, detail="invalid_state")
    flow = state_info.get("flow", "")
    user_id = state_info.get("user_id", "")
    account = store.get_naver_account(user_id) if user_id else None
    if not account:
        client_id = (NAVER_CLIENT_ID or "").strip()
        client_secret = (NAVER_CLIENT_SECRET or "").strip()
        if not client_id or not client_secret:
            raise HTTPException(status_code=400, detail="missing_client_info")
        redirect_uri = NAVER_REDIRECT_URI or f"{PUBLIC_BASE_URL.rstrip('/')}/naver/callback"
    else:
        client_id = account["client_id"]
        client_secret = account["client_secret"]
        redirect_uri = account["redirect_uri"]
    token = await naver_client.exchange_code(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        code=code,
        state=state,
    )
    if flow == "login":
        profile = await naver_client.get_profile(token.access_token)
        naver_id = ""
        if isinstance(profile, dict):
            response = profile.get("response") if isinstance(profile.get("response"), dict) else {}
            naver_id = str(response.get("id", "")).strip()
        if not naver_id:
            raise HTTPException(status_code=400, detail="missing_naver_id")
        mapped_user_id = store.get_user_by_naver_id(naver_id)
        user_id = mapped_user_id or f"naver:{naver_id}"
        if not store.is_user(user_id):
            if not ALLOW_NEW_USERS:
                raise HTTPException(status_code=403, detail="registration_closed")
            store.add_user(user_id)
        store.link_naver_identity(naver_id, user_id)
    store.upsert_naver_account(
        user_id=user_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_expires_at=token.expires_at(),
    )
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="jwt_not_configured")
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    access_token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    if FRONTEND_BASE_URL:
        html = f"""
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>로그인 완료</title>
  </head>
  <body>
    <script>
      try {{
        localStorage.setItem("hub_access_token", {json.dumps(access_token)});
        localStorage.setItem("hub_token_expires_at", String(Date.now() + {int(JWT_TTL_SECONDS)} * 1000));
      }} catch (e) {{}}
      window.location.replace({json.dumps(FRONTEND_BASE_URL)});
    </script>
    <p>로그인 완료. 이동 중...</p>
  </body>
</html>
"""
        return HTMLResponse(html)
    return {"ok": True, "access_token": access_token, "expires_in": JWT_TTL_SECONDS}


@app.post("/naver/publish")
async def naver_publish(
    request: PublishRequest,
    request_obj: Request,
    x_api_key: Optional[str] = Header(None),
):
    _require_dashboard_auth(request_obj, x_api_key)
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
