# `/auth` 프록시

backend의 `/auth/*`는 Kratos 공개 API로 가는 프록시입니다. Kratos는 backend 옆에서만 닿고 밖에 직접 열려 있지 않으므로, 로그인·가입·인증·복구·설정·세션 조회·JWT 발급은 모두 이 경로를 지납니다. 이 문서는 프록시가 요청을 넘기는 방식, 넘기기 전에 하는 확인과 그 순서, 프록시가 직접 답하는 응답을 설명합니다.

- 회원 인증의 구조는 [인증 가이드](auth.ko.md), 게스트 계정은 [게스트 계정 가이드](guest.ko.md)에 있습니다.
- `KRATOS_PUBLIC_URL`이 비어 있으면 `/auth/*`는 `404`입니다.
- `/auth/.well-known/jwks.json`과 `/auth/.well-known/openid-configuration`은 프록시가 아니라 backend가 직접 답합니다.

## 넘기는 방식

| 항목 | 동작 |
|------|------|
| 경로 | `/auth` 접두사를 떼고 `KRATOS_PUBLIC_URL`로 넘긴다. 예: `/auth/sessions/whoami` → `/sessions/whoami`. 쿼리 문자열은 그대로 |
| 메서드 | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| 넘기는 요청 헤더 | `X-Session-Token`, `Authorization`, `Accept`, `Content-Type`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Cf-Connecting-IP`. 그 밖의 헤더는 넘기지 않는다 |
| 쿠키 | 요청의 `Cookie`는 넘기지 않고, 응답의 `Set-Cookie`는 버린다. 인증은 세션 토큰과 JWT로만 한다 |
| 리다이렉트 | 따라가지 않고 클라이언트에 그대로 돌려준다 |
| 가는 곳 | `KRATOS_PUBLIC_URL` 한 곳. Kratos admin API에는 닿지 않는다 |
| 시간 제한 | 연결 3초, 전체 15초. Kratos에 닿지 않으면 `502` |
| 응답 | Kratos의 상태 코드와 본문을 그대로 돌려준다 |

## 판정 순서

GET은 아래 확인 없이 넘깁니다. 경로는 Kratos로 실제 나갈 경로(`..`와 인코딩을 정리한 뒤, 소문자, 끝의 `/` 제외)로 비교하므로, 같은 Kratos 경로에 닿는 다른 표기도 같은 확인을 받습니다.

**공통 단계.** GET 밖의 모든 `/auth/*` 요청이 지납니다.

```mermaid
flowchart TD
    A["GET 밖의<br/>/auth/* 요청"] --> RL{"요청 한도<br/>IP당 분당 60회<br/>(설정 제출은 세지 않음)"}
    RL -->|"초과"| R429["429"]
    RL -->|"이내"| RI{"로그인 · 가입 · 인증 · 복구 제출의<br/>같은 IP · 식별자<br/>분당 5회"}
    RI -->|"초과"| R429
    RI -->|"이내 · 해당 없음"| Q{"로그인 · 가입 · 설정 ·<br/>인증 · 복구 제출"}
    Q -->|"아니오"| FWD["Kratos로 넘김"]
    Q -->|"예"| QS{"쿼리 문자열에<br/>flow만"}
    QS -->|"아니오"| R400["400<br/>invalid_request_body"]
    QS -->|"예"| NEXT["경로별 확인"]
```

**경로별 확인.** 위에서 아래 순서로 하고, 모두 지나면 Kratos로 넘깁니다. 로그인·가입·설정 제출은 넘기기 전에 Kratos 자리를 잡습니다. 자리는 회원 2개, 게스트(게스트 handle 로그인, 게스트 이름 변경, 게스트 생성) 1개이고, 2초 안에 잡지 못하면 `429`입니다(`app/core/kratos_slots.py`).

| 제출 경로 | 확인 | 거절 응답 |
|-----------|------|-----------|
| 인증, 복구 | 본문을 읽을 수 있고 `email`이 하나인가 | `400` `invalid_request_body` |
| | `email`이 `@guest.invalid`로 끝나지 않는가 | `400` `address_not_accepted` |
| 로그인 | 아래 "로그인 제출" 그림 (`GUEST_ENABLED`일 때) | |
| 로그인, 가입 | `method: oidc`면 본문을 읽을 수 있는가. 읽으면 `traits.email`을 버리고 넘긴다 | `400` `invalid_request_body` |
| 설정 | 아래 "설정 제출" 그림 | |

**로그인 제출** (`GUEST_ENABLED=true`일 때만. 꺼져 있으면 `identifier`를 읽지 않는다)

```mermaid
flowchart TD
    L["로그인 제출"] --> I{"identifier를<br/>하나로 읽을 수 있는가"}
    I -->|"둘 이상 ·<br/>본문 못 읽음"| R400["400<br/>invalid_request_body"]
    I -->|"예"| H{"게스트 handle인가<br/>(@guest.invalid)"}
    H -->|"아니오"| FWD["다음 확인으로"]
    H -->|"예"| T{"X-Turnstile-Token"}
    T -->|"없음 · 거절"| R403["403<br/>guest_verification_failed"]
    T -->|"확인 불가"| R503["503<br/>guest_verification_unavailable"]
    T -->|"통과"| FWD
```

**설정 제출**

```mermaid
flowchart TD
    S["설정 제출"] --> M{"method"}
    M -->|"password"| P{"세션 토큰이 있고<br/>메일 복구 세션인가"}
    P -->|"예"| PL{"identity당<br/>분당 10회"}
    PL -->|"초과"| R429["429"]
    PL -->|"이내"| FWD["Kratos로 넘김<br/>(검사한 세션 토큰만)"]
    P -->|"아니오"| R403["403<br/>settings_require_email_recovery"]
    M -->|"profile<br/>(GUEST_ENABLED)"| G{"세션 토큰이 있고<br/>게스트 세션인가"}
    G -->|"아니오"| R403
    G -->|"예"| L{"identity당<br/>분당 10회"}
    L -->|"초과"| R429["429"]
    L -->|"이내"| N{"다른 게스트의<br/>이름인가"}
    N -->|"예"| R409["409<br/>guest_name_taken"]
    N -->|"아니오"| FWD
    M -->|"그 밖"| R403
```

설정 제출이 넘어갈 때는 검사한 `X-Session-Token`의 세션으로만 처리되도록 `Authorization` 헤더를 빼고 넘깁니다.

## 넘긴 뒤에 하는 일

| 조건 | 하는 일 |
|------|---------|
| `POST`이고 Kratos 응답이 `200`·`303`이며 경로가 가입·인증·복구·설정 제출 | 응답하기 전에 메일 잡(`KRATOS_COURIER_JOB`) 실행을 요청한다 |
| `POST`이고 Kratos 응답이 `200`이며 경로가 로그인·가입 제출 | identity id와 클라이언트 IP를 접근 기록으로 남긴다 |

두 경우 모두 클라이언트가 받는 응답은 바뀌지 않습니다.

## 프록시가 직접 답하는 응답

아래 응답은 Kratos에 넘기지 않고 프록시가 답합니다. `429`와 `502` 밖의 본문은 `{"error": {"id": "<id>", "code": <상태>, "status": "...", "reason": "..."}}` 모양입니다.

| 상태 | `id` | 언제 |
|------|------|------|
| `429` | (본문은 [레이트 리밋](../development/rate-limit.ko.md)의 429 형식) | GET 밖의 요청이 IP당 분당 60회, 로그인·가입·인증·복구 제출이 같은 IP·식별자로 분당 5회, 설정 제출이 identity당 분당 10회를 넘었다. 메서드마다 따로 세고, Kratos 제출은 모두 `POST`다. 또는 로그인·가입·설정 제출이 Kratos 자리를 2초 안에 잡지 못했다(본문 `detail`, `retry_after`, 헤더 `Retry-After: 1`) |
| `400` | `invalid_request_body` | 검사하는 제출의 쿼리 문자열에 `flow` 밖의 키가 있다. 본문을 읽을 수 없거나 같은 값을 둘 이상 보냈다 (`method`, `email`, `identifier`) |
| `400` | `address_not_accepted` | 인증·복구 제출의 `email`이 `@guest.invalid`로 끝난다 |
| `403` | `settings_require_email_recovery` | 설정 제출이 메일 복구 세션의 비밀번호 변경도, 게스트 세션의 이름 변경도 아니다 |
| `403` | `guest_verification_failed` | 게스트 handle의 로그인 제출에 `X-Turnstile-Token`이 없거나 Turnstile이 받지 않았다 |
| `503` | `guest_verification_unavailable` | 게스트 handle의 로그인 제출인데 Turnstile을 확인할 수 없다 |
| `409` | `guest_name_taken` | 게스트의 이름 변경이 같은 리소스의 다른 게스트 이름이다 |
| `502` | (본문 `{"detail": "Authentication service unavailable"}`) | Kratos 공개 API에 닿지 않는다 |

게스트 handle 로그인의 Turnstile 확인과 게스트 이름 변경은 `GUEST_ENABLED=true`일 때만 합니다. 요청 한도, 쿼리 문자열 규칙, `@guest.invalid` 주소 거절, 설정 제출 제한, 소셜 제출의 `traits.email` 버리기는 `GUEST_ENABLED`와 상관없이 합니다.

## Kratos 공개 API를 backend 뒤에 두기

이 문서의 확인은 모두 backend에서 합니다. Kratos 공개 API(`KRATOS_PUBLIC_URL`)에 backend를 거치지 않고 닿을 수 있으면 아래 왼쪽 열은 적용되지 않습니다. Kratos 공개 API와 admin API는 backend만 닿는 주소(같은 호스트의 루프백, 내부 망)에 둡니다.

| 프록시에서만 하는 것 | Kratos 설정이 하는 것 (프록시와 무관) |
|----------------------|----------------------------------------|
| `/auth` 제출의 요청 한도 | 이메일 인증 전 로그인 거절 (`require_verified_address`) |
| 제출의 쿼리 문자열에 `flow`만 | 비밀번호 변경·복구 뒤 기존 세션 종료 (`revoke_active_sessions`) |
| 설정 제출 제한 (메일 복구 세션의 비밀번호 변경, 게스트 세션의 이름 변경만) | 게스트 로그인 판정 (로그인 훅) |
| 소셜 제출의 `traits.email` 버리기 | 게스트의 handle·비밀번호 변경과 소셜 연결 거절, 이름 중복 거절 (설정 훅) |
| `@guest.invalid` 주소의 인증·복구 제출 거절 | 게스트 schema로의 셀프 가입 없음 (`default_schema_id`) |
| 게스트 로그인 제출의 Turnstile 확인 | 게스트의 비밀번호 복구 없음 (schema에 recovery 주소 없음) |
| 쿠키와 요청 헤더 거르기 | |
| 접근 기록, 메일 잡 실행 요청 | |

backend의 JWT 검증, 회원·게스트 구분, 게스트 경로의 요청별 판정은 `/auth`와 상관없이 API 요청마다 합니다.

## 관련 코드

| 확인 | 코드 | 테스트 |
|------|------|--------|
| 프록시 전체 | `app/api/auth_proxy.py` (`kratos_proxy`) | `tests/test_auth_proxy.py` |
| 넘기는 요청 헤더 | `FORWARD_REQUEST_HEADERS` (쿠키와 `X-Turnstile-Token`은 넘기지 않는다) | `tests/test_auth_proxy.py`, `tests/domain/guest/test_guest_login_turnstile.py` |
| 요청 한도 | `app/api/auth_proxy.py` (`_submit_rate_limit_refusal`, `_settings_rate_limit_refusal`), `app/ratelimit/config.py` (`AUTH_*`) | `tests/domain/guest/test_rate_limits.py` |
| Kratos 자리 | `app/core/kratos_slots.py`, `app/api/auth_proxy.py` (`HASHING_SUBMIT_PATHS`) | `tests/domain/guest/test_kratos_slots.py` |
| 게스트 로그인의 Turnstile | `app/core/turnstile.py` | `tests/domain/guest/test_guest_login_turnstile.py` |
| 게스트 이름 변경 | `app/domain/guest/service.py` (`name_taken_by_other`) | `tests/domain/guest/test_rename_proxy.py` |
| 메일 잡 | `app/core/courier.py` | `tests/core/test_courier.py` |
| 접근 기록 | `app/core/audit.py` | `tests/test_auth_proxy.py` |
| OIDC discovery·JWKS | `app/api/oidc_discovery.py` | |
