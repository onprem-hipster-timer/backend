<!-- # 🚀 Production Deployment Guide <작성중>

Hipster Timer Backend를 프로덕션 환경에 배포하기 위한 권장 설정 가이드입니다.

---

## 📋 목차

- [개요](#개요)
- [환경 설정](#환경-설정)
- [데이터베이스 설정](#데이터베이스-설정)
- [인증 설정 (OIDC)](#인증-설정-oidc)
- [Rate Limiting](#rate-limiting)
- [CORS 설정](#cors-설정)
- [Docker 배포](#docker-배포)
- [보안 체크리스트](#보안-체크리스트)
- [환경 변수 요약표](#환경-변수-요약표)

---

## 개요

프로덕션 환경 배포 시 반드시 고려해야 할 핵심 사항:

| 항목 | 개발 환경 | 프로덕션 환경 |
|------|-----------|---------------|
| 데이터베이스 | SQLite | **PostgreSQL** |
| 인증 | 비활성화 가능 | **OIDC 필수** |
| API 문서 | 활성화 | **비활성화** |
| 디버그 모드 | 활성화 | **비활성화** |
| CORS | 모든 origin 허용 | **특정 도메인만 허용** |
| WebSocket | `ws://` (local dev only) | **`wss://` required** (encrypted) |

---

## 환경 설정

### ENVIRONMENT 변수

`ENVIRONMENT=production`으로 설정하면 보안 관련 설정이 자동으로 적용됩니다:

```bash
ENVIRONMENT=production
```

**자동 적용되는 설정:**

| 설정 | 프로덕션 값 | 설명 |
|------|-------------|------|
| `DEBUG` | `False` | 디버그 모드 비활성화 |
| `OPENAPI_URL` | `""` (빈 문자열) | OpenAPI 스키마 비활성화 |
| `DOCS_URL` | `""` (빈 문자열) | Swagger UI 비활성화 |
| `REDOC_URL` | `""` (빈 문자열) | ReDoc 비활성화 |
| `GRAPHQL_ENABLE_PLAYGROUND` | `False` | GraphQL Sandbox 비활성화 |
| `GRAPHQL_ENABLE_INTROSPECTION` | `False` | GraphQL Introspection 비활성화 |

> ⚠️ 이 설정들은 `ENVIRONMENT=production`일 때 자동으로 적용되며, 개별적으로 다른 값을 설정해도 무시됩니다.

### API 문서 수동 비활성화

프로덕션이 아닌 환경에서도 개별적으로 API 문서를 비활성화할 수 있습니다 (FastAPI 공식 문서 권장 방식):

```bash
# 모든 API 문서 비활성화
OPENAPI_URL="" DOCS_URL="" REDOC_URL="" uvicorn app.main:app

# Swagger UI만 비활성화 (ReDoc은 유지)
DOCS_URL="" uvicorn app.main:app
```

---

## 데이터베이스 설정

### PostgreSQL 권장

프로덕션 환경에서는 **PostgreSQL**을 사용하세요. SQLite는 개발 및 테스트 용도로만 사용해야 합니다.

```bash
# PostgreSQL 연결 문자열
DATABASE_URL=postgresql://username:password@hostname:5432/database_name
```

### 연결 풀 설정

PostgreSQL 사용 시 연결 풀 최적화 설정:

```bash
# 연결 풀 크기 (동시 연결 수)
POOL_SIZE=10

# 풀이 가득 찼을 때 추가로 허용할 연결 수
MAX_OVERFLOW=20

# 연결 유효성 검사 (권장: True)
DB_POOL_PRE_PING=true

# 연결 재활용 시간 (초, 기본: 3600)
DB_POOL_RECYCLE=3600
```

**트래픽에 따른 권장 설정:**

| 트래픽 수준 | POOL_SIZE | MAX_OVERFLOW |
|-------------|-----------|--------------|
| 소규모 (< 100 RPS) | 5 | 10 |
| 중규모 (100-500 RPS) | 10 | 20 |
| 대규모 (> 500 RPS) | 20 | 40 |

---

## 인증 설정 (OIDC)

프로덕션 환경에서는 **반드시** OIDC 인증을 활성화하세요.

### 필수 환경 변수

```bash
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://your-auth-provider.com/realms/your-realm
OIDC_AUDIENCE=your-client-id
```

### Provider별 설정 예시

**Keycloak:**

```bash
OIDC_ISSUER_URL=https://keycloak.example.com/realms/myrealm
OIDC_AUDIENCE=hipster-timer-frontend
```

**Auth0:**

```bash
OIDC_ISSUER_URL=https://your-tenant.auth0.com/
OIDC_AUDIENCE=https://api.hipster-timer.com
```

**Google:**

```bash
OIDC_ISSUER_URL=https://accounts.google.com
OIDC_AUDIENCE=your-google-client-id.apps.googleusercontent.com
```

### JWKS 캐시 설정

```bash
# JWKS 캐시 TTL (기본: 3600초 = 1시간)
OIDC_JWKS_CACHE_TTL_SECONDS=3600
```

> 📖 **상세 가이드**: [Authentication Guide](../guides/auth.ko.md)

---

## Rate Limiting

프로덕션 환경에서는 Rate Limiting을 **반드시 활성화**하세요.

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_WINDOW=60    # 60초 윈도우
RATE_LIMIT_DEFAULT_REQUESTS=60  # 윈도우당 최대 60 요청
```

**사용 패턴에 따른 권장 설정:**

| 사용 패턴 | WINDOW | REQUESTS |
|-----------|--------|----------|
| 일반 웹앱 | 60 | 60 |
| API 중심 서비스 | 60 | 120 |
| 제한적 공개 API | 60 | 30 |

> 📖 **상세 가이드**: [Rate Limiting Guide](../development/rate-limit.en.md)

---

## CORS 설정

### 프로덕션 권장 설정

프로덕션에서는 **와일드카드(`*`) 사용을 피하고** 명시적으로 도메인을 지정하세요.

```bash
# 허용할 도메인 + WebSocket origin (콤마로 구분)
# HTTPS + wss:// required (ws:// is prohibited in production)
CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com,wss://api.example.com

# 자격 증명(쿠키, Authorization 헤더) 허용
CORS_ALLOW_CREDENTIALS=true

# 허용할 HTTP 메서드
CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS

# 허용할 헤더
CORS_ALLOW_HEADERS=Authorization,Content-Type
```

> ⚠️ **주의**: `CORS_ALLOWED_ORIGINS="*"`와 `CORS_ALLOW_CREDENTIALS=true`는 **함께 사용할 수 없습니다**. credentials를 허용하려면 반드시 특정 origin을 지정해야 합니다.

> ⚠️ **WebSocket**: 타이머 등 실시간 기능이 WebSocket(`/v1/ws/timers`)을 사용합니다. WebSocket 연결이 동작하려면 `CORS_ALLOWED_ORIGINS`에 **반드시** WebSocket URL을 포함해야 합니다. 프로덕션에서는 **`wss://`(암호화)만 사용**하세요. `ws://`는 평문 전송이므로 프로덕션에서 사용 금지입니다.

---

## Docker 배포

### GHCR에서 이미지 받기

```bash
# 최신 이미지
docker pull ghcr.io/onprem-hipster-timer/backend:latest

# 특정 버전
docker pull ghcr.io/onprem-hipster-timer/backend:v2026.01.13-f81a7c0
```

### 단일 컨테이너 실행

```bash
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e ENVIRONMENT=production \
  -e DATABASE_URL=postgresql://user:password@db-host:5432/hipster_timer \
  -e OIDC_ENABLED=true \
  -e OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm \
  -e OIDC_AUDIENCE=hipster-timer-frontend \
  -e CORS_ALLOWED_ORIGINS=https://app.example.com,wss://api.example.com \
  -e CORS_ALLOW_CREDENTIALS=true \
  ghcr.io/onprem-hipster-timer/backend:latest
```

### Docker Compose (PostgreSQL 포함)

프로덕션용 `compose.production.yaml` 예시:

```yaml
services:
  backend:
    image: ghcr.io/onprem-hipster-timer/backend:latest
    restart: always
    ports:
      - "2614:2614"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://hipster:${DB_PASSWORD}@db:5432/hipster_timer
      - OIDC_ENABLED=true
      - OIDC_ISSUER_URL=${OIDC_ISSUER_URL}
      - OIDC_AUDIENCE=${OIDC_AUDIENCE}
      - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS}
      - CORS_ALLOW_CREDENTIALS=true
      - RATE_LIMIT_ENABLED=true
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    restart: always
    environment:
      - POSTGRES_USER=hipster
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=hipster_timer
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "hipster"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres-data:
```

**.env 파일:**

```bash
DB_PASSWORD=your-secure-password-here
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm
OIDC_AUDIENCE=hipster-timer-frontend
CORS_ALLOWED_ORIGINS=https://app.example.com,wss://api.example.com
```

**실행:**

```bash
docker compose -f compose.production.yaml up -d
```

---

## 보안 체크리스트

프로덕션 배포 전 반드시 확인하세요:

### 필수 항목

- [ ] `ENVIRONMENT=production` 설정
- [ ] PostgreSQL 데이터베이스 사용
- [ ] OIDC 인증 활성화 (`OIDC_ENABLED=true`)
- [ ] OIDC Issuer URL 및 Audience 설정
- [ ] CORS에서 와일드카드(`*`) 제거, 명시적 도메인 지정
- [ ] CORS에 WebSocket origin(`wss://your-api-domain`) 포함
- [ ] Rate Limiting 활성화
- [ ] HTTPS를 통한 접근 (리버스 프록시 설정)
- [ ] WebSocket은 **`wss://`만 사용** (프로덕션에서 `ws://` 금지)

### 권장 항목

- [ ] 데이터베이스 연결 풀 최적화
- [ ] 로그 레벨 설정 (`LOG_LEVEL=WARNING` 또는 `ERROR`)
- [ ] 컨테이너 헬스체크 설정
- [ ] 자동 재시작 정책 설정 (`restart: always`)
- [ ] 데이터베이스 백업 정책 수립
- [ ] 모니터링/알림 시스템 연동

### 보안 고려사항

- [ ] 데이터베이스 비밀번호는 환경 변수 또는 시크릿 매니저 사용
- [ ] 컨테이너는 non-root 사용자로 실행 (기본 설정됨)
- [ ] 불필요한 포트 노출 금지
- [ ] 정기적인 이미지 업데이트 (보안 패치)

---

## 환경 변수 요약표

### 필수 환경 변수 (프로덕션)

| 변수 | 프로덕션 권장값 | 설명 |
|------|-----------------|------|
| `ENVIRONMENT` | `production` | 프로덕션 모드 활성화 |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL 연결 문자열 |
| `OIDC_ENABLED` | `true` | OIDC 인증 활성화 |
| `OIDC_ISSUER_URL` | Provider URL | OIDC Provider Issuer URL |
| `OIDC_AUDIENCE` | Client ID | 토큰 검증용 Client ID |
| `CORS_ALLOWED_ORIGINS` | 명시적 도메인 + `wss://` | 허용할 프론트엔드/WebSocket origin (예: `https://app.example.com,wss://api.example.com`) |

### 선택 환경 변수

| 변수 | 기본값 | 프로덕션 권장값 | 설명 |
|------|--------|-----------------|------|
| `POOL_SIZE` | `5` | `10` | DB 연결 풀 크기 |
| `MAX_OVERFLOW` | `10` | `20` | 초과 연결 수 |
| `DB_POOL_PRE_PING` | `true` | `true` | 연결 유효성 검사 |
| `DB_POOL_RECYCLE` | `3600` | `3600` | 연결 재활용 시간(초) |
| `LOG_LEVEL` | `INFO` | `WARNING` | 로그 레벨 |
| `OPENAPI_URL` | `/openapi.json` | `""` (자동) | OpenAPI 스키마 URL |
| `DOCS_URL` | `/docs` | `""` (자동) | Swagger UI URL |
| `REDOC_URL` | `/redoc` | `""` (자동) | ReDoc URL |
| `RATE_LIMIT_ENABLED` | `true` | `true` | Rate Limit 활성화 |
| `RATE_LIMIT_DEFAULT_WINDOW` | `60` | `60` | 윈도우 크기(초) |
| `RATE_LIMIT_DEFAULT_REQUESTS` | `60` | `60` | 윈도우당 요청 수 |
| `CORS_ALLOW_CREDENTIALS` | `false` | `true` | 자격 증명 허용 |
| `CORS_ALLOW_METHODS` | `*` | 명시적 지정 | 허용 HTTP 메서드 |
| `CORS_ALLOW_HEADERS` | `*` | 명시적 지정 | 허용 헤더 |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | `3600` | `3600` | JWKS 캐시 TTL |

### 프로덕션 .env 파일 예시

```bash
# 환경
ENVIRONMENT=production

# 데이터베이스
DATABASE_URL=postgresql://hipster:secure-password@localhost:5432/hipster_timer
POOL_SIZE=10
MAX_OVERFLOW=20

# 인증
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm
OIDC_AUDIENCE=hipster-timer-frontend

# CORS (HTTP/HTTPS + WebSocket wss:// required)
CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com,wss://api.example.com
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
CORS_ALLOW_HEADERS=Authorization,Content-Type

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_WINDOW=60
RATE_LIMIT_DEFAULT_REQUESTS=60

# 로깅
LOG_LEVEL=WARNING
```

---

## 관련 문서

- [Authentication Guide](../guides/auth.ko.md) - 프론트엔드 인증 통합 가이드
- [Rate Limiting Guide](../development/rate-limit.en.md) - Rate Limiting 상세 가이드
