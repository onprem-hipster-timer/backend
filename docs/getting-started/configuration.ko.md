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
| `HOLIDAY_API_BASE_URL` | 공휴일(천문연구원 특일정보) API 베이스 URL | `https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService` |
| `GRAPHQL_ENABLE_PLAYGROUND` | GraphQL Sandbox 활성화 | `True` |
| `GRAPHQL_ENABLE_INTROSPECTION` | GraphQL Introspection 허용 | `True` |

!!! warning "이미 배포된 버전의 HTTPS 적용"
    `HOLIDAY_API_BASE_URL` 기본값은 `https://`이지만, **현재 배포 태그(`v2026.06.12-cfa3200`)까지의 빌드는 `http://`를 기본값으로 포함**합니다. 해당 버전을 운영 중이라면 API 키(`HOLIDAY_API_SERVICE_KEY`)와 응답이 평문으로 전송되는 것을 막기 위해, 빌드를 갱신하기 전까지 환경변수로 HTTPS 주소를 직접 주입하세요.

    ```bash
    HOLIDAY_API_BASE_URL=https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService
    ```

## 데이터베이스 구성

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | DB 연결 문자열 | `sqlite:///./schedule.db` |
| `POOL_SIZE` | 연결 풀 크기 | `5` |
| `MAX_OVERFLOW` | 최대 초과 연결 수 | `10` |
| `DB_POOL_PRE_PING` | 사용 전 연결 유효성 검사 | `True` |
| `DB_POOL_RECYCLE` | 연결 재활용 시간 (초) | `3600` |
| `DB_KEEPALIVE_INTERVAL_SECONDS` | 주기적 keep-alive `SELECT 1` 실행 간격 (초). `0` 이하면 비활성화 | `0` |

**데이터베이스 URL 예시:**

```bash
# SQLite (개발)
DATABASE_URL=sqlite:///./schedule.db

# PostgreSQL (프로덕션)
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

!!! tip "DB Keep-Alive (유휴 자동 정지 방지)"
    일부 관리형/서버리스 데이터베이스는 일정 시간 트래픽이 없으면 인스턴스를
    자동으로 일시 정지시키거나 유휴 연결을 끊습니다. `DB_KEEPALIVE_INTERVAL_SECONDS`를
    양수(초)로 설정하면 해당 주기마다 가벼운 `SELECT 1` 쿼리를 실행해 DB를 깨운 상태로
    유지합니다. `0`(기본값) 또는 음수면 비활성화됩니다.

    초 변환표:

    | 주기 | 초 |
    |------|----|
    | 5분 | `300` |
    | 1시간 | `3600` |
    | 6시간 | `21600` |
    | 12시간 | `43200` |
    | 1일 | `86400` |
    | (참고) 7일 = Supabase 정지 기준 | `604800` |

    주기는 정지 기준(7일)보다 충분히 짧게 두세요. 앱 재시작·장애로 한 번 놓쳐도
    여유가 있도록 `86400`(1일) 정도를 권장합니다.

## 인증 (OIDC)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `OIDC_ENABLED` | OIDC 인증 활성화 | `True` |
| `OIDC_ISSUER_URL` | OIDC Provider Issuer URL | - |
| `OIDC_AUDIENCE` | 토큰 검증용 Client ID | - |
| `OIDC_DISCOVERY_URL` | 사용자 지정 Discovery 엔드포인트 | 자동 생성 |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS 캐시 TTL | `3600` |

> 📖 **상세 가이드**: [인증 가이드](../guides/auth.ko.md)

!!! note "검증 이메일 저장"
    토큰에 `email_verified=true`와 `email` 클레임이 있으면, 백엔드는 이메일 기반 친구 추가를 위해
    정규화한 검증 이메일을 저장합니다. 이 값은 친구 추가 매칭용 인덱스로만 사용하며 사용자 검색,
    목록, API 응답에는 노출하지 않습니다. 별도 HMAC secret 설정은 두지 않습니다.

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
    `CORS_ALLOWED_ORIGINS="*"`와 `CORS_ALLOW_CREDENTIALS=true`는 함께 사용할 수 없습니다.

!!! tip "팁"
    WebSocket을 사용하는 경우 `CORS_ALLOWED_ORIGINS`에 `ws://` 또는 `wss://` URL을 반드시 포함하세요.

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
