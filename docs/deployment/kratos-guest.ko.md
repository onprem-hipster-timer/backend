# 게스트 계정 설정 (Kratos)

이 backend를 배포하고 Kratos를 직접 운영하는 조직이 게스트 계정을 켜는 데 필요한 설정 전체입니다. Ory Kratos v26.2.0에서 확인한 설정입니다. 게스트가 무엇이고 API가 어떻게 생겼는지는 [게스트 계정 가이드](../guides/guest.ko.md)에 있습니다.

게스트를 켜려면 아래 두 쪽을 모두 바꿉니다. 한쪽만 바꾸면 게스트 입장이 실패하거나(`503`), 모든 회원 토큰이 `401`이 됩니다.

| 어디 | 무엇 |
|------|------|
| backend | 환경 변수 `GUEST_ENABLED`, `KRATOS_HOOK_API_KEY`, `KRATOS_ADMIN_URL`, `KRATOS_PUBLIC_URL` |
| Kratos | 게스트 identity schema, JWT 클레임 매퍼의 `schema_id`, 로그인 훅, 설정 훅, backend가 닿는 admin API |

## 1. backend 환경 변수

| 변수 | 값 | 설명 |
|------|----|------|
| `GUEST_ENABLED` | `true` | 게스트 기능을 켠다. 기본 `false` |
| `KRATOS_HOOK_API_KEY` | 무작위 값 (32자 이상 권장) | Kratos 훅 요청의 `X-Kratos-Hook-Key` 헤더와 같아야 한다 |
| `KRATOS_ADMIN_URL` | 예: `http://127.0.0.1:4434` | backend가 게스트 identity를 만들고, 읽고, 지운다 |
| `KRATOS_PUBLIC_URL` | 예: `http://127.0.0.1:4433` | backend가 게스트 대신 비밀번호 로그인을 해서 세션 토큰을 받는다 |
| `KRATOS_GUEST_SCHEMA_ID` | `guest` (기본값) | Kratos의 게스트 identity schema id. 바꾸면 아래 Kratos 설정의 `'guest'`도 모두 바꾼다 |

`GUEST_ENABLED=true`인데 `KRATOS_PUBLIC_URL`, `KRATOS_ADMIN_URL`, `KRATOS_HOOK_API_KEY`, `KRATOS_GUEST_SCHEMA_ID` 중 하나라도 비어 있으면 backend가 기동하지 않습니다.

```bash
GUEST_ENABLED=true
KRATOS_HOOK_API_KEY=<무작위 값>
KRATOS_PUBLIC_URL=http://127.0.0.1:4433
KRATOS_ADMIN_URL=http://127.0.0.1:4434
```

`GUEST_ENABLED=true`이면 backend는 `schema_id` 클레임이 없는 토큰을 `401`로 거부합니다. 그래서 Kratos의 클레임 매퍼(2.3)를 먼저 바꾸고, 바꾼 매퍼로 발급한 토큰이 퍼진 뒤(tokenizer `ttl`, 기본 10분) backend에서 `GUEST_ENABLED`를 켭니다.

## 2. Kratos 설정

`kratos serve`는 `-c`를 여러 번 받고, 뒤 파일의 값으로 앞 파일의 값을 덮습니다. 목록 값(`identity.schemas`, 훅 목록)은 합쳐지지 않고 통째로 바뀌므로, 기존 목록의 항목도 다시 적습니다. 저장소의 `dev/kratos/kratos.guest.yml`이 이 방식의 예입니다.

```bash
kratos serve -c kratos.yml -c kratos.guest.yml
```

### 2.1 게스트 identity schema

게스트의 trait은 로그인 식별자 `handle`과 이름 `name`뿐입니다. 인증·복구 주소가 없어 이메일 인증과 비밀번호 찾기가 없습니다. 파일: `dev/kratos/guest.schema.json`

```json
{
  "$id": "https://kratos.invalid/identity.guest.schema.json",
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Guest",
  "type": "object",
  "properties": {
    "traits": {
      "type": "object",
      "properties": {
        "handle": {
          "type": "string",
          "title": "Handle",
          "minLength": 36,
          "maxLength": 36,
          "ory.sh/kratos": {
            "credentials": {
              "password": {
                "identifier": true
              }
            }
          }
        },
        "name": {
          "type": "string",
          "title": "Name",
          "minLength": 1,
          "maxLength": 50
        }
      },
      "required": [
        "handle",
        "name"
      ],
      "additionalProperties": false
    }
  }
}
```

- `handle`: backend가 만드는 UUID 문자열(36자)이고 비밀번호 로그인 식별자다
- `name`: 표시 이름. backend의 이름 규칙(1~50자)과 같은 길이 제한

### 2.2 identity schema 등록

```yaml
identity:
  default_schema_id: default
  schemas:
    - id: default
      url: file:///etc/config/kratos/identity.schema.json
    - id: guest
      url: file:///etc/config/kratos/guest.schema.json
```

- `default_schema_id`는 회원 schema 그대로 둔다. 셀프 가입은 기본 schema로만 되므로 아무도 게스트로 가입할 수 없다
- 게스트 identity는 backend가 admin API로만 만든다. admin API로 만들 때는 Kratos 비밀번호 정책이 적용되지 않는다

### 2.3 JWT 클레임 매퍼에 `schema_id`

세션을 JWT로 바꾸는 tokenizer 템플릿의 클레임 매퍼가 `schema_id`를 넣어야 합니다. 게스트에게는 `email` trait이 없으므로 매퍼가 `email`을 전제하면 안 됩니다. 파일: `dev/kratos/api-jwt.claims.jsonnet`

```jsonnet
local session = std.extVar('session');
local identity = session.identity;
local traits = identity.traits;
local email = if 'email' in traits then traits.email else null;
local addresses = if 'verifiable_addresses' in identity then identity.verifiable_addresses else [];
local verified = [
  a
  for a in addresses
  if a.via == 'email' && a.verified && email != null && std.asciiLower(a.value) == std.asciiLower(email)
];

{
  claims: {
    aud: 'https://api.example.com',
    schema_id: identity.schema_id,
    [if email != null then 'email' else null]: email,
    email_verified: std.length(verified) > 0,
    [if 'name' in traits then 'name' else null]: traits.name,
  },
}
```

- `schema_id`: backend는 이 값이 `KRATOS_GUEST_SCHEMA_ID`와 같으면 게스트로 보고 회원 경로에서 `403`, `GUEST_ENABLED=true`인데 클레임이 없으면 `401`로 거부한다
- `aud`: backend `OIDC_AUDIENCE`와 같은 값

### 2.4 로그인 훅

`selfservice.flows.login.after.password.hooks`의 `require_verified_address`를 backend `web_hook`으로 바꿉니다. `require_verified_address`는 인증할 주소가 없는 identity(게스트)의 로그인을 `500`으로 끝내기 때문입니다.

```yaml
selfservice:
  flows:
    login:
      after:
        password:
          hooks:
            - hook: web_hook
              config:
                url: https://api.example.com/internal/kratos/hooks/login
                method: POST
                body: file:///etc/config/kratos/hook.login.jsonnet
                response:
                  parse: true
                auth:
                  type: api_key
                  config:
                    name: X-Kratos-Hook-Key
                    value: <KRATOS_HOOK_API_KEY와 같은 값>
                    in: header
```

훅 본문 (`dev/kratos/hook.login.jsonnet`):

```jsonnet
function(ctx)
  local identity = ctx.identity;
  local addresses = if 'verifiable_addresses' in identity then identity.verifiable_addresses else [];
  local verified = std.length([a for a in addresses if a.verified]) > 0;
  if identity.schema_id != 'guest' && verified then error 'cancel' else {
    identity_id: identity.id,
    schema_id: identity.schema_id,
    verified: verified,
  }
```

- `url`: Kratos에서 닿는 backend 주소. backend는 `/internal/kratos/hooks/login`에서 받는다
- `response.parse: true`: backend의 `403` 응답이 로그인을 멈춘다. 이 값이 없으면 거절이 무시된다
- `auth`: backend는 `X-Kratos-Hook-Key`가 `KRATOS_HOOK_API_KEY`와 다르면 `401`이고, Kratos는 그 로그인을 거절한다
- `error 'cancel'`: 인증된 주소가 있는 회원은 훅을 부르지 않는다. 이런 회원의 로그인은 backend 상태와 상관없다
- 훅을 부르면 backend가 정한다. 게스트는 게스트 행이 있고 리소스가 `OPEN`일 때, 회원은 인증된 주소가 있을 때 허용한다
- `'guest'`: `KRATOS_GUEST_SCHEMA_ID`와 같은 값

### 2.5 설정 훅

`selfservice.flows.settings.after`의 `profile`, `password`, `oidc`에 `web_hook`을 겁니다. 이 훅은 Kratos가 바뀐 identity를 저장하기 전에 실행되어 변경을 거절할 수 있습니다. 훅이 없으면 게스트가 로그인 식별자를 바꾸고, 비밀번호를 바꾸고, 소셜 로그인을 연결할 수 있습니다(Kratos는 schema와 상관없이 소셜 로그인 연결을 보여 준다).

```yaml
selfservice:
  flows:
    settings:
      after:
        profile:
          hooks:
            - hook: web_hook
              config:
                url: https://api.example.com/internal/kratos/hooks/settings/profile
                method: POST
                body: file:///etc/config/kratos/hook.settings.jsonnet
                response:
                  parse: true
                auth:
                  type: api_key
                  config:
                    name: X-Kratos-Hook-Key
                    value: <KRATOS_HOOK_API_KEY와 같은 값>
                    in: header
        password:
          hooks:
            - hook: web_hook
              config:
                url: https://api.example.com/internal/kratos/hooks/settings/password
                method: POST
                body: file:///etc/config/kratos/hook.settings.jsonnet
                response:
                  parse: true
                auth:
                  type: api_key
                  config:
                    name: X-Kratos-Hook-Key
                    value: <KRATOS_HOOK_API_KEY와 같은 값>
                    in: header
            - hook: revoke_active_sessions # 기존 훅을 그대로 둔다
        oidc:
          hooks:
            - hook: web_hook
              config:
                url: https://api.example.com/internal/kratos/hooks/settings/oidc
                method: POST
                body: file:///etc/config/kratos/hook.settings.jsonnet
                response:
                  parse: true
                auth:
                  type: api_key
                  config:
                    name: X-Kratos-Hook-Key
                    value: <KRATOS_HOOK_API_KEY와 같은 값>
                    in: header
```

훅 본문 (`dev/kratos/hook.settings.jsonnet`):

```jsonnet
function(ctx)
  if ctx.identity.schema_id != 'guest' then error 'cancel' else {
    identity_id: ctx.identity.id,
    schema_id: ctx.identity.schema_id,
    traits: ctx.identity.traits,
  }
```

- URL의 마지막 경로(`profile`, `password`, `oidc`)로 backend가 어떤 변경인지 안다
- `error 'cancel'`: 게스트가 아닌 identity의 설정 변경은 훅을 부르지 않는다. 회원 설정은 backend 상태와 상관없다
- backend는 게스트의 `profile` 변경 중 `handle`이 그대로이고 이름 규칙에 맞는 것만 허용하고, `password`·`oidc` 변경은 거절한다
- 기존 `password` 훅(`revoke_active_sessions` 등)은 목록에 다시 적는다

### 2.6 admin API

backend가 `KRATOS_ADMIN_URL`로 admin API에 닿아야 합니다. backend가 쓰는 호출은 다음과 같습니다.

| 호출 | 용도 |
|------|------|
| `POST /admin/identities` | 게스트 identity 만들기 (`schema_id`, `traits`, 비밀번호) |
| `GET /admin/identities?ids=...` | 리소스 게스트들의 현재 이름 읽기 (한 번에 100개씩) |
| `GET /admin/identities/{id}` | 이름 변경 때 현재 `handle` 읽기 |
| `DELETE /admin/identities/{id}` | 게스트 폐기 |

admin API는 backend 밖으로 열지 않습니다.

### 2.7 훅 키를 환경 변수로 넣기

설정 파일에 키를 적지 않으려면 Kratos 환경 변수로 덮습니다. 목록 항목은 0부터 센 위치로 적습니다(v26.2.0에서 로그인 훅으로 확인).

```bash
SELFSERVICE_FLOWS_LOGIN_AFTER_PASSWORD_HOOKS_0_CONFIG_AUTH_CONFIG_VALUE=<키>
SELFSERVICE_FLOWS_SETTINGS_AFTER_PROFILE_HOOKS_0_CONFIG_AUTH_CONFIG_VALUE=<키>
SELFSERVICE_FLOWS_SETTINGS_AFTER_PASSWORD_HOOKS_0_CONFIG_AUTH_CONFIG_VALUE=<키>
SELFSERVICE_FLOWS_SETTINGS_AFTER_OIDC_HOOKS_0_CONFIG_AUTH_CONFIG_VALUE=<키>
```

## 3. 게스트를 끈 상태

`GUEST_ENABLED=false`(기본)이면:

- `/v1/guests/*`와 `/internal/kratos/hooks/*`는 `404`입니다
- `schema_id`가 게스트 schema인 토큰은 모든 경로에서 거부됩니다(`403`)
- `schema_id` 클레임이 없는 토큰도 받습니다
- Kratos는 2장의 설정 없이 기존 설정(`require_verified_address`)으로 둡니다. 게스트 훅 설정을 남긴 채 backend만 끄면 훅이 `404`를 받아 게스트와 이메일을 인증하지 않은 회원의 로그인이 거절됩니다. 인증된 회원은 영향이 없습니다

## 4. 설정 후 확인

`API`는 backend 주소, `KRATOS_PUBLIC`은 Kratos 공개 API 주소, `KEY`는 훅 키입니다. 게스트를 받는 리소스가 하나 있어야 4.3부터 확인할 수 있습니다(`RESOURCE_TYPE`, `RESOURCE_ID`). JSON은 `python3`로 읽습니다.

### 4.1 Kratos가 게스트 schema를 안다

```bash
curl -s "$KRATOS_PUBLIC/schemas" | python3 -c 'import json,sys; print(*[s["id"] for s in json.load(sys.stdin)])'
# default guest
```

### 4.2 훅 엔드포인트와 키

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$API/internal/kratos/hooks/login" \
  -H 'content-type: application/json' -d '{"identity_id":"x","schema_id":"default","verified":true}'
# 401 (키 없음). 404면 GUEST_ENABLED가 꺼져 있다

curl -s -w ' %{http_code}\n' -X POST "$API/internal/kratos/hooks/login" -H "X-Kratos-Hook-Key: $KEY" \
  -H 'content-type: application/json' -d '{"identity_id":"x","schema_id":"default","verified":true}'
# {} 200
```

### 4.3 입장과 JWT

```bash
TOKEN=$(curl -s -X POST "$API/v1/guests/enter" -H 'content-type: application/json' \
  -d "{\"resource_type\":\"$RESOURCE_TYPE\",\"resource_id\":\"$RESOURCE_ID\",\"name\":\"확인\",\"password\":\"1\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_token"])')
JWT=$(curl -s "$API/auth/sessions/whoami?tokenize_as=api" -H "X-Session-Token: $TOKEN" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokenized"])')
echo "$JWT" | python3 -c 'import base64,json,sys; p=sys.stdin.read().split(".")[1]; c=json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))); print(c["schema_id"], c.get("email"))'
# guest None

curl -s -o /dev/null -w '%{http_code}\n' "$API/v1/users/me" -H "Authorization: Bearer $JWT"
# 403
```

입장이 `503`이면 backend 로그에서 Kratos 오류를 봅니다. 로그인 훅의 키가 다르면 Kratos가 게스트 로그인을 거절해 입장이 `503`이 됩니다.

### 4.4 회원

- 이메일을 인증한 회원으로 로그인하면 성공하고, backend 로그에 `/internal/kratos/hooks/login` 요청이 없습니다.
- 회원 JWT를 위와 같이 디코드하면 `schema_id`가 `default`입니다.

### 4.5 정리

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$API/v1/guests/me" -H "Authorization: Bearer $JWT"
# 204
curl -s -o /dev/null -w '%{http_code}\n' "$API/auth/sessions/whoami" -H "X-Session-Token: $TOKEN"
# 401
```

## 5. 장애 때 동작

| 상황 | 동작 |
|------|------|
| Kratos가 로그인 훅 URL에 닿지 않는다 | Kratos는 세 번 시도(약 3초)한 뒤 그 로그인을 거절한다. 이메일을 인증한 회원은 훅을 부르지 않으므로 그대로 로그인된다. 게스트와 이메일을 인증하지 않은 회원은 거절된다 |
| Kratos가 설정 훅 URL에 닿지 않는다 | 게스트의 설정 변경이 거절된다. 회원 설정은 영향이 없다 |
| 훅 키가 다르다 | backend가 `401`을 돌려주고 Kratos는 위와 같이 거절한다 |
| backend가 Kratos admin·공개 API에 닿지 않는다 | 입장이 `503`이고 게스트를 만들지 않는다. 게스트 폐기는 게스트 행만 지우고 identity 삭제 실패를 로그에 남긴다. 행이 없는 게스트 identity는 로그인할 수 없다 |

## 6. 회원에게 달라지는 점

게스트를 켜면 이메일을 인증하지 않은 회원의 로그인 거절 응답이 바뀝니다.

| | 게스트 끔 (`require_verified_address`) | 게스트 켬 (로그인 훅) |
|---|---|---|
| 응답 | 오류 `error.id: session_verified_address_required` | `400`, 플로우 메시지 `id: 4000010` |
| 인증 플로우 | `continue_with`에 새 인증 플로우가 오고 코드를 다시 보낸다 | 오지 않는다. 클라이언트가 인증 플로우를 만든다 |

클라이언트는 두 응답을 모두 "이메일 인증 필요"로 다룹니다.

## 7. 로컬에서 켜기

```bash
python scripts/gen_dev_jwks.py
docker compose -f compose.kratos.yaml -f compose.kratos.guest.yaml up -d
```

backend는 `compose.kratos.yaml`의 환경 변수에 다음을 더해 `0.0.0.0:2614`에서 실행합니다(Kratos 컨테이너가 `host.docker.internal:2614`로 훅을 부른다).

```bash
GUEST_ENABLED=true
KRATOS_ADMIN_URL=http://127.0.0.1:4434
KRATOS_HOOK_API_KEY=dev-only-kratos-hook-key
```

게스트를 받는 리소스(호스트)가 등록되어 있어야 입장할 수 있습니다. 등록된 호스트가 없으면 입장은 `403`입니다.
