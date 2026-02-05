# Hub Internal Posts API

## 목적
- 워커/백엔드 간 내부 트래픽으로 게시글 저장을 처리합니다.
- 사용자 로그인 API와 내부 서비스 API를 분리합니다.

## 엔드포인트
- 내부 저장: `POST /internal/posts`
- 사용자 저장: `POST /posts` (사용자 JWT 전용)

## 내부 인증 방식
`POST /internal/posts`는 아래 중 하나가 필요합니다.

1. 권장: 서비스 토큰
- Header: `Authorization: Bearer <HUB_SERVICE_TOKEN>`

2. fallback: 내부 API 키
- Header: `X-Internal-API-Key: <HUB_INTERNAL_API_KEY>`

인증 실패 시:
- `401 service_auth_required`

## 요청 스펙
Request JSON:
```json
{
  "user_id": "naver:example-user",
  "title": "제목",
  "content": "본문"
}
```

Response:
```json
{ "ok": true }
```

오류:
- `403 not_registered`: `user_id`가 허브에 미등록인 경우

## 사용자 API 분리 규칙
`POST /posts`는 사용자 JWT만 허용합니다.
- `Authorization: Bearer <user_jwt>` 필요
- JWT `sub`와 요청 `user_id`가 다르면 `403 forbidden`
- 미로그인 시 `401 login_required`

## 환경 변수
```env
HUB_SERVICE_TOKEN=replace-with-strong-random-token
HUB_INTERNAL_API_KEY=
```

권장:
- 운영에서는 `HUB_SERVICE_TOKEN`을 기본 사용
- `HUB_INTERNAL_API_KEY`는 이전 호환/fallback 용도로만 사용

## 워커 연동 체크리스트
1. 허브 `.env`에 `HUB_SERVICE_TOKEN` 설정
2. 워커 `.env`에도 동일한 `HUB_SERVICE_TOKEN` 설정
3. 워커의 post 저장 경로를 `/internal/posts`로 사용
4. 저장 성공 여부를 워커 로그에서 확인

## 예시 호출
서비스 토큰:
```bash
curl -X POST http://localhost:8000/internal/posts \
  -H "Authorization: Bearer ${HUB_SERVICE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","title":"title","content":"content"}'
```

내부 API 키:
```bash
curl -X POST http://localhost:8000/internal/posts \
  -H "X-Internal-API-Key: ${HUB_INTERNAL_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","title":"title","content":"content"}'
```

## 감사 로그
`/internal/posts` 성공 시 아래 필드를 로그에 남깁니다.
- caller (`service_token` 또는 `internal_api_key`)
- endpoint (`/internal/posts`)
- user_id
- request_id (`X-Request-Id`, 없으면 `-`)
