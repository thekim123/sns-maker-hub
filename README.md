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

## 환경변수
- DATABASE_URL (기본: sqlite:///./hub.db)
- PUBLIC_BASE_URL (OAuth 콜백 URL)
- HUB_API_KEY (비워두면 인증 없음)
- ALLOW_NEW_USERS (false면 등록 제한)

## 주요 API
- POST /register
- POST /jobs
- GET /jobs/next
- POST /jobs/{job_id}/result
- POST /posts
- GET /posts/latest?user_id=...
- POST /naver/set
- GET /naver/link?user_id=...
- GET /naver/callback?code=...&state=...
- POST /naver/publish
