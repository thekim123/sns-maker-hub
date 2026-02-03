# SNS Maker Hub 개발자 문서

## 개요
- FastAPI 기반 허브 서버입니다.
- 로컬 LLM 워커(예: `sns-maker`)가 `/jobs/next`를 폴링해 작업을 처리합니다.
- React 대시보드는 별도 레포(`sns-maker-hub-frontend`)에서 `/api/status`를 조회합니다.

## 로컬 실행
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 환경변수
- `DATABASE_URL`: 기본 `sqlite:///./hub.db`
- `PUBLIC_BASE_URL`: OAuth 콜백 기준 URL
- `HUB_API_KEY`: 비어있으면 인증 없음
- `ALLOW_NEW_USERS`: `true`일 때 신규 등록 허용
- `FRONTEND_BASE_URL`: 네이버 로그인 완료 후 리다이렉트할 프론트 URL
- `JWT_SECRET`: 로그인 JWT 서명 키
- `JWT_TTL_SECONDS`: 로그인 JWT 만료 시간 (초)

## 인증
- `HUB_API_KEY`가 설정되어 있으면 모든 API 요청에 `X-API-KEY` 필요

## 네이버 로그인
- `GET /auth/naver/login`으로 네이버 OAuth 로그인 시작
- `GET /naver/callback`에서 토큰을 저장하고 JWT를 발급
- 프론트는 `hub_access_token`을 저장하고 `Authorization: Bearer <token>`로 요청
- `GET /auth/status`로 로그인 여부 확인

## 데이터 모델 (SQLite)
- `hub_users`: 허브 등록 사용자
- `oauth_states`: 네이버 OAuth 상태값
- `naver_accounts`: 네이버 연동 정보
- `jobs`: 큐 작업
- `posts`: 생성된 게시물

## API 요약
- `GET /health`: 헬스체크
- `GET /api/status`: 대시보드 집계
- `POST /register`: 사용자 등록
- `POST /jobs`: 작업 등록
- `GET /jobs/next`: 워커가 다음 작업 가져오기
- `GET /jobs/{job_id}`: 작업 상태 조회
- `POST /jobs/{job_id}/result`: 작업 완료 업로드
- `POST /posts`: 게시물 저장
- `GET /posts/latest`: 사용자 최신 게시물
- `POST /naver/set`: 네이버 앱 키 등록
- `GET /naver/link`: 네이버 OAuth 링크 생성
- `GET /naver/callback`: 네이버 OAuth 콜백
- `POST /naver/publish`: 네이버 블로그 게시

## 작업 흐름
1. 클라이언트가 `/jobs`로 작업 등록
2. 워커가 `/jobs/next`로 작업 가져감
3. 처리 결과를 `/jobs/{id}/result`로 업로드
4. 생성된 글을 `/posts`에 저장

## 네이버 OAuth/게시 흐름
1. `/naver/set`으로 Client ID/Secret 등록
2. `/naver/link`에서 authorize URL 수신
3. 사용자가 URL에서 인증 완료
4. `/naver/callback`이 토큰을 저장
5. `/naver/publish`로 최신 게시물을 발행

## 대시보드
- `/api/status`는 최근 작업, 큐 상태, 최신 게시물을 반환합니다.
- 시간 필드는 UTC ISO 문자열입니다.

## 배포
- `deploy/nginx/sns-maker.conf` 예시를 사용하면 `/`는 React 정적 파일, `/api` `/health` `/naver`는 FastAPI로 프록시합니다.
- 단일 EC2 또는 ALB + ACM 구성에서 사용 가능합니다.

## 보안 및 운영 팁
- 운영 환경에서는 `HUB_API_KEY`를 필수로 설정
- `ALLOW_NEW_USERS=false`로 공개 등록 차단
- SQLite 사용 시 `hub.db` 백업 필요, RDS로 대체 가능
