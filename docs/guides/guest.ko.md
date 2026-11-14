# 게스트 계정 가이드

게스트는 회원 가입 없이 리소스 하나에 들어가는 계정입니다. 이 문서는 게스트의 수명 주기, API, 그리고 리소스가 게스트를 받으려면 구현할 것을 설명합니다. Kratos와 배포 설정은 [게스트 계정 설정 (Kratos)](../deployment/kratos-guest.ko.md)에 있습니다.

## 게스트란

게스트는 회원과 같이 Kratos가 발급하는 계정입니다. 자격 증명은 Kratos가 저장하고, 세션과 JWT도 Kratos가 발급합니다. 회원과 다른 점은 다음과 같습니다.

| | 회원 | 게스트 |
|---|---|---|
| Kratos identity schema | `default` | `KRATOS_GUEST_SCHEMA_ID` (기본 `guest`) |
| 속한 곳 | 없음 | 리소스 하나 (`resource_type`, `resource_id`) |
| 로그인 식별자 | 이메일 | 서버가 만든 `<uuid4>@guest.invalid`(`handle`). 게스트가 입력하지 않는다 |
| 이름 | 선택 | 필수. 1~50자, 같은 리소스 안에서도 겹칠 수 있다 |
| 비밀번호 | Kratos 비밀번호 정책 | 비어 있지 않고 UTF-8로 72바이트 이하면 된다 |
| 이메일 인증 | 로그인에 필요 | 없음. handle을 처음부터 인증된 주소로 만든다(메일이 가지 않는 주소) |
| 접근 범위 | 회원 경로 전체 | 자기 리소스의 게스트 경로만 |

- 게스트 기능은 `GUEST_ENABLED=true`일 때만 켜집니다(기본 꺼짐). 꺼져 있으면 게스트 엔드포인트는 404이고, 게스트 토큰은 모든 경로에서 거부됩니다.
- 게스트는 자기 이름만 바꿀 수 있습니다. 로그인 식별자·비밀번호 변경과 소셜 로그인 연결은 Kratos 설정 훅이 거절합니다.
- 회원 경로(`/v1/*`의 인증 경로, GraphQL, WebSocket)는 게스트 토큰을 `403`으로 거부합니다.
- 게스트를 켜도 회원 로그인은 Kratos 기본 동작 그대로입니다. 로그인에서 backend를 부르는 것은 게스트뿐입니다.
- 게스트 JWT에는 `email` 클레임이 없고 `email_verified`는 `false`입니다. handle은 이메일로 쓰이지 않습니다.

## 수명 주기

| 단계 | 일어나는 일 |
|------|-------------|
| 입장 | `POST /v1/guests/enter`. 리소스가 게스트를 받으면(`OPEN`) 게스트 identity와 게스트 행을 만들고 Kratos 세션 토큰을 돌려준다 |
| 다시 입장 | 같은 요청. 그 리소스에서 이름이 같은 게스트 중 비밀번호가 맞는 게스트가 있으면 그 게스트로 들어간다. 없으면 새 게스트를 만든다 |
| 이름 변경 | Kratos 설정 플로우(`method: profile`)로 `traits.name`을 바꾼다. 리소스에 `GuestRenamed` 이벤트가 간다 |
| 자기 삭제 | `DELETE /v1/guests/me` |
| 폐기 | 아래 조건에서 게스트 행과 Kratos identity를 지우고 `GuestDiscarded` 이벤트를 낸다 |

게스트는 다음 경우에 폐기됩니다.

- 게스트가 자기를 삭제할 때
- 게스트 확인(로그인, 게스트 경로 요청, 이름 변경, 같은 리소스로의 입장)에서 리소스가 `EXPIRED`나 `MISSING`일 때
- 리소스가 지워지면서 `discard_resource_guests`를 부를 때

폐기된 게스트의 Kratos 세션은 바로 끊깁니다. 이미 받은 JWT는 만료(Kratos tokenizer `ttl`, 기본 10분)까지 서명은 유효하지만, 게스트 경로는 요청마다 게스트 행을 확인하므로 거부됩니다. Kratos identity 삭제가 실패해도 게스트 행은 지워지고, 행이 없는 게스트 identity는 로그인할 수 없습니다.

## API

### 입장 — `POST /v1/guests/enter`

인증이 필요 없습니다.

```json
{
  "resource_type": "meeting",
  "resource_id": "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
  "name": "민수",
  "password": "1234"
}
```

| 필드 | 규칙 |
|------|------|
| `resource_type` | 리소스 종류 (`meeting` 등) |
| `resource_id` | 리소스 UUID |
| `name` | 앞뒤 공백을 뗀 뒤 1~50자, 제어 문자 없음 |
| `password` | 비어 있지 않고 UTF-8로 72바이트 이하. 다른 규칙은 없다 |

`name`과 `password`는 다른 규칙(공백 제거, 길이, 바이트 수, 이름 비교)보다 먼저 NFC로 정규화합니다. 이름 변경은 NFC인 이름만 받습니다.

응답 (200):

```json
{
  "session_token": "ory_st_...",
  "guest_id": "0b9c...",
  "resource_type": "meeting",
  "resource_id": "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
}
```

| 상태 | 뜻 |
|------|----|
| `200` | 들어갔다 (다시 들어갔거나 새로 만들었다) |
| `403` | 리소스가 없거나, 지금 게스트를 받지 않거나, 게스트 기간이 끝났다. 세 경우 응답이 같다 |
| `409` | 이 리소스에 같은 이름의 게스트가 이미 10명이고, 그중 비밀번호가 맞는 게스트가 없다 |
| `422` | 입력 규칙 위반 |
| `429` | IP당 분당 10회를 넘었다 |
| `503` | Kratos에 닿지 않는다. 새로 만들던 게스트는 남지 않는다 |
| `404` | `GUEST_ENABLED`가 꺼져 있다 |

### JWT 받기

게스트도 회원과 같이 세션 토큰으로 JWT를 받습니다.

```http
GET /auth/sessions/whoami?tokenize_as=api
X-Session-Token: ory_st_...
```

응답의 `tokenized`가 JWT입니다. 클레임에는 `sub`(게스트의 Kratos identity id), `schema_id`(게스트 schema id), `name`이 있고 `email`은 없습니다. 이후 요청에는 `Authorization: Bearer <JWT>`를 붙입니다.

### 이름 변경

Kratos 설정 플로우를 `/auth` 프록시로 씁니다. `traits.handle`은 현재 값 그대로 보내야 합니다(`GET /auth/sessions/whoami`의 `identity.traits.handle`).

```http
GET  /auth/self-service/settings/api
X-Session-Token: ory_st_...

POST /auth/self-service/settings?flow=<flow id>
X-Session-Token: ory_st_...
Content-Type: application/json

{"method": "profile", "traits": {"handle": "<현재 handle>", "name": "철수"}}
```

- 이름 규칙은 입장과 같습니다. 규칙에 맞지 않거나 `handle`이 다르면 Kratos가 `400`으로 거절합니다(설정 훅이 거절하면 메시지 `id`는 `4000001`).
- 다른 설정(`method: password`, `oidc` 등)은 프록시가 `403`으로, Kratos 설정 훅이 다시 거절합니다.
- 게스트의 리소스가 `OPEN`이 아니면 이름을 바꿀 수 없습니다.

### 자기 삭제 — `DELETE /v1/guests/me`

게스트 JWT가 필요합니다. 응답은 `204`이고, 다시 불러도 `204`입니다. 회원 토큰은 `403`, 토큰이 없으면 `401`입니다.

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
| `GuestRenamed(name)` | Kratos가 바뀐 이름을 저장하기 직전 | 표시하는 이름을 바꾼다 |

핸들러는 `@register(GuestDiscarded)`로 등록하고, 모듈을 `app/shared/messagebus.py`의 `register_handlers`에 더합니다([도메인 이벤트](../development/domain-events.ko.md)).

### 4. 리소스를 지울 때

리소스 삭제를 커밋한 뒤 게스트를 모두 폐기합니다. 부르지 않아도 다음 게스트 확인에서 `MISSING`으로 폐기되지만, 그때까지 게스트 행과 Kratos identity가 남습니다.

```python
from app.domain.guest.service import discard_resource_guests

await discard_resource_guests(ResourceType.MEETING, meeting_id)
```

## 제한

- 같은 리소스에서 같은 이름은 10명까지입니다. 입장 한 번은 이름이 같은 게스트 수만큼 Kratos 로그인을 시도합니다.
- 이름은 앞뒤 공백만 떼고 그대로 비교합니다(대소문자 구분).
- 같은 이름으로 동시에 입장하면 10명을 잠깐 넘을 수 있습니다.
- 입장은 IP당 분당 10회입니다(`app/ratelimit/config.py`).
- 게스트는 비밀번호를 바꾸거나 찾을 수 없습니다. 비밀번호를 잊으면 같은 이름과 새 비밀번호로 새 게스트가 됩니다.

## 관련 코드

| 위치 | 내용 |
|------|------|
| `app/domain/guest/service.py` | 입장, 접근 정책, 폐기, Kratos 훅 판정 |
| `app/domain/guest/host.py` | 호스트 계약 |
| `app/domain/guest/dependencies.py` | 게스트 경로 의존성 |
| `app/api/v1/guests.py` | `/v1/guests/*` |
| `app/api/kratos_hooks.py` | Kratos 훅 수신 |
| `app/core/auth/dependencies.py` | `ensure_member` (회원 경로의 게스트 거부) |
| `tests/domain/guest/` | 테스트 |
