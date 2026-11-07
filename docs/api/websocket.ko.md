# WebSocket API

타이머 변경을 실시간으로 **받기만** 하는 소켓입니다. 타이머 명령(생성·일시정지·재개·종료·수정·삭제)은 [REST API](../guides/timer.ko.md)로 보내고, 커밋된 변경은 이 소켓으로 소유자의 다른 기기와 공개 범위상 받을 수 있는 친구에게 전달됩니다.

배포 구조와 계약 전체는 [실시간 전달](../development/realtime-adapter.ko.md)을 참고하세요.

## 연결

### 엔드포인트

전달 모드(`REALTIME_BACKEND`)에 따라 주소가 다릅니다. 메시지 형식은 같습니다.

| 모드 | 주소 |
|------|------|
| `inprocess` (기본) | `ws://localhost:2614/v1/ws/timers`, `wss://your-domain.com/v1/ws/timers` |
| `cloudflare` (분리된 Worker) | `wss://your-domain.com/realtime/ws` |

### 테스트 링크

**자체 WebSocket Playground** (개발 모드 전용, `inprocess`):

- **WebSocket Playground**: [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground)

JWT를 입력하고 연결하면 받은 메시지가 표시되고 `ping`을 보낼 수 있습니다. 타이머 명령을 Swagger UI 등으로 REST 호출하면 그 이벤트가 표시됩니다.

[wscat](https://github.com/websockets/wscat) 등으로 `Sec-WebSocket-Protocol` 헤더에 토큰을 넣어 직접 연결할 수도 있습니다.

### 인증

!!! warning "주의"
    **보안**: 로그 노출 위험으로 인해 쿼리 매개변수를 통한 인증은 지원하지 않습니다.

인증은 `Sec-WebSocket-Protocol` 헤더를 통해 수행됩니다:

```
Sec-WebSocket-Protocol: authorization.bearer.<jwt_token>
```

서버는 WebSocket 핸드셰이크를 완료하기 위해 응답에 동일한 서브프로토콜을 반환합니다. JWT는 연결할 때만 검증합니다.

!!! warning "주의"
    **중요**: WebSocket 연결이 작동하려면 `CORS_ALLOWED_ORIGINS`에 WebSocket URL을 추가해야 합니다:
    - 개발: `ws://localhost:2614,ws://127.0.0.1:2614`
    - 프로덕션: `wss://your-domain.com`

## 메시지

### 클라이언트 → 서버

| 메시지 | 설명 |
|--------|------|
| `ping` (문자열) | 연결 유지. 서버가 `pong`으로 답합니다 |

그 외 메시지는 무시합니다.

### 서버 → 클라이언트

모든 메시지는 같은 봉투입니다:

```json
{
  "id": "6f1c0c1e-8a53-4d6e-9d0a-2b1f5f0c9a11",
  "type": "timer.updated",
  "from_user": "<행위자 sub>",
  "timestamp": "2026-11-06T10:30:00+0000",
  "payload": {
    "action": "pause",
    "actor_name": "홍길동",
    "timer": { "id": "…", "status": "PAUSED", "elapsed_time": 1800, "…": "…" }
  }
}
```

| `type` | `payload` |
|--------|-----------|
| `connected` | `{}` — 연결 직후 한 번 |
| `timer.created` | `{ action: "start", actor_name, timer }` |
| `timer.updated` | `{ action: "pause" \| "resume" \| "stop" \| "cancel" \| "update", actor_name, timer }` |
| `timer.deleted` | `{ action: "delete", actor_name, timer: null, timer_id }` |

- `id`: 메시지 ID. 같은 메시지를 두 번 받으면 버립니다.
- `from_user`: 변경을 일으킨 사용자의 `sub` (`connected`는 `null`). 내 `sub`가 아니면 친구의 활동입니다.
- `timer`: 커밋된 타이머. 시각은 모두 UTC이고 REST 응답(`timezone=UTC`)과 같은 형식입니다. `elapsed_time`은 저장된 누적값입니다(RUNNING이면 `now - started_at`을 더해 표시).

!!! note "필드 이름"
    페이로드 필드는 서버 DTO와 동일하게 `snake_case`를 사용합니다. 예: `elapsed_time`, `timer_id`, `actor_name`.

## 재동기화

소켓은 연결 전이나 끊긴 동안의 메시지를 다시 보내지 않습니다. 클라이언트는 다음을 지킵니다.

1. 연결·재연결 직후 REST로 타이머를 다시 조회합니다 (`timezone=UTC`).
2. `id`로 중복을 버립니다.
3. `timer.updated_at`이 가진 값보다 이전이면 버리고, 같거나 나중이면 반영합니다. REST 응답에도 같은 규칙을 씁니다.
4. `timer.deleted`를 받은 타이머의 이전 이벤트는 버립니다.

## 사용 예시

### JavaScript/TypeScript

```javascript
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers',
  [`authorization.bearer.${accessToken}`]  // 인증용 서브프로토콜
);

ws.onopen = () => {
  resyncTimersFromRest();  // REST로 다시 맞춤
};

ws.onmessage = (event) => {
  if (event.data === 'pong') return;
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'timer.created':
    case 'timer.updated':
      applyTimer(message);  // id 중복·updated_at 확인 후 반영
      break;
    case 'timer.deleted':
      removeTimer(message.payload.timer_id);
      break;
  }
};

// 연결 유지
setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 45000);
```

## Rate Limiting

`inprocess` 소켓은 연결 수에 제한이 있습니다 (기본: 60초당 10회, `WS_CONNECT_MAX`/`WS_CONNECT_WINDOW`). 넘으면 `4029`로 닫습니다.

> 📖 **상세 가이드**: [Rate Limiting 가이드](../development/rate-limit.ko.md)

## Close Codes

| Close Code | 이름 | 설명 | 재연결 |
|-----------|------|------|--------|
| `1000` | Normal Closure | 정상 종료 | 선택적 |
| `1008` | Policy Violation | 인증 실패 (토큰 누락·만료·무효) | :x: 토큰 갱신 후 재시도 |
| `1011` | Internal Error | 서버 내부 오류 | :white_check_mark: 지수 백오프 후 재시도 |
| `4000` | Reconnect | 소켓 수명(24시간) 만료 (`cloudflare`) | :white_check_mark: 바로 재연결 |
| `4029` | Rate Limit Exceeded | 연결 Rate Limit 초과 (`inprocess`) | :white_check_mark: 지수 백오프 후 재시도 |

!!! tip "프론트엔드 구현 가이드"
    - **`1008`**: 재연결하지 마세요. 토큰을 갱신한 후 재연결하세요.
    - **`4000`**: 바로 재연결하세요.
    - **그 외**: 지수 백오프와 지터를 두고 재연결하세요.
    - 재연결에 성공하면 REST로 다시 맞추세요.

## 상세 가이드

- [타이머 가이드](../guides/timer.ko.md) — REST 명령과 데이터 모델
- [실시간 전달](../development/realtime-adapter.ko.md) — 두 모드, 계약, 받는 사람 규칙
