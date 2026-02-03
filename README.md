# sns-maker-hub

AWS용 얇은 서버 (OAuth/DB/Jobs). 로컬 LLM 워커가 폴링으로 작업을 가져갑니다.

## 구성
- FastAPI API 서버
- SQLite (기본) / RDS로 교체 가능
- 네이버 OAuth/게시 엔드포인트 포함

## 실행
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Web dashboard (React)

The dashboard lives in `frontend/` and expects the API at `/api`.

```powershell
cd frontend
npm install
npm run dev
```

To build static files for Nginx:

```powershell
cd frontend
npm run build
```

Copy `frontend/dist` to `/var/www/sns-maker-hub` (or your chosen web root).

## Nginx (single EC2: web + API)

An example Nginx config is in `deploy/nginx/sns-maker.conf`. It serves the React app and proxies
`/api`, `/health`, and `/naver` to FastAPI on port 8000.

## 환경변수
- DATABASE_URL (기본: sqlite:///./hub.db)
- PUBLIC_BASE_URL (OAuth 콜백 URL)
- HUB_API_KEY (비워두면 인증 없음)
- ALLOW_NEW_USERS (false면 등록 제한)

## 주요 API
- POST /register
- POST /jobs
- GET /jobs/next
- GET /jobs/{job_id}
- POST /jobs/{job_id}/result
- POST /posts
- GET /posts/latest?user_id=...
- POST /naver/set
- GET /naver/link?user_id=...
- GET /naver/callback?code=...&state=...
- POST /naver/publish
- GET /api/status

## 요청/응답 예시

### 1) 작업 등록
Request:
```json
POST /jobs
{
  "user_id": "123456",
  "payload": {
    "task": "generate",
    "style": "insta",
    "caption": "설명",
    "images_b64": ["<base64>"]
  }
}
```
Response:
```json
{ "ok": true, "job_id": "abc123" }
```

### 2) 워커가 작업 가져가기
Request:
```
GET /jobs/next
```
Response:
```json
{
  "ok": true,
  "job": {
    "job_id": "abc123",
    "user_id": "123456",
    "payload": { "task": "generate", "style": "insta", "images_b64": ["<base64>"] }
  }
}
```

### 3) 작업 완료 업로드
Request:
```json
POST /jobs/abc123/result
{ "result": "생성된 글 ..." }
```
Response:
```json
{ "ok": true }
```

### 4) 상태 조회
Request:
```
GET /jobs/abc123
```
Response:
```json
{
  "ok": true,
  "job": {
    "job_id": "abc123",
    "status": "done",
    "result": "생성된 글 ...",
    "updated_at": 1717000000.0
  }
}
```
