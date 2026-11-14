# 게스트 계정 설정 (Kratos)

이 backend를 배포하고 Kratos를 직접 운영하는 조직이 게스트 계정을 켜는 데 필요한 설정 전체입니다. Ory Kratos v26.2.0에서 확인한 설정입니다. 게스트가 무엇이고 API가 어떻게 생겼는지는 [게스트 계정 가이드](../guides/guest.ko.md)에 있습니다.

게스트를 켜려면 아래 세 쪽을 모두 갖춥니다. Kratos와 backend 중 한쪽만 바꾸면 게스트 생성·로그인이 실패하거나, 모든 회원 토큰이 `401`이 됩니다.

| 어디 | 무엇 |
|------|------|
| backend | 환경 변수 `GUEST_ENABLED`, `KRATOS_HOOK_API_KEY`, `KRATOS_ADMIN_URL`, `KRATOS_PUBLIC_URL`, `TURNSTILE_SECRET_KEY` |
| Kratos | 게스트 identity schema, JWT 클레임 매퍼의 `schema_id`, 로그인 훅, 설정 훅, backend가 닿는 admin API |
| Cloudflare Turnstile | 위젯(사이트 키는 클라이언트, 비밀 키는 backend). 게스트를 켜면 반드시 쓴다 |

게스트를 켜도 회원 로그인은 Kratos 기본 동작 그대로입니다. 로그인과 설정 변경에서 backend를 부르는 것은 게스트뿐입니다.

## 1. backend 환경 변수

| 변수 | 값 | 설명 |
|------|----|------|
| `GUEST_ENABLED` | `true` | 게스트 기능을 켠다. 기본 `false` |
| `KRATOS_HOOK_API_KEY` | 무작위 값 (32자 이상 권장) | Kratos 훅 요청의 `X-Kratos-Hook-Key` 헤더와 같아야 한다 |
| `KRATOS_ADMIN_URL` | 예: `http://127.0.0.1:4434` | backend가 게스트 identity를 만들고 지운다 |
| `KRATOS_PUBLIC_URL` | 예: `http://127.0.0.1:4433` | `/auth` 프록시가 넘기는 곳. 게스트도 회원처럼 `/auth`로 로그인하고 JWT를 받는다 |
| `TURNSTILE_SECRET_KEY` | Turnstile 위젯의 비밀 키 | 게스트 생성 요청의 `turnstile_token`을 확인한다 (1.1) |
| `TURNSTILE_VERIFY_URL` | 기본 `https://challenges.cloudflare.com/turnstile/v0/siteverify` | 토큰 확인 주소. 보통 바꾸지 않는다 |
| `KRATOS_GUEST_SCHEMA_ID` | `guest` (기본값) | Kratos의 게스트 identity schema id. 바꾸면 아래 Kratos 설정의 `'guest'`도 모두 바꾼다 |

`GUEST_ENABLED=true`인데 `KRATOS_PUBLIC_URL`, `KRATOS_ADMIN_URL`, `KRATOS_HOOK_API_KEY`, `KRATOS_GUEST_SCHEMA_ID`, `TURNSTILE_SECRET_KEY` 중 하나라도 비어 있으면 backend가 기동하지 않습니다.

```bash
GUEST_ENABLED=true
KRATOS_HOOK_API_KEY=<무작위 값>
KRATOS_PUBLIC_URL=http://127.0.0.1:4433
KRATOS_ADMIN_URL=http://127.0.0.1:4434
TURNSTILE_SECRET_KEY=<Turnstile 비밀 키>
```

`GUEST_ENABLED=true`이면 backend는 `schema_id` 클레임이 없는 토큰을 `401`로 거부합니다. 그래서 Kratos의 클레임 매퍼(2.3)를 먼저 바꾸고, 바꾼 매퍼로 발급한 토큰이 퍼진 뒤(tokenizer `ttl`, 기본 10분) backend에서 `GUEST_ENABLED`를 켭니다.

### 1.1 Cloudflare Turnstile

게스트 생성(`POST /v1/guests`)은 Cloudflare Turnstile 토큰을 요구합니다. 게스트를 켠 채 Turnstile을 끄는 설정은 없습니다.

1. Cloudflare 대시보드의 Turnstile에서 위젯을 만들고, 호스트 이름에 게스트 화면을 띄우는 클라이언트의 도메인을 넣는다. 사이트 키와 비밀 키가 나온다.
2. 사이트 키는 클라이언트에 넣는다. 클라이언트는 위젯에서 받은 토큰을 생성 요청의 `turnstile_token`으로 보낸다.
3. 비밀 키는 backend의 `TURNSTILE_SECRET_KEY`에 넣는다.

- backend는 요청마다 `TURNSTILE_VERIFY_URL`에 비밀 키와 토큰만 보냅니다(접속 주소는 보내지 않는다). backend에서 `challenges.cloudflare.com`으로 나가는 HTTPS가 열려 있어야 합니다.
- 토큰은 한 번만 확인할 수 있고 위젯이 준 뒤 5분 동안 유효합니다. 생성이 `403 GuestVerificationFailedError`면 클라이언트는 새 토큰을 받아 다시 보냅니다.
- 이름 찾기(`POST /v1/guests/lookup`)와 로그인은 토큰을 요구하지 않습니다.
- 개발·테스트용 비밀 키(Cloudflare 문서의 테스트 키): `1x0000000000000000000000000000000AA`는 어떤 토큰이든 통과시키고, `2x0000000000000000000000000000000AA`는 모두 거절합니다. 운영에 쓰지 않습니다.

### 1.2 접속 주소와 요청 한도

게스트 이름 찾기, 게스트 생성, `/auth` 제출은 IP당 분당 10회로 제한합니다. 이 한도는 backend가 방문자의 주소를 바르게 알 때만 지켜집니다.

- backend 앞에 프록시가 있으면 프록시가 `X-Forwarded-For`를 방문자 주소로 덮어쓰고, backend는 그 프록시의 요청만 받아야 합니다(`ORIGIN_VERIFY_HEADER`·`ORIGIN_VERIFY_SECRET`, 또는 `TRUSTED_PROXY_IPS`·`PROXY_FORCE`). 설정은 [환경 변수](../getting-started/configuration.ko.md)와 [레이트 리밋](../development/rate-limit.ko.md)에 있습니다.
- uvicorn의 `FORWARDED_ALLOW_IPS`를 `*`로 두면서 프록시를 거치지 않은 요청도 받으면, 요청이 적어 넣은 `X-Forwarded-For`가 그대로 방문자 주소가 됩니다.
- `/internal/kratos/hooks/*`는 Kratos만 부릅니다. 앞단에서 밖으로 열지 않는 것을 권합니다.

## 2. Kratos 설정

`kratos serve`는 `-c`를 여러 번 받고, 뒤 파일의 값으로 앞 파일의 값을 덮습니다. 목록 값(`identity.schemas`, 훅 목록)은 합쳐지지 않고 통째로 바뀌므로, 기존 목록의 항목도 다시 적습니다. 저장소의 `dev/kratos/kratos.guest.yml`이 이 방식의 예입니다.

```bash
kratos serve -c kratos.yml -c kratos.guest.yml
```

### 2.1 게스트 identity schema

게스트의 trait은 로그인 식별자 `handle`과 이름 `name`뿐입니다. 파일: `dev/kratos/guest.schema.json`

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
          "format": "email",
          "maxLength": 64,
          "ory.sh/kratos": {
            "credentials": {
              "password": {
                "identifier": true
              }
            },
            "verification": {
              "via": "email"
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

- `handle`: 비밀번호 로그인 식별자. backend가 `<guest_id>@guest.invalid`(`guest_id`는 `guest` 테이블의 행 id)로 만들고 같은 값을 인증된 주소(`verifiable_addresses`, `verified: true`)로 넣는다. 그래서 게스트도 로그인 훅 뒤의 `require_verified_address`를 통과한다. `.invalid`는 예약된 최상위 도메인이라 이 주소로 메일이 가지 않는다. 게스트는 handle을 입력하지 않는다
- `handle`의 `verification`: `require_verified_address`가 보는 인증 주소가 되려면 필요하다. `recovery`는 두지 않아 비밀번호 찾기가 없다
- `name`: 표시 이름. backend의 이름 규칙(1~50자)과 같은 길이 제한. backend는 같은 이름을 `guest.name`에도 두고 이름 찾기와 중복 검사에 쓴다
- backend의 `/auth` 프록시는 `@guest.invalid` 주소로 온 인증·복구 제출을 Kratos에 넘기지 않는다(`400 address_not_accepted`). Kratos 공개 API에 직접 온 인증 코드 요청은 Kratos가 그 주소로 메일을 큐에 넣고 주소의 `status`를 `sent`로 바꾼다. `verified`는 그대로라 로그인에는 영향이 없고, 메일은 `.invalid` 주소라 전달되지 않는다. 복구 요청은 메일을 큐에 넣지 않는다

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

세션을 JWT로 바꾸는 tokenizer 템플릿의 클레임 매퍼가 `schema_id`를 넣어야 합니다. 게스트에게는 `email` trait이 없으므로 매퍼가 `email`을 전제하면 안 됩니다. `email`은 `traits.email`에서만 읽으므로 게스트 handle(인증된 주소)은 `email` 클레임이 되지 않고, 게스트의 `email_verified`는 `false`입니다. 파일: `dev/kratos/api-jwt.claims.jsonnet`

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

`selfservice.flows.login.after.password.hooks`에서 기존 `require_verified_address` 앞에 게스트 `web_hook`을 둡니다.

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
            - hook: require_verified_address
```

훅 본문 (`dev/kratos/hook.login.jsonnet`):

```jsonnet
function(ctx)
  if ctx.identity.schema_id != 'guest' then error 'cancel' else {
    identity_id: ctx.identity.id,
    schema_id: ctx.identity.schema_id,
  }
```

- `error 'cancel'`: 게스트가 아닌 identity는 훅을 부르지 않는다. 회원 로그인은 `require_verified_address`가 지금과 같이 판정한다(미인증 회원은 `session_verified_address_required`와 `continue_with`의 인증 플로우)
- backend는 게스트 행이 있고 리소스가 `OPEN`일 때만 게스트 로그인을 허용한다. 게스트가 아닌 요청이 오면 허용한다
- `require_verified_address`: 순서대로 실행되므로 게스트 훅 뒤에 둔다. 게스트는 handle이 인증된 주소라 통과한다
- `url`: Kratos에서 닿는 backend 주소. backend는 `/internal/kratos/hooks/login`에서 받는다
- `response.parse: true`: backend의 `403` 응답이 로그인을 멈춘다. 이 값이 없으면 거절이 무시된다
- `auth`: backend는 `X-Kratos-Hook-Key`가 `KRATOS_HOOK_API_KEY`와 다르면 `401`이고, Kratos는 그 로그인을 거절한다
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
- backend는 게스트의 `profile` 변경 중 `handle`이 그대로이고 이름이 [정규형](../guides/guest.ko.md#이름과-비밀번호-규칙)이며 같은 리소스의 다른 게스트가 쓰지 않는 것만 허용하고, `password`·`oidc` 변경은 거절한다
- 이름이 바뀌는 변경을 허용할 때 backend는 `guest.name`을 먼저 바꾼다. 이름 중복은 `guest` 테이블의 UNIQUE 제약이 막는다. 훅 판정은 Kratos를 부르지 않는다
- 기존 `password` 훅(`revoke_active_sessions` 등)은 목록에 다시 적는다

### 2.6 admin API

backend가 `KRATOS_ADMIN_URL`로 admin API에 닿아야 합니다. backend가 쓰는 호출은 다음과 같습니다.

| 호출 | 용도 |
|------|------|
| `POST /admin/identities` | 게스트 identity 만들기 (`schema_id`, `traits`, 비밀번호, handle을 인증된 주소로) |
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

저장소의 `dev/kratos/kratos.guest.yml`에 있는 키(`dev-only-kratos-hook-key`)는 로컬 전용입니다. 운영에서는 새 무작위 값을 씁니다.

## 3. 게스트를 끈 상태

`GUEST_ENABLED=false`(기본)이면:

- `/v1/guests/*`와 `/internal/kratos/hooks/*`는 `404`입니다
- `schema_id`가 게스트 schema인 토큰은 모든 경로에서 거부됩니다(`403`)
- `schema_id` 클레임이 없는 토큰도 받습니다
- Kratos는 2장의 설정 없이 기존 설정으로 둡니다. 게스트 훅 설정을 남긴 채 backend만 끄면 게스트 로그인은 훅이 `404`를 받아 거절되고, 회원 로그인은 영향이 없습니다

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
  -H 'content-type: application/json' -d '{"identity_id":"x","schema_id":"default"}'
# 401 (키 없음). 404면 GUEST_ENABLED가 꺼져 있다

curl -s -w ' %{http_code}\n' -X POST "$API/internal/kratos/hooks/login" -H "X-Kratos-Hook-Key: $KEY" \
  -H 'content-type: application/json' -d '{"identity_id":"x","schema_id":"default"}'
# {} 200
```

### 4.3 생성, 로그인, JWT

`TS_TOKEN`은 Turnstile 위젯에서 받은 토큰입니다. backend가 테스트용 비밀 키(1.1)를 쓰는 환경에서는 아무 문자열이나 됩니다.

```bash
R="\"resource_type\":\"$RESOURCE_TYPE\",\"resource_id\":\"$RESOURCE_ID\",\"name\":\"확인\""

curl -s -X POST "$API/v1/guests/lookup" -H 'content-type: application/json' -d "{$R}"
# {"handle":null}

HANDLE=$(curl -s -X POST "$API/v1/guests" -H 'content-type: application/json' \
  -d "{$R,\"password\":\"1\",\"turnstile_token\":\"$TS_TOKEN\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["handle"])')

FLOW=$(curl -s "$API/auth/self-service/login/api" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
TOKEN=$(curl -s -X POST "$API/auth/self-service/login?flow=$FLOW" -H 'content-type: application/json' \
  -d "{\"method\":\"password\",\"identifier\":\"$HANDLE\",\"password\":\"1\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_token"])')
JWT=$(curl -s "$API/auth/sessions/whoami?tokenize_as=api" -H "X-Session-Token: $TOKEN" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokenized"])')
echo "$JWT" | python3 -c 'import base64,json,sys; p=sys.stdin.read().split(".")[1]; c=json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))); print(c["schema_id"], c.get("email"))'
# guest None

curl -s -o /dev/null -w '%{http_code}\n' "$API/v1/users/me" -H "Authorization: Bearer $JWT"
# 403
```

- 생성이 `403`이면 응답의 `error_type`을 봅니다. `GuestEntryRefusedError`는 리소스가 게스트를 받지 않는 것이고, `GuestVerificationFailedError`는 Turnstile 토큰입니다.
- 생성이 `503`이면 backend가 Turnstile 확인 주소나 Kratos admin API에 닿지 않는 것입니다. backend 로그를 봅니다.
- 로그인이 `400`이고 메시지 `id`가 `4000001`이면 로그인 훅이 거절한 것입니다. 훅 URL과 키를 확인합니다(4.2).

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
| Kratos가 로그인 훅 URL에 닿지 않는다 | Kratos는 세 번 시도(약 3초)한 뒤 그 게스트의 로그인을 거절한다. 회원은 인증 여부와 상관없이 게스트가 없을 때와 같다(훅을 부르지 않는다) |
| Kratos가 설정 훅 URL에 닿지 않는다 | 게스트의 설정 변경이 거절된다. 회원 설정은 영향이 없다 |
| 훅 키가 다르다 | backend가 `401`을 돌려주고 Kratos는 위와 같이 게스트 로그인·설정 변경을 거절한다 |
| backend가 Kratos admin API에 닿지 않는다 | 게스트 생성이 `503`이고 게스트를 만들지 않는다. 게스트 폐기는 게스트 행만 지우고 identity 삭제 실패를 로그에 남긴다. 행이 없는 게스트 identity는 로그인할 수 없다. 이름 찾기는 Kratos를 부르지 않아 그대로 된다 |
| backend가 Kratos 공개 API에 닿지 않는다 | `/auth` 요청이 `502`다. 회원과 게스트 모두 로그인하거나 JWT를 받을 수 없다 |
| backend가 Turnstile 확인 주소에 닿지 않는다 | 게스트 생성이 `503`이고 게스트를 만들지 않는다. 이미 만든 게스트의 로그인과 이름 찾기는 그대로 된다 |

## 6. 로컬에서 켜기

```bash
python scripts/gen_dev_jwks.py
docker compose -f compose.kratos.yaml -f compose.kratos.guest.yaml up -d
```

backend는 `compose.kratos.yaml`의 환경 변수에 다음을 더해 `0.0.0.0:2614`에서 실행합니다(Kratos 컨테이너가 `host.docker.internal:2614`로 훅을 부른다).

```bash
GUEST_ENABLED=true
KRATOS_ADMIN_URL=http://127.0.0.1:4434
KRATOS_HOOK_API_KEY=dev-only-kratos-hook-key
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
```

게스트를 받는 리소스(호스트)가 등록되어 있어야 게스트를 만들 수 있습니다. 등록된 호스트가 없으면 이름 찾기와 생성은 `403`입니다.
