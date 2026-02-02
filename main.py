from datetime import datetime
import json
import secrets
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from app_config import ALLOW_NEW_USERS, HUB_API_KEY, PUBLIC_BASE_URL
from hub_store import HubStore
from naver_client import NaverClient

app = FastAPI(title="SNS Maker Hub")
store = HubStore()
naver_client = NaverClient()


class JobRequest(BaseModel):
    user_id: str
    payload: dict


class JobResultRequest(BaseModel):
    result: str


class NaverSetRequest(BaseModel):
    user_id: str
    client_id: str
    client_secret: str
    redirect_uri: Optional[str] = None


class PublishRequest(BaseModel):
    user_id: str
    title: Optional[str] = None


class RegisterRequest(BaseModel):
    user_id: str


class PostRecord(BaseModel):
    user_id: str
    title: str
    content: str


def _require_key(api_key: Optional[str]) -> None:
    if not HUB_API_KEY:
        return
    if api_key != HUB_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


@app.post("/register")
async def register(request: RegisterRequest, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    if not ALLOW_NEW_USERS and not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="registration_closed")
    store.add_user(request.user_id)
    return {"ok": True}


@app.post("/jobs")
async def create_job(request: JobRequest, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    if not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    job_id = secrets.token_urlsafe(12)
    store.create_job(job_id, request.user_id, json.dumps(request.payload, ensure_ascii=False))
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/next")
async def next_job(x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    job = store.fetch_next_job()
    if not job:
        return {"ok": True, "job": None}
    payload = json.loads(job["payload"])
    return {"ok": True, "job": {"job_id": job["job_id"], "user_id": job["user_id"], "payload": payload}}


@app.post("/jobs/{job_id}/result")
async def complete_job(job_id: str, request: JobResultRequest, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    store.complete_job(job_id, request.result)
    return {"ok": True}


@app.post("/posts")
async def save_post(request: PostRecord, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    store.create_post(secrets.token_urlsafe(12), request.user_id, request.title, request.content)
    return {"ok": True}


@app.get("/posts/latest")
async def latest_post(user_id: str, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    post = store.get_latest_post(user_id)
    if not post:
        return {"ok": True, "post": None}
    return {"ok": True, "post": post}


@app.post("/naver/set")
async def naver_set(request: NaverSetRequest, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    if not store.is_user(request.user_id):
        raise HTTPException(status_code=403, detail="not_registered")
    redirect_uri = request.redirect_uri or f"{PUBLIC_BASE_URL.rstrip('/')}/naver/callback"
    store.upsert_naver_account(
        user_id=request.user_id,
        client_id=request.client_id,
        client_secret=request.client_secret,
        redirect_uri=redirect_uri,
        access_token="",
        refresh_token="",
        token_expires_at=0.0,
    )
    return {"ok": True, "redirect_uri": redirect_uri}


@app.get("/naver/link")
async def naver_link(user_id: str, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
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
async def naver_publish(request: PublishRequest, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)
    account = store.get_naver_account(request.user_id)
    if not account or not account.get("access_token"):
        raise HTTPException(status_code=400, detail="naver_not_linked")
    title = request.title
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
