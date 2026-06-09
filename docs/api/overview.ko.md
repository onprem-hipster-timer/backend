# API 개요

Hipster Timer Backend는 세 가지 유형의 API를 제공합니다:

1. **REST API** - 전통적인 HTTP 엔드포인트
2. **GraphQL API** - 유연한 쿼리 언어
3. **WebSocket API** - 실시간 통신

## 기본 URL

모든 API는 `/v1` 접두사로 제공됩니다:

- **개발**: `http://localhost:2614/v1`
- **프로덕션**: `https://your-domain.com/v1`

## 인증

모든 API 엔드포인트(헬스체크 제외)는 OIDC Bearer 토큰 인증이 필요합니다:

```
Authorization: Bearer <access_token>
```

> 📖 **상세 가이드**: [인증 가이드](../guides/auth.ko.md)

## API 유형

### REST API

CRUD 작업을 위한 전통적인 RESTful 엔드포인트:

- **일정**: `/v1/schedules`
- **타이머**: `/v1/timers`
- **투두**: `/v1/todos`
- **태그**: `/v1/tags`
- **공휴일**: `/v1/holidays`

> 📖 **상세 가이드**: [REST API 레퍼런스](rest-api.ko.md)

### GraphQL API

효율적인 데이터 조회를 위한 유연한 쿼리 언어:

- **엔드포인트**: `/v1/graphql`
- **플레이그라운드**: `/v1/graphql` (개발 환경만)

> 📖 **상세 가이드**: [GraphQL 가이드](graphql.ko.md)

### WebSocket API

타이머 제어를 위한 실시간 통신:

- **엔드포인트**: `/v1/ws/timers`
- **프로토콜**: JSON 메시지를 사용하는 WebSocket

> 📖 **상세 가이드**: [WebSocket 가이드](websocket.ko.md)

## Rate Limiting

모든 API는 Rate Limiting이 적용됩니다:

- **기본값**: 사용자당 60초에 60회 요청
- **헤더**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

> 📖 **상세 가이드**: [Rate Limiting 가이드](../development/rate-limit.ko.md)

## 에러 처리

모든 API는 일관된 에러 응답을 반환합니다:

```json
{
  "detail": "Error message here"
}
```

일반적인 HTTP 상태 코드:

- `200` - 성공
- `201` - 생성됨
- `400` - 잘못된 요청
- `401` - 인증 필요
- `403` - 권한 없음
- `404` - 찾을 수 없음
- `429` - 요청 한도 초과
- `500` - 서버 내부 오류

## 데이터 형식

- **요청**: JSON (`Content-Type: application/json`)
- **응답**: JSON (`Content-Type: application/json`)
- **날짜**: ISO 8601 형식 (`2024-01-15T10:00:00Z`)
- **UUID**: 표준 UUID v4 형식

!!! warning "JSON 요청에는 `Content-Type` 헤더가 필수입니다"
    본문을 포함하는 요청(`POST`, `PUT`, `PATCH`)은 반드시 `Content-Type: application/json` 헤더를 포함해야 합니다.

    - **헤더 누락** → `422 Unprocessable Entity` (본문이 JSON으로 파싱되지 않음)
    - **잘못된 타입**(예: `text/plain`) → `415 Unsupported Media Type`
    - `application/json` 및 `application/*+json` 계열이 허용됩니다.
    - 본문이 없는 요청(`GET`, `DELETE` 등)은 영향받지 않습니다.

    `fetch`, `axios`, `httpx` 등 대부분의 HTTP 클라이언트는 JSON 전송 시 이 헤더를 자동으로 설정하지만, `curl --data`처럼 본문만 수동으로 보내는 경우 헤더를 직접 지정해야 합니다. (이 엄격한 검사는 FastAPI 0.132부터 기본 활성화되었습니다.)

## 대화형 문서 (테스트 링크)

로컬 개발 서버 실행 시 아래 주소로 접속해 API를 테스트할 수 있습니다.

| 항목 | 테스트 링크 (Development) |
|------|---------------------------|
| **Swagger UI** | [http://localhost:2614/docs](http://localhost:2614/docs) |
| **ReDoc** | [http://localhost:2614/redoc](http://localhost:2614/redoc) |
| **GraphQL Playground** | [http://localhost:2614/v1/graphql](http://localhost:2614/v1/graphql) |
| **WebSocket Playground** | [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground) |
| **WebSocket (타이머 엔드포인트)** | `ws://localhost:2614/v1/ws/timers` |

!!! warning "주의"
    위 링크는 개발 모드(`DOCS_ENABLED=true`)에서만 제공됩니다. WebSocket Playground는 JWT 입력 후 브라우저에서 바로 타이머 WebSocket API를 테스트할 수 있는 자체 제공 페이지입니다.
