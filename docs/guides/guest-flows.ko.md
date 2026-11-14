# 게스트 계정 흐름도

게스트 계정의 요청이 어디를 지나고, 각 지점에서 무엇을 확인하는지를 그림으로 정리한 문서입니다. API와 규칙은 [게스트 계정 가이드](guest.ko.md), 설정은 [게스트 계정 설정 (Kratos)](../deployment/kratos-guest.ko.md)에 있습니다.

각 그림 아래의 표는 그 확인을 하는 코드와 그 동작을 지키는 테스트의 위치입니다.

## 1. 구성 요소와 경계

화살표의 글자는 그 구간에서 상대를 확인하는 수단입니다.

```mermaid
flowchart LR
    C["클라이언트<br/>(게스트·회원)"]
    P["앞단 프록시<br/>(선택)"]

    subgraph BE["backend"]
        MW["미들웨어<br/>출처 확인 → 토큰 검증 → 요청 한도"]
        G["/v1/guests/*"]
        AP["/auth/* 프록시"]
        HK["/internal/kratos/hooks/*"]
        DB[("guest 테이블<br/>identity id · 리소스 · 이름")]
    end

    subgraph KR["Kratos"]
        KP["공개 API"]
        KA["admin API"]
        KS[("identity<br/>handle · 비밀번호 · 이름")]
    end

    TS["Cloudflare Turnstile<br/>siteverify"]

    C -->|"HTTPS"| P
    P -->|"출처 확인 헤더<br/>방문자 주소"| MW
    MW --> G
    MW --> AP
    G -->|"비밀 키 + 토큰"| TS
    G -->|"내부 망"| KA
    G --- DB
    AP -->|"세션 토큰"| KP
    KP -->|"X-Kratos-Hook-Key"| HK
    HK --- DB
    KP --- KS
    KA --- KS
```

| 구간 | 확인 수단 | 없거나 틀리면 |
|------|-----------|---------------|
| 클라이언트 → `/v1/guests/lookup`, `POST /v1/guests` | 없음(인증 없는 경로). 생성은 Turnstile 토큰 | 생성 `403`/`422` |
| 클라이언트 → 게스트 경로 | 게스트 JWT (`Authorization: Bearer`) | `401`/`403` |
| 클라이언트 → `/auth/*` | Kratos 세션 토큰 (`X-Session-Token`) 또는 없음(로그인 전) | Kratos가 판정 |
| 앞단 프록시 → backend | `ORIGIN_VERIFY_HEADER`·`ORIGIN_VERIFY_SECRET` (설정했을 때) | `403` |
| backend → Kratos admin API | 망 분리(밖에 열지 않는다) | — |
| backend → Turnstile | `TURNSTILE_SECRET_KEY` | 생성 `403`/`503` |
| Kratos → backend 훅 | `X-Kratos-Hook-Key` = `KRATOS_HOOK_API_KEY` | `401`, Kratos는 그 요청을 거절 |

- 게스트의 비밀번호는 backend에 저장되지 않습니다. 생성 요청 한 번에서만 backend를 지나 Kratos admin API로 갑니다.
- backend는 게스트 대신 로그인하지 않습니다. 세션 토큰과 JWT는 클라이언트가 `/auth/*`로 직접 받습니다.

## 2. 요청이 backend에 들어온 뒤의 공통 순서

HTTP 요청이 라우트에 닿기 전에 지나는 순서입니다(`app/main.py`). `/health`는 출처 확인을 하지 않습니다.

```mermaid
flowchart TD
    A["요청"] --> B{"출처 확인 헤더<br/>(설정했을 때)"}
    B -->|"틀림"| B403["403"]
    B -->|"맞음 · 미설정"| C["토큰 검증<br/>유효하면 사용자 정보를 둔다<br/>거부하지 않는다"]
    C --> D{"경로가 /v1 또는 /auth/"}
    D -->|"아님"| R["라우트"]
    D -->|"맞음"| E{"요청 한도<br/>규칙이 per_ip면 IP로,<br/>아니면 토큰의 sub 또는 IP로 센다"}
    E -->|"초과"| E429["429"]
    E -->|"이내"| R
    R --> F{"라우트의 의존성"}
    F -->|"회원 경로"| M["3.1 회원 판정"]
    F -->|"게스트 경로"| GG["3.2 게스트 판정"]
    F -->|"인증 없는 경로"| N["lookup · 생성 · /auth/*"]
```

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 출처 확인 | `app/middleware/origin_verify.py` | `tests/core/test_origin_verify.py` |
| 토큰 검증 | `app/core/auth/middleware.py`, `app/core/auth/client.py` | `tests/core/` |
| 요청 한도와 `per_ip` | `app/ratelimit/middleware.py`, `app/ratelimit/config.py` | `tests/ratelimit/`, `tests/domain/guest/test_rate_limits.py` |

## 3. 토큰 판정

### 3.1 회원 경로

REST의 인증 경로, GraphQL, WebSocket이 모두 `ensure_member`를 거칩니다.

```mermaid
flowchart TD
    A["토큰"] --> B{"서명 · iss · aud · exp"}
    B -->|"틀림 · 없음"| B401["401"]
    B -->|"맞음"| C{"GUEST_ENABLED이고<br/>schema_id가 비어 있지 않은<br/>문자열이 아니다"}
    C -->|"예"| C401["401"]
    C -->|"아니오"| D{"schema_id ==<br/>KRATOS_GUEST_SCHEMA_ID"}
    D -->|"예"| D403["403<br/>(GUEST_ENABLED와 무관)"]
    D -->|"아니오"| OK["회원으로 통과"]
```

### 3.2 게스트 경로

`require_guest_access(resource_type, id_param)`을 명시한 경로만 게스트를 받습니다. 판정은 요청마다 다시 합니다.

```mermaid
flowchart TD
    A["토큰"] --> B{"GUEST_ENABLED"}
    B -->|"꺼짐"| X403["403"]
    B -->|"켜짐"| C{"서명 · iss · aud · exp"}
    C -->|"틀림 · 없음"| C401["401"]
    C -->|"맞음"| D{"schema_id ==<br/>KRATOS_GUEST_SCHEMA_ID"}
    D -->|"아니오"| X403
    D -->|"예"| E{"guest 행이 있다<br/>(identity id = 토큰의 sub)"}
    E -->|"없음"| X403
    E -->|"있음"| F{"행의 리소스 ==<br/>경로 파라미터의 리소스"}
    F -->|"다름"| X403
    F -->|"같음"| G{"호스트 상태"}
    G -->|"OPEN"| OK["게스트로 통과"]
    G -->|"CLOSED"| X403
    G -->|"EXPIRED · MISSING"| H["게스트 폐기"] --> X403
```

| 확인 | 코드 | 테스트 |
|------|------|--------|
| `ensure_member` | `app/core/auth/dependencies.py` | `tests/core/test_auth_guest_token.py` |
| `schema_id` 읽기 | `app/core/auth/model.py` (`CurrentUser.from_claims`, `is_guest`) | `tests/core/test_auth_guest_token.py` |
| 게스트 의존성 | `app/domain/guest/dependencies.py` | `tests/domain/guest/test_dependencies.py` |
| 행·리소스·호스트 상태 | `app/domain/guest/service.py` (`authorize`, `check_access`) | `tests/domain/guest/test_policy.py` |
| 모든 경로가 게스트 토큰을 거부하는지 | 경로 전체 | `tests/domain/guest/test_route_guard.py` (받는 경로는 허용 목록에 올린다) |

## 4. 게스트 생성

```mermaid
sequenceDiagram
    autonumber
    participant C as 클라이언트
    participant B as backend
    participant D as guest 테이블
    participant T as Turnstile
    participant K as Kratos admin API

    C->>B: POST /v1/guests/lookup (리소스, 이름)
    B->>B: 호스트 상태가 OPEN인가
    B->>D: (리소스, 이름) 조회
    B-->>C: handle 또는 null

    C->>B: POST /v1/guests (리소스, 이름, 비밀번호, turnstile_token)
    B->>B: 입력 규칙 · 이름 정규형 (아니면 422)
    B->>B: 호스트 상태가 OPEN인가 (아니면 403)
    B->>D: 이름이 이미 있는가 (있으면 409)
    B->>D: 게스트가 100명인가 (맞으면 409)
    B->>T: 비밀 키 + 토큰
    T-->>B: success (false면 403, 닿지 않으면 503)
    B->>K: identity 생성 (guest schema, handle, 이름, 비밀번호, handle을 인증된 주소로)
    K-->>B: identity id (실패하면 503)
    B->>D: 행 삽입 (UNIQUE 리소스 + 이름)
    alt 삽입 실패
        B->>K: 방금 만든 identity 삭제
        B-->>C: 409 (이름 중복) 또는 오류
    else 성공
        B-->>C: 201 guest_id, handle
    end
```

- `handle`은 `<guest_id>@guest.invalid`이고, `guest_id`는 backend가 삽입 전에 만든 행 id입니다.
- 4~6번에서 거절되면 Turnstile 토큰을 쓰지 않고 Kratos를 부르지 않습니다.
- Kratos 호출 동안 DB 트랜잭션을 열어 두지 않습니다. 이름 중복은 9번의 UNIQUE 제약이 최종으로 막습니다.

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 순서 전체 | `app/domain/guest/service.py` (`lookup`, `create`) | `tests/domain/guest/test_lookup_create.py`, `test_guest_api.py` |
| 이름 정규형 | `app/domain/guest/schema/dto.py` (`normalize_guest_name`) | `tests/domain/guest/test_guest_api.py` |
| 100명 상한 | `service.MAX_GUESTS_PER_RESOURCE` | `tests/domain/guest/test_guest_limit.py` |
| Turnstile | `app/core/turnstile.py` | `tests/domain/guest/test_turnstile.py` |
| 동시 생성 | `guest` 테이블의 UNIQUE 제약 | `tests/domain/guest/test_name_concurrency.py` (PostgreSQL) |

## 5. 로그인과 JWT

```mermaid
sequenceDiagram
    autonumber
    participant C as 클라이언트
    participant P as backend /auth 프록시
    participant K as Kratos 공개 API
    participant H as backend 훅 수신
    participant D as guest 테이블

    C->>P: GET /auth/self-service/login/api
    P->>K: 그대로 넘김
    K-->>C: flow id

    C->>P: POST /auth/self-service/login?flow=… (handle, 비밀번호)
    P->>P: 요청 한도 (IP당 분당 10회) · 쿼리 문자열에 flow만
    P->>K: 넘김
    K->>K: 비밀번호 확인 (틀리면 400)
    opt identity의 schema가 guest일 때만
        K->>H: 로그인 훅 (identity id, schema_id) + X-Kratos-Hook-Key
        H->>D: guest 행이 있는가
        H->>H: 호스트 상태가 OPEN인가 (EXPIRED · MISSING이면 폐기)
        H-->>K: 200 허용 또는 403 거절
    end
    K->>K: require_verified_address
    K-->>C: session_token (거절이면 400)

    C->>P: GET /auth/sessions/whoami?tokenize_as=api + X-Session-Token
    P->>K: 넘김
    K-->>C: JWT (sub, schema_id, name. 게스트는 email 없음)
```

- 회원 로그인에서는 7~10번이 일어나지 않습니다(Kratos 훅 본문의 `error 'cancel'`). 회원은 11번이 판정합니다.
- 게스트는 handle이 처음부터 인증된 주소라 11번을 통과합니다.
- 로그인 훅은 로그인 시점에만 판정합니다. 그 뒤의 게스트 경로 요청은 3.2가 요청마다 다시 확인합니다.
- JWT의 `schema_id`는 Kratos 클레임 매퍼가 identity에서 읽습니다. identity의 schema는 본인이 바꿀 수 없습니다.

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 프록시의 한도·쿼리 문자열 | `app/api/auth_proxy.py`, `app/ratelimit/config.py` | `tests/test_auth_proxy.py`, `tests/domain/guest/test_rate_limits.py` |
| 훅 키 | `app/api/kratos_hooks.py` (`_authorize`) | `tests/domain/guest/test_kratos_hooks.py` |
| 로그인 판정 | `app/domain/guest/service.py` (`login_allowed`) | `tests/domain/guest/test_hook_decisions.py`, `test_client_login.py` |
| Kratos 설정(훅 순서, 게스트만 호출, 클레임) | `dev/kratos/kratos.guest.yml`, `hook.login.jsonnet`, `api-jwt.claims.jsonnet` | `tests/domain/guest/test_kratos_config.py` |

## 6. 이름 변경

```mermaid
sequenceDiagram
    autonumber
    participant C as 클라이언트
    participant P as backend /auth 프록시
    participant K as Kratos 공개 API
    participant H as backend 훅 수신
    participant D as guest 테이블

    C->>P: POST /auth/self-service/settings?flow=… (method: profile, traits) + X-Session-Token
    P->>P: 요청 한도 · 쿼리 문자열에 flow만
    P->>P: method가 profile인가 · 세션 토큰이 있는가 (아니면 403)
    P->>K: whoami (그 세션 토큰)
    K-->>P: 세션의 identity
    P->>P: 게스트 세션인가 (아니면 403)
    P->>D: 같은 리소스의 다른 게스트가 그 이름인가 (맞으면 409)
    P->>K: 넘김 (검사한 세션 토큰만)
    K->>K: traits를 guest schema로 검증
    K->>H: 설정 훅 (identity id, schema_id, 바뀔 traits) + X-Kratos-Hook-Key
    H->>D: guest 행 · 호스트 상태 OPEN
    H->>H: handle이 그대로인가 · 이름이 정규형인가
    H->>D: guest.name 변경 (UNIQUE 위반이면 거절) + GuestRenamed
    H-->>K: 200 허용 또는 403 거절
    K->>K: identity 저장
    K-->>C: 200 (거절이면 400)
```

- `method`가 `password`·`oidc`인 게스트의 설정 제출은 프록시에서 `403`이고, Kratos에 직접 닿아도 그 메서드의 설정 훅이 거절합니다.
- 7번은 빠른 응답을 위한 조회이고, 이름 중복을 최종으로 막는 것은 13번의 UNIQUE 제약입니다.
- 13번이 끝난 뒤 15번이 실패하면 `guest.name`과 Kratos의 `traits.name`이 다음 이름 변경까지 다릅니다.

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 프록시의 게스트 처리 | `app/api/auth_proxy.py` (`_settings_rejection`), `service.name_taken_by_other` | `tests/domain/guest/test_rename_proxy.py`, `tests/test_auth_proxy.py` |
| 설정 판정 | `app/domain/guest/service.py` (`settings_change_allowed`) | `tests/domain/guest/test_hook_decisions.py`, `test_kratos_hooks.py` |
| 동시 이름 변경·생성 | `guest` 테이블의 UNIQUE 제약 | `tests/domain/guest/test_name_concurrency.py` (PostgreSQL) |

## 7. `/auth` 프록시의 판정 순서

GET은 아래 확인 없이 넘깁니다. 경로는 Kratos로 실제 나갈 경로(정리한 뒤, 소문자, 끝의 `/` 제외)로 비교합니다.

```mermaid
flowchart TD
    A["GET 밖의 /auth/* 요청"] --> RL{"요청 한도<br/>IP당 분당 10회"}
    RL -->|"초과"| R429["429"]
    RL -->|"이내"| Q{"로그인 · 가입 · 설정 ·<br/>인증 · 복구 제출인가"}
    Q -->|"아니오"| FWD["Kratos로 넘김"]
    Q -->|"예"| QS{"쿼리 문자열에<br/>flow만 있는가"}
    QS -->|"아니오"| R400a["400 invalid_request_body"]
    QS -->|"예"| AD{"인증 · 복구 제출"}
    AD -->|"본문을 읽을 수 없음"| R400a
    AD -->|"email이 @guest.invalid"| R400b["400 address_not_accepted"]
    AD -->|"그 밖 · 해당 없음"| OI{"로그인 · 가입 제출의<br/>method: oidc"}
    OI -->|"본문을 읽을 수 없음"| R400a
    OI -->|"traits.email을 버리고 계속 · 해당 없음"| ST{"설정 제출"}
    ST -->|"해당 없음"| FWD
    ST -->|"세션 토큰 없음"| R403["403"]
    ST -->|"password + 메일 복구 세션"| FWD
    ST -->|"profile + 게스트 세션<br/>(GUEST_ENABLED)"| NM{"다른 게스트의 이름인가"}
    ST -->|"그 밖"| R403
    NM -->|"예"| R409["409 guest_name_taken"]
    NM -->|"아니오"| FWD
```

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 순서 전체 | `app/api/auth_proxy.py` (`kratos_proxy`) | `tests/test_auth_proxy.py` |
| 넘기는 요청 헤더 | `FORWARD_REQUEST_HEADERS` (쿠키는 넘기지 않는다) | `tests/test_auth_proxy.py` |

## 8. 게스트의 상태

```mermaid
stateDiagram-v2
    state "게스트 있음" as Present {
        state "접근 가능" as Allowed
        state "접근 거절 (게스트는 남는다)" as Refused
        [*] --> Allowed
        Allowed --> Refused: 호스트 상태 CLOSED
        Refused --> Allowed: 호스트 상태 OPEN
    }
    state "폐기" as Discarded
    [*] --> Present: POST /v1/guests
    Present --> Discarded: DELETE /v1/guests/me
    Present --> Discarded: 게스트 확인에서 EXPIRED 또는 MISSING
    Present --> Discarded: discard_resource_guests
    Discarded --> [*]
```

게스트 확인은 로그인 훅, 설정 훅, 게스트 경로 요청, 같은 리소스의 이름 찾기·생성입니다. 호스트 상태는 저장하지 않고 확인할 때마다 리소스에 묻습니다.

폐기는 다음 순서입니다.

```mermaid
sequenceDiagram
    autonumber
    participant B as backend
    participant D as guest 테이블
    participant R as 리소스 도메인
    participant K as Kratos admin API

    B->>D: 행 삭제 + GuestDiscarded (한 트랜잭션, 커밋)
    D-->>R: GuestDiscarded 핸들러
    B->>K: identity 삭제
    Note over B,K: 실패하면 로그만 남긴다. 행이 없으므로 그 identity는 로그인 훅과 게스트 경로에서 거절된다
```

| 폐기 뒤 | 동작 |
|---------|------|
| Kratos 세션 | identity가 지워지면 바로 끊긴다 |
| 이미 받은 JWT | 만료(tokenizer `ttl`, 기본 10분)까지 서명은 유효하다. 게스트 경로는 행이 없어 `403`, 회원 경로는 `schema_id`로 `403` |
| 이름 | 다시 쓸 수 있다 |

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 접근 정책과 폐기 | `app/domain/guest/service.py` (`check_access`, `discard_guest`, `discard_resource_guests`) | `tests/domain/guest/test_policy.py` |
| 호스트 계약 | `app/domain/guest/host.py` | `tests/domain/guest/test_policy.py` |

## 9. 꺼진 상태 (`GUEST_ENABLED=false`)

```mermaid
flowchart LR
    A["/v1/guests/*"] --> A404["404"]
    B["/internal/kratos/hooks/*"] --> B404["404"]
    C["게스트 schema의 토큰"] --> C403["모든 인증 경로에서 403"]
    D["schema_id 없는 토큰"] --> D200["회원으로 받는다"]
    E["/auth 게스트 세션의 profile 제출"] --> E403["403"]
```

게스트와 상관없이 적용되는 것은 `/auth` 제출의 요청 한도, 쿼리 문자열 규칙, `@guest.invalid` 주소의 인증·복구 제출 거절입니다(7장).

| 확인 | 테스트 |
|------|--------|
| 꺼진 상태 | `tests/domain/guest/test_guest_api.py`, `test_kratos_hooks.py`, `tests/test_auth_proxy.py` |
