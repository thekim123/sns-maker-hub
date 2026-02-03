# SNS Maker Hub 사용자 가이드

이 가이드는 SNS Maker Hub를 일반 사용자가 사용하는 흐름을 설명합니다. 현재 제공되는 웹 화면은 상태 대시보드이며, 작업 생성/게시 등은 API 또는 별도 클라이언트(sns-maker)로 수행합니다.

## 준비물
- 허브 URL (예: https://hub.example.com)
- 본인 `user_id`
- 네이버 블로그 연동용 Client ID/Secret (게시 기능 사용 시)
- 운영자가 설정한 API 키 (필요한 경우)

## 대시보드 보기
1. 허브 프론트 주소로 접속합니다.
2. 로그인 화면에서 네이버 로그인으로 이동합니다.
3. 로그인 후 서버 상태, 작업 큐, 최근 작업/게시물을 확인합니다.
4. 문제가 있으면 `헬스체크 확인` 버튼으로 `/health`를 확인합니다.

로그인 토큰은 브라우저에 저장되며, 만료되면 다시 로그인해야 합니다.

## 사용자 등록
1. 운영자가 등록을 열어두었는지 확인합니다. (`ALLOW_NEW_USERS`가 `true`일 때 신규 등록 가능)
2. 아래 요청으로 계정을 등록합니다.
```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: <키가 있으면 입력>" \
  -d '{"user_id":"my-user","telegram_id":"my-telegram"}'
```

## 네이버 블로그 연동
1. 네이버 앱의 Client ID/Secret을 허브에 등록합니다.
```bash
curl -X POST http://localhost:8000/naver/set \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: <키가 있으면 입력>" \
  -d '{"user_id":"my-user","client_id":"...","client_secret":"..."}'
```
2. 인증 URL을 받아 브라우저에서 열고 연동을 완료합니다.
```bash
curl "http://localhost:8000/naver/link?user_id=my-user" -H "X-API-KEY: <키가 있으면 입력>"
```
3. `PUBLIC_BASE_URL`이 올바른 허브 주소로 설정되어 있어야 콜백이 정상 동작합니다.

## 작업 생성과 결과 확인
1. 작업 등록은 보통 `sns-maker` 클라이언트가 수행합니다.
2. 상태 확인:
```bash
curl "http://localhost:8000/jobs/<job_id>" -H "X-API-KEY: <키가 있으면 입력>"
```
3. 최신 게시물 확인:
```bash
curl "http://localhost:8000/posts/latest?user_id=my-user" -H "X-API-KEY: <키가 있으면 입력>"
```

## 네이버 게시
1. 최신 게시물을 네이버 블로그에 발행합니다.
```bash
curl -X POST http://localhost:8000/naver/publish \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: <키가 있으면 입력>" \
  -d '{"user_id":"my-user"}'
```

## 주의사항
- API 키가 설정된 경우 모든 요청에 `X-API-KEY`가 필요합니다.
- 서버 시간이 UTC ISO 포맷으로 반환됩니다.
- 현재 프론트는 조회용 대시보드입니다. 생성/게시 UI는 추후 확장 영역입니다.
