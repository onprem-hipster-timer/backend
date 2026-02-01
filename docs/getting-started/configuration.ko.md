# 구성

이 가이드는 Hipster Timer Backend에서 사용할 수 있는 모든 구성 옵션을 다룹니다.

## 환경 변수

구성은 `.env` 파일 또는 환경 변수를 통해 수행됩니다.

## 환경 모드

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ENVIRONMENT` | 런타임 환경 (`development`, `staging`, `production`) | `development` |

!!! warning "주의"
    **프로덕션 모드**: `ENVIRONMENT=production`일 때 다음 설정이 자동 적용됩니다:
    - `DEBUG` → `False`
    - `OPENAPI_URL` → `""` (비활성화)
    - `DOCS_URL` → `""` (비활성화)
    - `REDOC_URL` → `""` (비활성화)
    - `GRAPHQL_ENABLE_PLAYGROUND` → `False`
    - `GRAPHQL_ENABLE_INTROSPECTION` → `False`

## 핵심 설정

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DOCS_ENABLED` | 모든 API 문서 마스터 스위치 (Swagger, ReDoc, GraphQL Sandbox) | `True` |
| `DEBUG` | 디버그 모드 활성화 | `True` |
| `OPENAPI_URL` | OpenAPI 스키마 URL (빈 문자열로 비활성화) | `/openapi.json` |
| `DOCS_URL` | Swagger UI URL (빈 문자열로 비활성화) | `/docs` |
| `REDOC_URL` | ReDoc URL (빈 문자열로 비활성화) | `/redoc` |
| `LOG_LEVEL` | 로그 레벨 | `INFO` |
| `HOLIDAY_API_SERVICE_KEY` | 공공데이터포털 API 키 | - |
| `GRAPHQL_ENABLE_PLAYGROUND` | GraphQL Sandbox 활성화 | `True` |
| `GRAPHQL_ENABLE_INTROSPECTION` | GraphQL Introspection 허용 | `True` |

## 데이터베이스 구성

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | DB 연결 문자열 | `sqlite:///./schedule.db` |
| `POOL_SIZE` | 연결 풀 크기 | `5` |
| `MAX_OVERFLOW` | 최대 초과 연결 수 | `10` |
| `DB_POOL_PRE_PING` | 사용 전 연결 유효성 검사 | `True` |
| `DB_POOL_RECYCLE` | 연결 재활용 시간 (초) | `3600` |

**데이터베이스 URL 예시:**

```bash
# SQLite (개발)
DATABASE_URL=sqlite:///./schedule.db

# PostgreSQL (프로덕션)
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

## 인증 (OIDC)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `OIDC_ENABLED` | OIDC 인증 활성화 | `True` |
| `OIDC_ISSUER_URL` | OIDC Provider Issuer URL | - |
| `OIDC_AUDIENCE` | 토큰 검증용 Client ID | - |
| `OIDC_DISCOVERY_URL` | 사용자 지정 Discovery 엔드포인트 | 자동 생성 |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS 캐시 TTL | `3600` |

> 📖 **상세 가이드**: [인증 가이드](../guides/auth.ko.md)

## Rate Limiting

**HTTP Rate Limiting:**

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `RATE_LIMIT_ENABLED` | Rate Limiting 활성화 | `True` |
| `RATE_LIMIT_DEFAULT_WINDOW` | 기본 윈도우 크기 (초) | `60` |
| `RATE_LIMIT_DEFAULT_REQUESTS` | 윈도우당 기본 최대 요청 수 | `60` |

**WebSocket Rate Limiting:**

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `WS_RATE_LIMIT_ENABLED` | WebSocket Rate Limiting 활성화 | `True` |
| `WS_CONNECT_WINDOW` | 연결 제한 윈도우 (초) | `60` |
| `WS_CONNECT_MAX` | 윈도우당 최대 연결 수 | `10` |
| `WS_MESSAGE_WINDOW` | 메시지 제한 윈도우 (초) | `60` |
| `WS_MESSAGE_MAX` | 윈도우당 최대 메시지 수 | `120` |

> 📖 **상세 가이드**: [Rate Limiting 가이드](../development/rate-limit.ko.md)

## 프록시 설정 (Cloudflare / 신뢰할 수 있는 프록시)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `PROXY_FORCE` | 프록시 사용 강제 (직접 접근 차단) | `False` |
| `CF_ENABLED` | Cloudflare 프록시 모드 활성화 | `False` |
| `CF_IP_CACHE_TTL` | Cloudflare IP 목록 캐시 TTL (초) | `86400` |
| `TRUSTED_PROXY_IPS` | 신뢰할 수 있는 프록시 IP (쉼표 구분, CIDR 지원) | `""` |
| `ORIGIN_VERIFY_HEADER` | 출처 검증용 사용자 지정 헤더 이름 (선택) | `""` |
| `ORIGIN_VERIFY_SECRET` | 출처 검증 헤더의 시크릿 값 | `""` |

## CORS (Cross-Origin Resource Sharing)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `CORS_ALLOWED_ORIGINS` | 허용 Origin (쉼표 구분) | 개발 기본값 |
| `CORS_ALLOW_CREDENTIALS` | 자격 증명 허용 (쿠키 등) | `False` |
| `CORS_ALLOW_METHODS` | 허용 HTTP 메서드 (쉼표 구분) | `*` |
| `CORS_ALLOW_HEADERS` | 허용 헤더 (쉼표 구분) | `*` |

!!! warning "주의"
    **참고**: `CORS_ALLOWED_ORIGINS="*"`와 `CORS_ALLOW_CREDENTIALS=true`는 함께 사용할 수 없습니다.

## .env 파일 예시

```bash
# 환경
ENVIRONMENT=development

# 데이터베이스
DATABASE_URL=sqlite:///./schedule.db

# 인증 (개발 - 비활성화)
OIDC_ENABLED=false

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_WINDOW=60
RATE_LIMIT_DEFAULT_REQUESTS=60

# 로깅
LOG_LEVEL=INFO
```

## 프로덕션 구성

프로덕션 배포에 대해서는 [프로덕션 가이드](../deployment/production.ko.md)를 참조하세요.
