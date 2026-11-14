# 게스트 계정 가이드

게스트는 회원 가입 없이 리소스 하나에 들어가는 계정입니다. 이 문서는 게스트의 수명 주기, 클라이언트가 따르는 순서, API, 그리고 리소스가 게스트를 받으려면 구현할 것을 설명합니다. Kratos와 배포 설정은 [게스트 계정 설정 (Kratos)](../deployment/kratos-guest.ko.md)에 있습니다.

## 게스트란

게스트는 회원과 같이 Kratos가 발급하는 계정입니다. 자격 증명은 Kratos가 저장하고, 세션과 JWT도 Kratos가 발급합니다. 회원과 다른 점은 다음과 같습니다.

| | 회원 | 게스트 |
|---|---|---|
| Kratos identity schema | `default` | `KRATOS_GUEST_SCHEMA_ID` (기본 `guest`) |
| 속한 곳 | 없음 | 리소스 하나 (`resource_type`, `resource_id`) |
| 로그인 식별자 | 이메일 | 서버가 만든 `<guest_id>@guest.invalid`(`handle`). 게스트가 입력하지 않는다 |
| 이름 | 선택 | 필수. 1~50자, 같은 리소스 안에서 겹치지 않는다 |
| 비밀번호 | Kratos 비밀번호 정책 | 비어 있지 않고 UTF-8로 72바이트 이하면 된다 |
| 이메일 인증 | 로그인에 필요 | 없음. handle을 처음부터 인증된 주소로 만든다(메일이 가지 않는 주소) |
| 만들 때 | Kratos 가입 플로우 | `POST /v1/guests`, Cloudflare Turnstile 토큰 필요 |
| 접근 범위 | 회원 경로 전체 | 자기 리소스의 게스트 경로만 |

- 게스트 기능은 `GUEST_ENABLED=true`일 때만 켜집니다(기본 꺼짐). 꺼져 있으면 게스트 엔드포인트는 404이고, 게스트 토큰은 모든 경로에서 거부됩니다.
- 게스트를 켜려면 Cloudflare Turnstile이 필요합니다. `TURNSTILE_SECRET_KEY`가 없으면 서버가 뜨지 않고, Turnstile 없이 게스트를 켜는 설정은 없습니다.
- 게스트는 자기 이름만 바꿀 수 있습니다. 로그인 식별자·비밀번호 변경과 소셜 로그인 연결은 Kratos 설정 훅이 거절합니다.
- 회원 경로(`/v1/*`의 인증 경로, GraphQL, WebSocket)는 게스트 토큰을 `403`으로 거부합니다.
- 게스트를 켜도 회원 로그인은 Kratos 기본 동작 그대로입니다. 로그인에서 backend를 부르는 것은 게스트뿐입니다.
- 게스트 JWT에는 `email` 클레임이 없고 `email_verified`는 `false`입니다. handle은 이메일로 쓰이지 않습니다.

게스트의 정보는 두 곳에 있습니다.

| 곳 | 가진 것 | 쓰는 곳 |
|----|---------|---------|
| Kratos identity | handle, 비밀번호, 이름(`traits.name`) | 로그인, 세션, JWT의 `name` |
| `guest` 테이블 | identity id, 리소스, 이름(`name`) | 이름 찾기, 이름 중복 검사, 접근 확인 |

## 클라이언트가 따르는 순서

게스트는 이름과 비밀번호만 입력합니다. 클라이언트는 다음 순서로 호출합니다.

1. `POST /v1/guests/lookup`으로 그 리소스에 그 이름의 게스트가 있는지 찾는다.
2. 없으면(`handle: null`) Turnstile 위젯에서 토큰을 받아 `POST /v1/guests`로 게스트를 만든다. 응답에 `handle`이 있다.
3. `handle`과 비밀번호로 회원과 같은 Kratos 로그인 플로우를 `/auth`로 호출한다.
4. 세션 토큰으로 JWT를 받아(`GET /auth/sessions/whoami?tokenize_as=api`) 게스트 경로에 쓴다.

이름이 이미 있으면 2번을 건너뜁니다. 3번에서 비밀번호가 틀리면 Kratos가 `400`으로 거절합니다.

```http
POST /v1/guests/lookup
{"resource_type": "meeting", "resource_id": "<uuid>", "name": "민수"}
→ 200 {"handle": null}

POST /v1/guests
{"resource_type": "meeting", "resource_id": "<uuid>", "name": "민수", "password": "1234", "turnstile_token": "<위젯 토큰>"}
→ 201 {"guest_id": "0b9c...", "handle": "0b9c...@guest.invalid", ...}

GET  /auth/self-service/login/api
→ 200 {"id": "<flow id>", ...}

POST /auth/self-service/login?flow=<flow id>
{"method": "password", "identifier": "0b9c...@guest.invalid", "password": "1234"}
→ 200 {"session_token": "ory_st_...", ...}

GET  /auth/sessions/whoami?tokenize_as=api
X-Session-Token: ory_st_...
→ 200 {"tokenized": "<JWT>", "identity": {"schema_id": "guest", ...}}
```

세션 응답의 `identity.traits`에는 `email`이 없고 `handle`과 `name`이 있습니다. 게스트인지는 `identity.schema_id`로 가립니다.

## 수명 주기

| 단계 | 일어나는 일 |
|------|-------------|
| 생성 | `POST /v1/guests`. 리소스가 게스트를 받고(`OPEN`) 그 이름이 비어 있으면 Kratos identity와 게스트 행을 만든다 |
| 로그인 | Kratos 로그인 플로우. Kratos 로그인 훅이 backend에 묻고, 게스트 행이 있고 리소스가 `OPEN`일 때만 세션을 만든다 |
| 이름 변경 | Kratos 설정 플로우(`method: profile`)로 `traits.name`을 바꾼다. 설정 훅이 `guest.name`을 바꾸고 `GuestRenamed` 이벤트를 낸다 |
| 자기 삭제 | `DELETE /v1/guests/me` |
| 폐기 | 아래 조건에서 게스트 행과 Kratos identity를 지우고 `GuestDiscarded` 이벤트를 낸다 |

게스트는 다음 경우에 폐기됩니다.

- 게스트가 자기를 삭제할 때
- 게스트 확인(로그인, 게스트 경로 요청, 이름 변경, 같은 리소스의 이름 찾기·생성)에서 리소스가 `EXPIRED`나 `MISSING`일 때
- 리소스가 지워지면서 `discard_resource_guests`를 부를 때

폐기된 게스트의 Kratos 세션은 바로 끊깁니다. 이미 받은 JWT는 만료(Kratos tokenizer `ttl`, 기본 10분)까지 서명은 유효하지만, 게스트 경로는 요청마다 게스트 행을 확인하므로 거부됩니다. Kratos identity 삭제가 실패해도 게스트 행은 지워지고, 행이 없는 게스트 identity는 로그인할 수 없습니다. 폐기된 게스트의 이름은 다시 쓸 수 있습니다.

리소스가 `CLOSED`인 동안 게스트는 남지만 로그인, 이름 찾기, 생성, 이름 변경은 거절됩니다. 자기 삭제는 됩니다.

## 이름과 비밀번호 규칙

이름은 다음 순서로 정규형으로 바꾼 뒤 저장하고 비교합니다.

1. NFC로 정규화한다.
2. 이어진 공백 문자(탭·줄바꿈, NBSP·전각 공백 같은 다른 공백 포함)를 공백 한 칸으로 바꾸고 앞뒤 공백을 뗀다.
3. 제어·서식·대체·사용자 정의·미배정 문자(유니코드 범주 Cc, Cf, Cs, Co, Cn)가 있으면 거절한다. 폭 없는 공백(U+200B), 폭 없는 결합자(U+200D), BOM, 방향 제어 문자가 여기에 든다.
4. 길이가 1~50자가 아니면 거절한다.

- 정규형이 같으면 같은 이름입니다. `김  민수`와 `김 민수`는 같고, 대소문자는 구분합니다(`Min`과 `min`은 다른 이름).
- 결합자 없는 이모지(`🙂`, `👍🏽`, `🇰🇷`)는 쓸 수 있습니다. U+200D로 이은 이모지(가족 이모지 등)는 쓸 수 없습니다.
- 생성과 이름 찾기는 받은 이름을 정규형으로 바꿉니다. 이름 변경은 이미 정규형인 이름만 받습니다(Kratos가 저장할 값을 backend가 바꿀 수 없다).

비밀번호는 NFC로 정규화한 뒤 비어 있지 않고 UTF-8로 72바이트 이하면 받습니다. 다른 규칙은 없습니다. 로그인 때는 클라이언트가 NFC로 보냅니다.

## API

`GUEST_ENABLED`가 꺼져 있으면 아래 경로는 모두 `404`입니다.

### 이름 찾기 — `POST /v1/guests/lookup`

인증이 필요 없습니다. Kratos를 부르지 않습니다.

```json
{
  "resource_type": "meeting",
  "resource_id": "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
  "name": "민수"
}
```

응답 (200): 그 이름의 게스트가 있으면 `{"handle": "<guest_id>@guest.invalid"}`, 없으면 `{"handle": null}`.

| 상태 | 뜻 |
|------|----|
| `200` | 찾았거나(`handle`) 없다(`null`) |
| `403` | 리소스가 없거나, 지금 게스트를 받지 않거나, 게스트 기간이 끝났다. 세 경우 응답이 같다 |
| `422` | 입력 규칙 위반 |
| `429` | IP당 분당 10회를 넘었다 |

### 생성 — `POST /v1/guests`

인증이 필요 없습니다.

```json
{
  "resource_type": "meeting",
  "resource_id": "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
  "name": "민수",
  "password": "1234",
  "turnstile_token": "0.AbC..."
}
```

| 필드 | 규칙 |
|------|------|
| `resource_type` | 리소스 종류 (`meeting` 등) |
| `resource_id` | 리소스 UUID |
| `name` | [이름 규칙](#이름과-비밀번호-규칙) |
| `password` | [비밀번호 규칙](#이름과-비밀번호-규칙) |
| `turnstile_token` | Cloudflare Turnstile 위젯이 준 토큰. 1~2048자, 한 번만 쓸 수 있다 |

응답 (201):

```json
{
  "guest_id": "0b9c6d1e-...",
  "handle": "0b9c6d1e-...@guest.invalid",
  "resource_type": "meeting",
  "resource_id": "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
}
```

서버는 리소스 상태, 이름 중복, Turnstile 토큰 순으로 확인합니다. 앞에서 거절되는 요청은 토큰을 쓰지 않습니다.

| 상태 | `error_type` | 뜻 |
|------|--------------|----|
| `201` | | 만들었다 |
| `403` | `GuestEntryRefusedError` | 리소스가 없거나, 지금 게스트를 받지 않거나, 게스트 기간이 끝났다 |
| `409` | `GuestNameTakenError` | 이 리소스에 같은 이름의 게스트가 있다 |
| `403` | `GuestVerificationFailedError` | Turnstile이 토큰을 받지 않았다. 위젯에서 새 토큰을 받아 다시 보낸다 |
| `503` | `GuestServiceUnavailableError` | Turnstile 확인 서버나 Kratos에 닿지 않는다. 게스트는 만들어지지 않는다 |
| `422` | | 입력 규칙 위반 (`turnstile_token` 누락 포함) |
| `429` | | IP당 분당 10회를 넘었다 (이름 찾기와 따로 센다) |

### 로그인과 JWT

회원과 같은 경로입니다(`/auth`는 Kratos 공개 API 프록시).

```http
GET  /auth/self-service/login/api
POST /auth/self-service/login?flow=<flow id>
     {"method": "password", "identifier": "<handle>", "password": "<비밀번호>"}
GET  /auth/sessions/whoami?tokenize_as=api
     X-Session-Token: ory_st_...
```

- 비밀번호가 틀리면 Kratos가 `400`(메시지 `id` `4000006`)으로 거절합니다.
- 게스트 행이 없거나 리소스가 `OPEN`이 아니면 로그인 훅이 거절해 `400`(메시지 `id` `4000001`)입니다.
- JWT 클레임에는 `sub`(게스트의 Kratos identity id), `schema_id`(게스트 schema id), `name`이 있고 `email`은 없습니다. 이후 요청에는 `Authorization: Bearer <JWT>`를 붙입니다.
- `/auth`로 가는 GET 밖의 요청은 IP당 분당 10회입니다. 회원의 로그인·가입·코드 제출도 같은 한도를 받습니다.

### 이름 변경

Kratos 설정 플로우를 `/auth` 프록시로 씁니다. `traits.handle`은 현재 값 그대로 보내야 합니다.

```http
GET  /auth/self-service/settings/api
X-Session-Token: ory_st_...

POST /auth/self-service/settings?flow=<flow id>
X-Session-Token: ory_st_...
Content-Type: application/json

{"method": "profile", "traits": {"handle": "<현재 handle>", "name": "철수"}}
```

| 상태 | 뜻 |
|------|----|
| `200` | 바뀌었다. 이후 이름 찾기는 새 이름을 따른다 |
| `409` `guest_name_taken` | 같은 리소스의 다른 게스트가 그 이름이다 (프록시가 Kratos에 넘기기 전에 답한다) |
| `400` 메시지 `id` `4000001` | 설정 훅이 거절했다: 이름이 정규형이 아니거나, `handle`이 다르거나, 리소스가 `OPEN`이 아니거나, 그 사이 다른 게스트가 그 이름을 가졌다 |
| `403` | `method`가 `profile`이 아니다 (`password`, `oidc` 등). Kratos 설정 훅도 다시 거절한다 |

- 지금 이름과 같은 이름으로 바꾸는 요청은 받고, 아무것도 바꾸지 않습니다.
- 이름 중복은 `guest` 테이블의 UNIQUE 제약이 막습니다. 요청이 `/auth` 프록시를 거치지 않아도 같습니다.
- 훅이 허용한 뒤 Kratos가 이름 저장에 실패하면 `guest.name`(찾기·중복 기준)과 Kratos의 `traits.name`(JWT의 `name`)이 다음 이름 변경까지 다릅니다.

### 자기 삭제 — `DELETE /v1/guests/me`

게스트 JWT가 필요합니다. 응답은 `204`이고, 다시 불러도 `204`입니다. 회원 토큰은 `403`, 토큰이 없으면 `401`입니다.

### `/auth` 프록시가 받지 않는 요청

| 요청 | 응답 |
|------|------|
| 인증·복구 제출의 `email`이 `@guest.invalid`로 끝난다 | `400` `address_not_accepted` |
| 로그인·가입·설정·인증·복구 제출(GET 밖)의 쿼리 문자열에 `flow` 밖의 값이 있다 | `400` `invalid_request_body` |

## 리소스가 게스트를 받게 하기

게스트 도메인(`app/domain/guest/`)은 리소스 도메인을 import하지 않습니다. 리소스가 게스트 도메인에 자기를 등록합니다.

### 1. 호스트 계약 구현과 등록

리소스 종류마다 `GuestHost`를 구현해 `register_guest_host`로 등록합니다. 등록하지 않은 리소스 종류는 `MISSING`으로 봅니다.

| `GuestHostStatus` | 뜻 | 접근 정책 |
|-------------------|----|-----------|
| `OPEN` | 리소스가 있고, 게스트를 받으며, 게스트 기간 안이다 | 허용 |
| `CLOSED` | 리소스가 있지만 지금은 게스트를 받지 않는다 | 거부, 게스트는 남는다 |
| `EXPIRED` | 게스트 기간이 끝났다 | 거부, 게스트를 폐기한다 |
| `MISSING` | 리소스가 없다 | 거부, 게스트를 폐기한다 |

```python
# app/domain/meeting/guest_host.py
from uuid import UUID

from sqlmodel import Session

from app.domain.guest.host import GuestHostStatus, register_guest_host
from app.models.visibility import ResourceType


class MeetingGuestHost:
    def guest_status(self, session: Session, resource_id: UUID) -> GuestHostStatus:
        meeting = session.get(Meeting, resource_id)
        if meeting is None:
            return GuestHostStatus.MISSING
        if meeting.guest_period_over():
            return GuestHostStatus.EXPIRED
        if not meeting.accepts_guests:
            return GuestHostStatus.CLOSED
        return GuestHostStatus.OPEN


def register() -> None:
    register_guest_host(ResourceType.MEETING, MeetingGuestHost())
```

- `guest_status`는 읽기만 하고 세션을 커밋하지 않습니다.
- 등록은 앱 시작 때 한 번 합니다(이벤트 핸들러 등록과 같은 자리). 테스트는 `register_guest_host`·`unregister_guest_host`로 가짜 호스트를 둡니다(`tests/domain/guest/conftest.py`).

### 2. 게스트 경로

게스트를 받는 경로는 `require_guest_access`를 명시합니다. 회원 의존성(`get_current_user` 등)은 게스트를 받지 않습니다.

```python
from fastapi import Depends

from app.domain.guest.dependencies import require_guest_access
from app.domain.guest.model import Guest
from app.models.visibility import ResourceType


@router.get("/meetings/{meeting_id}/guest-view")
async def guest_view(guest: Guest = Depends(require_guest_access(ResourceType.MEETING, "meeting_id"))):
    ...
```

- 토큰이 게스트 토큰이고, 게스트 행이 있고, 그 행의 리소스가 경로 파라미터의 리소스와 같고, 접근 정책이 허용할 때만 통과합니다. 아니면 `403`(토큰이 없으면 `401`)입니다.
- 게스트를 받는 경로는 회원 게이트(`get_current_user_synced`)가 걸린 `/v1` 인증 라우터 밖에 둡니다.
- 새 경로가 게스트 토큰을 거부하지 않으면 `tests/domain/guest/test_route_guard.py`가 실패합니다. 게스트를 받는 경로는 그 테스트의 허용 목록에 올립니다.

### 3. 이벤트

게스트 이벤트는 `app/domain/guest/events.py`에 있습니다. `owner_id`는 게스트의 Kratos identity id이고, 리소스는 `resource_type`·`resource_id`로 자기 리소스인지 가립니다.

| 이벤트 | 언제 | 리소스가 할 일 |
|--------|------|----------------|
| `GuestDiscarded` | 게스트 행을 지운 뒤, 같은 트랜잭션 | 그 게스트에 대해 저장한 것을 지운다 |
| `GuestRenamed(name)` | `guest.name`을 바꾼 뒤, 같은 트랜잭션. Kratos가 바뀐 이름을 저장하기 직전이다 | 표시하는 이름을 바꾼다 |

핸들러는 `@register(GuestDiscarded)`로 등록하고, 모듈을 `app/shared/messagebus.py`의 `register_handlers`에 더합니다([도메인 이벤트](../development/domain-events.ko.md)).

### 4. 리소스를 지울 때

리소스 삭제를 커밋한 뒤 게스트를 모두 폐기합니다. 부르지 않아도 다음 게스트 확인에서 `MISSING`으로 폐기되지만, 그때까지 게스트 행과 Kratos identity가 남습니다.

```python
from app.domain.guest.service import discard_resource_guests

await discard_resource_guests(ResourceType.MEETING, meeting_id)
```

## 제한

- 이름은 리소스 안에서 겹치지 않고, 대소문자를 구분합니다.
- 이름 찾기와 생성은 각각 IP당 분당 10회, `/auth` 제출은 IP당 분당 10회입니다(`app/ratelimit/config.py`). 요청에 토큰이 있어도 IP로 셉니다.
- 게스트는 비밀번호를 바꾸거나 찾을 수 없습니다. 비밀번호를 잊으면 그 이름으로 다시 들어갈 수 없고, 다른 이름으로 새 게스트를 만듭니다.
- 리소스 하나의 게스트 수에는 상한이 없습니다.
- IP당 한도는 backend가 접속 주소를 바르게 알 때만 지켜집니다([배포 조건](../deployment/kratos-guest.ko.md)).

## 관련 코드

| 위치 | 내용 |
|------|------|
| `app/domain/guest/service.py` | 이름 찾기, 생성, 접근 정책, 폐기, Kratos 훅 판정 |
| `app/domain/guest/schema/dto.py` | 요청·응답, 이름 정규형 |
| `app/domain/guest/host.py` | 호스트 계약 |
| `app/domain/guest/dependencies.py` | 게스트 경로 의존성 |
| `app/models/guest.py` | `guest` 테이블 |
| `app/api/v1/guests.py` | `/v1/guests/*` |
| `app/api/kratos_hooks.py` | Kratos 훅 수신 |
| `app/api/auth_proxy.py` | `/auth` 프록시의 게스트 처리 |
| `app/core/turnstile.py` | Turnstile 토큰 확인 |
| `app/core/auth/dependencies.py` | `ensure_member` (회원 경로의 게스트 거부) |
| `tests/domain/guest/` | 테스트 |
