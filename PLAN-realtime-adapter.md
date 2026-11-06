# 타이머 실시간 전달: 어댑터 구조 (온프렘 = 프로세스 내 WS, 호스팅 = Cloudflare Worker+DO) — 플랜

## Context

- 이 프로젝트는 오픈소스·온프렘(`onprem-hipster-timer`, `compose.yaml`)입니다. 실시간 전달은 외부 벤더 없이도 동작해야 합니다.
- 지금 구조(Cloud Run 프로세스 안의 WebSocket, `ConnectionManager`)는 온프렘에서는 문제가 없지만, 우리 호스팅에서는 열린 소켓이 Cloud Run 인스턴스를 깨워 두어 scale-to-zero가 깨집니다(공식 문서: 열린 WebSocket이 있는 인스턴스는 인스턴스 기반 과금). 또 `friend_activity`가 공개 범위와 무관하게 친구 전원에게 갑니다(ws_handler.py:349-391).
- **목표**: 메시지 서버를 어댑터로 분리합니다. 온프렘은 지금처럼 프로세스 안에서, 우리 호스팅은 Cloudflare Worker + Durable Object에서 소켓을 들고, **클라이언트는 한 벌**입니다. 명령·접근 판정·상태는 어느 모드든 Python이 결정합니다.
- **근거 원칙**: 저장소 문서는 검증 전 주장으로 다뤘고, 판단은 코드·git 이력·Terraform·FastAPI/SQLAlchemy 소스·Cloudflare 공식 문서·npm 메타데이터로 했습니다.

## 확정된 결정 (사용자 답변)

- 어댑터 구조. 온프렘 기본 = `inprocess`, 우리 호스팅 = `cloudflare`.
- 명령(create/pause/resume/stop)은 두 모드 모두 **REST**. 소켓은 **수신 전용**.
- Worker 메시지 서버는 **별도 private 레포**(`onprem-hipster-timer/realtime-worker`, 사용자가 생성)에 둡니다. 런타임 의존성은 검증된 **jose 하나**이고, partyserver·hono·zod는 활동·CVE·적합성 검토 끝에 제외했습니다(단계 3 참고).
- 서비스 전이라 전환 기간·구버전 앱은 고려하지 않습니다. 기존 WS 명령 핸들러는 제거합니다.
- 공개 범위 **엄격 적용**. 권한 경계 설정 UI는 후속. 비친구 대상(PUBLIC, 이메일 도메인) 전달은 범위 밖.
- elapsed 문제는 별도 fix 브랜치에서 먼저.
- 관리형 서비스(AppSync, Firestore, Pusher)와 Centrifugo 호스팅은 제외: 온프렘에서 쓸 수 없거나(관리형), 우리가 VM·바이너리를 운영해야 합니다(Centrifugo). 비용 근거는 이전 조사(AppSync 월 $1 미만, Cloud Run 인스턴스 과금 월 $45, e2-micro 월 $7~12)로 남깁니다.

## 목표 구조

```
Flutter 앱 (한 벌)
 ├─ 명령/조회: HTTPS api/v1/*  (REST)
 └─ 수신:      WSS <REALTIME_WS_URL>   Sec-WebSocket-Protocol: authorization.bearer.<Kratos JWT>
        온프렘:  wss://api/v1/ws/timers      → FastAPI ConnectionManager (수신 전용)
        호스팅:  wss://api/realtime/ws       → Cloudflare Worker → UserHub DO (사용자당 1개, Hibernation)

backend: 커밋 직후, 응답 전에 publisher.publish(users, message)
   inprocess  → connection_manager.send_to_user(...)  (온프렘 기본)
   cloudflare → POST https://api/realtime/push  Authorization: Bearer <REALTIME_PUSH_SECRET>
```

- 호스팅 모드의 Worker는 Kratos JWT를 backend가 서빙하는 JWKS로 직접 검증합니다(jose). 티켓은 없습니다.
- `/realtime/*`은 wrangler `routes`로 새 Worker에 붙고, 같은 호스트의 custom domain(api-proxy)보다 route가 우선합니다(Cloudflare 문서). api-proxy는 WS 업그레이드를 410으로 막는 변경(PR #8)만 유지합니다.

## 계약 (두 모드 공통)

### 1) 소켓 메시지 (기존 `WSServerMessage` 봉투 유지 + `id`)

```json
{"id": "<uuid4>", "type": "timer.updated", "from_user": "<sub>", "timestamp": "…+00:00",
 "payload": {"action": "pause", "actor_name": "<표시명|null>", "timer": {"…": "TimerData, UTC aware"}}}
```

- `type`/`action`: `timer.created`(start), `timer.updated`(pause, resume, stop, cancel, update), `timer.deleted`(delete, `timer`는 null).
- 연결 직후 서버가 `connected`를 보냅니다. **`sync_result`는 없앱니다**(DO는 DB를 못 보므로). 클라이언트는 연결·재연결 직후 REST로 다시 맞춥니다.
- `elapsed_time`은 저장값. 클라이언트가 RUNNING일 때 `elapsed_time + (now - started_at)`로 표시(단계 1 전제).
- 클라이언트 규칙: `id` 중복 제거 → `timer.updated_at`이 보유값보다 작으면 무시 → `timer.deleted`는 tombstone → 재연결 시 REST 재동기화. 모든 타이머 REST 호출에 `timezone=UTC`.
- 친구 알림 SnackBar는 `from_user ≠ 내 sub`인 이벤트로. `friend_activity` 타입은 제거.
- 클라이언트 → 서버 메시지는 `ping`(문자열)뿐. 서버는 `pong`. 그 외는 무시.

### 2) 인증
- 두 모드 모두 `Sec-WebSocket-Protocol: authorization.bearer.<jwt>`, 서버는 101에 그 값을 echo(브라우저 요구).
- 온프렘: 기존 `get_ws_current_user`. 호스팅: Worker가 `jose.createRemoteJWKSet(https://api/auth/.well-known/jwks.json)` + `jwtVerify(alg ES256, iss, aud)`. 실패하면 1008로 닫음(기존 앱 규약과 같음).
- 호스팅 소켓 수명 24시간(DO가 attachment에 만료 기록, 만료 시 4000으로 닫음 → 즉시 재연결). JWT(10분)는 연결 시점에만 검증.

### 3) push (backend → Worker, 호스팅 모드만)
- `POST https://api/realtime/push`, `Authorization: Bearer <REALTIME_PUSH_SECRET>`(Worker는 `timingSafeEqual`).
- 본문 `{"users": ["<sub>", …], "message": {…봉투…}}`, users 최대 40명(넘으면 413).
- Worker는 검증 후 202를 바로 돌려주고 `ctx.waitUntil`로 사용자별 `UserHub.deliver()`.

### 4) OIDC discovery (backend)
- `GET /auth/.well-known/openid-configuration`, `GET /auth/.well-known/jwks.json`(=`settings.OIDC_JWKS`, `Cache-Control: public, max-age=3600`). 인증 없음, `/auth/{path:path}` 프록시(auth_proxy.py:185)보다 먼저 등록.

## 단계 0 — 플랜 저장
- `backend/PLAN-realtime-adapter.md`로 저장(untracked). 사용자 검토 전 구현 금지.

## 단계 1 — backend: 조회 경로의 elapsed (브랜치 `fix/timer-read-elapsed`)
- 조회 메서드(service.py:142~332)가 RUNNING 타이머의 `elapsed_time`을 관리 객체에 더하고 GET이 커밋해 DB 누적·`updated_at` 오염·frontend 이중 가산이 생깁니다. 조회는 저장값을 반환하도록 가산을 지우고, 명령의 가산은 유지. `test_service.py:1774-1776`(조회 80)을 저장값(60)으로. 실패 테스트(소유자·친구 GET 뒤 새 세션으로 DB 값 확인) → 수정 → 전체 테스트.

## 단계 2 — backend 본 작업 (브랜치 `feat/realtime-adapter`, `feat/webrtc-p2p-signaling`에서 이름만 변경)

1. `feat(auth): Kratos JWT용 OIDC discovery와 JWKS 서빙` — 계약 4). 새 app/api/oidc_discovery.py. 테스트: JSON·캐시 헤더·비었을 때 404·더블 슬래시.
2. `feat(realtime): 응답 전 커밋과 커밋 후 실행 큐`
   - session.py: `get_db_transactional` 세션을 받아 `yield` 뒤 `commit_with_events`하는 래퍼를 `Depends(…, scope="function")` alias로(FastAPI 0.142.2: function scope는 응답 전에 닫히고, 캐시 키가 같아 `get_current_user_synced`와 같은 세션). `get_db`/`get_db_transactional`은 그대로.
   - uow.py: `enqueue_after_commit(session, item)`; `after_commit`은 `in_nested_transaction()`이면 반환(SAVEPOINT RELEASE도 발생), `after_transaction_end`는 `parent is None`일 때만 큐 비움. 리스너 본문 try/except. docstring에 begin_nested 안 enqueue 금지.
3. `feat(realtime): publisher 어댑터` — 새 app/realtime/publisher.py
   - `Publisher` Protocol: `publish(users: set[str], message: dict)`. 구현 `InProcessPublisher`(connection_manager로 전송; 동기 큐 리스너에서 호출되므로 `anyio.from_thread`/loop handoff 처리)와 `CloudflarePublisher`(httpx, Bearer, 40명 분할, 전체 기한 2초, 5xx·연결 오류 1회 재시도, 실패는 `realtime_push_failed` 로그).
   - 설정: `REALTIME_BACKEND = inprocess|cloudflare`(기본 inprocess), `REALTIME_PUSH_URL`, `REALTIME_PUSH_SECRET`. cloudflare인데 URL/시크릿이 비면 기동 실패(production validator).
4. `feat(visibility): 실시간 수신자 계산` — `VisibilityService.get_realtime_recipients(...)`: 행 없음·PRIVATE·ALLOWED_EMAILS → 없음, FRIENDS·PUBLIC → 친구 전원, SELECTED_FRIENDS → 친구 ∩ allow list. 테스트는 `can_access`와 결과 일치 확인.
5. `feat(timer): 타이머 변경을 실시간 push로 적재` — create/pause/resume/stop/cancel/update가 flush 뒤 봉투를 큐에, delete는 visibility 삭제 **전**에 수신자 계산. 조립은 app/domain/timer/realtime.py.
6. `feat(timer): REST 타이머 명령 복원` — 8edc3eb 직전 경로(`POST ""` 201, `PATCH /{id}/pause|resume`, `POST /{id}/stop`), 응답 전 커밋 alias(기존 PATCH/DELETE도).
7. `refactor(websocket): 타이머 WebSocket을 수신 전용으로` — `/v1/ws/timers` 유지하되 명령 디스패치·`TimerWSHandler`·`sync_result`·`friend_activity` 제거, `ping`→`pong`만 처리, `connected` 전송. WS rate limit은 연결 제한만 유지. `schema/ws.py`는 `TimerData`와 봉투만. WS 테스트의 pause_history·timezone 검증은 REST 테스트로 이관.
8. `docs(realtime)` — docs/development/realtime-adapter.ko.md(두 모드, 계약, 재동기화), docs/api/websocket.{ko,en}.md 갱신, timer 가이드, configuration(새 env), mkdocs nav, CHANGELOG `[Unreleased]`(영어).

## 단계 3 — Worker 메시지 서버 (새 private 레포, 예: `onprem-hipster-timer/realtime-worker`)

- **스택**: TypeScript, wrangler 4.158. **런타임 의존성 3개(exact pin)**: jose 6.2.15(JWT 검증 전담), hono 4.13.16(라우터·`bearerAuth`만; `hono/jwt`·`hono/jwk`·jsx·serveStatic·CORS는 import하지 않음), zod 4.6.7(backend가 보내는 본문 스키마 + `z.infer` 타입). 개발 의존성 wrangler·vitest·@cloudflare/vitest-plugin 1.6.0·typescript. 런타임 타입은 `wrangler types`로 생성.
  - 결정 근거(2026-11-06): jose는 CVE 3건이 모두 JWE 경로이고 JWS 검증 경로 무사고, 메이저 전체 동시 패치 이력. hono는 2026년 CVE 25건이 외부 신고+당일 패치로 대응 품질이 좋고 라우터 코어 결함은 없음; 다만 `hono/jwt`·`hono/jwk`의 스킴 미검사(CVE-2026-47673)·NumericDate(CVE-2026-44459) 때문에 JWT는 jose 전담. zod는 2건 모두 신속 대응. 확장 구조(presence 콜백, 채널 ws, 채널 리셋)에서 라우트·스키마가 늘어나므로 처음부터 hono+zod로 통일. partyserver는 101 echo 불가·0.x 추적·확장 시점에도 런타임 API로 1:1 대체되어 제외. PUBLIC 채널 착수 시 Centrifugo 전환 재비교.
  - 공급망: lockfile integrity 고정, `npm ci`, dependabot 월 단위 그룹, 빌드 산출물에 미사용 hono 모듈이 없는지 CI에서 grep.
  - 소켓 수명주기·ping(`setWebSocketAutoResponse`)·101 헤더·전달은 Cloudflare 런타임 API 직접(공식 Hibernation 예제 그대로). `wrangler.jsonc`에 DO 바인딩 `USER_HUB` + `exports: { UserHub: { type: "durable-object", storage: "sqlite" } }`, `routes: [{ pattern: "<api_host>/realtime/*", zone_name: "<zone>" }]`, vars `JWKS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`.
- **코드(≈120줄, 모듈별)**
  - ① `auth.ts`: `jose.createRemoteJWKSet(JWKS_URL)` + `jwtVerify(token, jwks, {algorithms: ["ES256"], issuer, audience})`. 서브프로토콜 `authorization.bearer.<jwt>`에서 토큰 추출.
  - ② `index.ts`(hono app): `app.get("/realtime/ws")` — `GET /realtime/ws` → ①로 sub 확인(실패 시 WebSocketPair 수락 후 1008로 닫음) → URL에서 `_pk` 등 쿼리 제거 → `env.USER_HUB.getByName(sub).fetch(req)` → 돌아온 101에 `Sec-WebSocket-Protocol: authorization.bearer.<jwt>`를 **Worker가 아니라 DO가** 넣으므로 그대로 반환. `app.post("/realtime/push", bearerAuth({token: env.PUSH_SECRET}))` → ③. 그 외 404(hono 기본).
  - ③ push: Bearer는 hono `bearerAuth`(상수 시간 비교, 401), 본문은 zod `PushBody = z.object({users: z.array(z.string().uuid()).min(1).max(40), message: z.record(z.unknown())})`로 검증(400, 41명 이상은 413), 202 반환 후 `ctx.waitUntil(Promise.allSettled(users.map(u => env.USER_HUB.getByName(u).deliver(message))))`.
  - ④~⑧ `user_hub.ts`(DurableObject): 생성자에서 `setWebSocketAutoResponse(new WebSocketRequestResponsePair("ping", "pong"))`; `fetch`는 `WebSocketPair` 생성 → `acceptWebSocket(server)` → `serializeAttachment({exp: now+24h})` → `new Response(null, {status: 101, webSocket: client, headers: {"Sec-WebSocket-Protocol": <요청의 authorization.bearer.* 값>}})`; `deliver(message)` RPC는 `getWebSockets()` 순회하며 만료는 4000으로 닫고 나머지에 `send(JSON.stringify(message))`; `webSocketClose/Error`는 로그만.
- **partyserver 0.5.10 소스 감사 결과(제외 결정의 근거; dist/index.js 935줄 전부 읽음, GitHub 태그 소스와 일치)**
  - 네트워크 호출·eval·환경 변수 접근 없음. 런타임 의존성은 nanoid 하나(wrangler 번들 조건에서 `index.browser.js` → `crypto.getRandomValues`).
  - 101 응답에 `Sec-WebSocket-Protocol`을 echo하지 않아 우리 인증(서브프로토콜)과 맞지 않음. **이 점이 제외 사유 중 하나.** plain DO에서는 101을 우리가 만들므로 헤더를 넣을 수 있음(Miniflare #179: Workers는 이 헤더를 사용자가 직접 넣어야 하며, 중복으로 넣으면 브라우저가 실패).
  - `routePartykitRequest`는 `/parties/<binding>/<name>` 경로로 **클라이언트가 DO 이름을 고를 수 있게** 하므로 쓰지 않음. `getServerByName(env.USER_HUB, sub)`만 사용(sub는 검증된 JWT에서).
  - 쿼리 `_pk`로 클라이언트가 연결 id를 지정할 수 있음(같은 허브의 다른 연결과 충돌 가능). Worker가 DO로 넘기기 전에 `_pk`를 제거.
  - 세션 설정 중 예외가 나면 `err.stack`을 소켓으로 클라이언트에 보냄(정보 노출). `onConnect`/`getConnectionTags`에서 예외를 던지지 않도록 감싸고, 테스트로 고정.
  - 에러 시 `broadcast`는 1011로 닫음, hibernation 경로는 attachment에 `__pk`/`__user`를 저장(setState 2KB 제한). 우리 용도에 문제 없음.
- **jose 6.2.15 감사**: 80개 파일·의존성 0, eval·환경 접근 없음. 유일한 아웃바운드는 `createRemoteJWKSet`의 fetch(캐시 기본 10분, cooldown 30초, timeout 5초, Workers 감지 코드 있음). ES256은 WebCrypto로 처리.
- **공급망**: jose·hono·zod 모두 npm provenance 증명이 없음. `package-lock.json`으로 integrity를 고정하고 `npm ci`만 사용, exact pin, dependabot 월 단위 그룹 PR은 diff를 읽고 병합.
- **테스트(vitest)**: JWT 정상/alg 변조/만료/aud 불일치 → 1008; 다른 사용자 JWT는 자기 허브로만; `?_pk=`·`/parties/*` 무시; Bearer 불일치 401, 41명 413, 본문 형식 오류 400; 연결·deliver·ping 자동 응답; 101에 서브프로토콜 1회 echo; 24h 만료 4000; 설정 중 예외가 클라이언트로 새지 않음.
- **CI**: `cloudflare/wrangler-action@v4`(레포 시크릿 `CLOUDFLARE_API_TOKEN`(Edit Cloudflare Workers 템플릿 + Zone Workers Routes), `CLOUDFLARE_ACCOUNT_ID`), main push 시 `wrangler deploy`. Worker 시크릿 `PUSH_SECRET`은 `wrangler secret put`으로 1회(운영자).
- **문서**: README에 계약, 로컬 실행(`wrangler dev`), 온프렘에서는 필요 없음을 명시.

## 단계 4 — infra (브랜치 `feat/realtime-adapter`)

- `secrets.tf` `manual_secrets`에 `realtime-push-secret` 추가(사람이 값을 넣고 같은 값을 Worker 시크릿에 넣음). `env.tf` api env에 `REALTIME_BACKEND = "cloudflare"`, `REALTIME_PUSH_URL = "https://${var.api_host}/realtime/push"`, secrets에 `REALTIME_PUSH_SECRET`.
- Terraform은 realtime Worker 스크립트·라우트를 관리하지 않습니다(wrangler 소유). README에 두 저장소의 책임 경계를 적습니다.
- plan.tftest.hcl에 env·secret 단언 추가. 운영자 확인: Cloudflare API 토큰(Worker 레포용)에 Workers Routes 권한.

## 단계 5 — frontend (브랜치 `feat/realtime-adapter-client`)

- REST 클라이언트 재생성(`lib/openapi/openapi.json` 갱신 → swagger_parser·build_runner). 명령은 REST, `timezone=UTC`, 명령 응답도 `updated_at` 규칙으로 즉시 반영.
- **표시 계산 통일**: RUNNING 표시는 `elapsed_time + (now - started_at)` 한 함수로. `schedule_timer_section.dart`(지금은 `elapsedTime`을 그대로 표시)와 todo 쪽 provider도 이 함수를 쓴다.
- **시계 보정**: 기기 시계를 믿지 않는다. 타이머 REST 응답의 `Date` 헤더로 `offset = server_time - client_time`을 추정(여러 응답으로 평활)하고, 표시에 쓰는 `now`에 offset을 더한다.
- 기존 `timer_ws_client.dart`를 수신 전용으로 축소: URL은 `AppConfig.realtimeWsUrl`(기본 `wss://api/v1/ws/timers`, 호스팅 빌드는 `/realtime/ws`), 서브프로토콜 인증 유지, 연결 직후 REST 재동기화, 45초 `ping`, `connected`/이벤트 봉투 파싱(`id` dedupe, `updated_at`, tombstone), 닫힘 코드(1008 중단, 4000 즉시 재연결, 그 외 백오프+지터 — `origin/feat/ws-reconnect`의 `reconnectDelay`와 테스트 흡수, 브랜치는 닫음). foreground 복귀 시 재연결.
- `friend_activity` 모델·SnackBar를 `from_user ≠ me` 이벤트 기반으로 교체.
- 테스트: 중복 id, 오래된 updated_at, tombstone, offset 없는 문자열, 닫힘 코드별 동작.

## 단계 6 — 후속 (범위 밖, 확장 경로를 미리 적어 둠)

- **로드맵 결정(사용자)**: 실시간 공개 범위는 당장 친구 단계(FRIENDS·SELECTED·정확한 이메일)까지. PUBLIC·이메일 도메인 규칙은 사용자 기반이 안정된 뒤. presence는 "친구 온라인·타이머 중 표시" 수준.
- **구조 선택 근거**: 친구 단계는 수신자를 셀 수 있어 사용자 채널 push로 충분하고, 친구 presence도 사용자 채널로 됩니다. 그래서 Centrifugo(채널·presence 내장, 대신 상시 컨테이너 호스팅 월 $7~45)보다 DO 어댑터(호스팅 $0, 온프렘 추가 설치 0)를 유지합니다. 두 벌 구현이 늘어나는 지점은 아래 두 기능뿐이며, 그때 다시 비교합니다.
- **친구 presence 설계(후속)**: 메시지 서버가 사용자의 첫 연결·마지막 끊김을 backend에 알립니다(호스팅: UserHub DO가 `getWebSockets().length`가 0↔1로 바뀔 때 `POST /v1/internal/presence` + Bearer; 온프렘: ConnectionManager가 같은 함수를 직접 호출). backend가 `status: online|offline` 이벤트를 `get_realtime_recipients`(FRIENDS 기준)로 친구에게 push. "타이머 중"은 이미 timer 이벤트로 전달됨. DO 쪽 ≈15줄, backend 라우트 1개. Cloud Run이 연결/해제마다 깨어나므로 디바운스(끊긴 뒤 30초 유지)를 둠.
- **PUBLIC·도메인 규칙 실시간(후속)**: 타이머별 채널 DO(`TimerChannel`, UserHub와 같은 패턴) + backend가 `can_access` 통과 시 발급하는 구독 토큰(joserfc HS256, `{sub, ch, exp}`) + 공개 범위 변경 시 채널 리셋. 온프렘 WS에도 채널 구독 추가. 이 시점에 Centrifugo 전환과 비용을 다시 비교(두 벌 유지 vs 컨테이너 호스팅).
- 타이머 공개 범위 설정 UI와 `timer.removed`. Cloud Run 타임아웃 단축(WS가 빠지므로). Workers Paid($5/월) 전환 기준: API 트래픽이 하루 10만 건에 근접할 때.

## 비용 (Cloudflare 공식, 2026-11)
- Workers Free: 하루 10만 요청(api-proxy와 합산), DO 하루 10만 요청·13,000 GB-s, SQLite만. 들어오는 WS 메시지 20건=1건, 나가는 메시지·Hibernation 무료. 지금 규모 **$0**.
- Workers Paid: 월 $5 정액(Workers 1,000만, DO 100만 요청 + 400,000 GB-s 포함, 초과 종량).

## 배포 순서
1. backend 단계 1 → 2-1(discovery) 배포.
2. Worker 레포 스파이크 → 배포(route까지). 이 시점에 api-proxy의 410은 `/realtime/*`에 영향 없음.
3. infra 단계 4 apply(env·secret). 기존 이미지는 모르는 env를 무시(pydantic-settings 기본).
4. backend 단계 2 나머지 + frontend 단계 5 배포.
- 되돌리기: `REALTIME_BACKEND=inprocess`로 바꾸면 호스팅도 프로세스 내 WS로 동작(비용은 예전처럼).

## 검증
- backend: 전체 `pytest`. 새 테스트 — oidc_discovery, after_commit(루트/SAVEPOINT 경우), publisher(inprocess 전달·cloudflare Bearer/분할/재시도/기한/URL 비면 미호출), realtime_recipients(`can_access` 일치), timers_rest_commands(상태·pause_history·봉투·수신자·응답 전 커밋 순서), websocket_receive_only(connected·ping/pong·명령 메시지 무시).
- worker 레포: `npm test`, `wrangler deploy --dry-run`.
- infra: fmt/validate/test, tflint, trivy.
- frontend: analyze, custom_lint, test.
- 수동 E2E: 온프렘 모드 — 로컬 compose로 REST pause → 같은 계정 두 소켓에 `timer.updated`. 호스팅 모드 — `wrangler dev` + backend `REALTIME_BACKEND=cloudflare`로 같은 시나리오, 잘못된 JWT는 1008.

## 커밋·브랜치 규칙
- `type(scope): 한국어 설명`. AI 문구·트레일러 금지, CLAUDE.md 커밋 금지. push·PR·레포 생성·원격 삭제는 매번 허가 후.
