# WebSocket API

타이머 생성 및 제어 작업은 기기 간, 공유 사용자 간 실시간 동기화를 위해 WebSocket을 통해 처리됩니다.

## 연결

### 엔드포인트

```
개발: ws://localhost:2614/v1/ws/timers
프로덕션: wss://your-domain.com/v1/ws/timers
```

### 테스트 링크

**자체 WebSocket Playground** (개발 모드 전용):

- **WebSocket Playground**: [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground)

브라우저에서 위 링크로 접속한 뒤 JWT를 입력하면 타이머 WebSocket API를 바로 테스트할 수 있습니다. (Swagger UI처럼 개발 환경에서만 활성화됩니다.)

직접 연결할 때 사용할 주소:

- **연결 URL**: `ws://localhost:2614/v1/ws/timers`
- **쿼리 예시 (타임존)**: `ws://localhost:2614/v1/ws/timers?timezone=Asia/Seoul`

Playground 외에 [Postman](https://www.postman.com/), [wscat](https://github.com/websockets/wscat) 등으로 `Sec-WebSocket-Protocol` 헤더에 Bearer 토큰을 넣어 연결할 수도 있습니다. 동작 예제는 아래 [Example Usage](#example-usage)를 참고하세요.

선택적 쿼리 매개변수:
- `timezone`: 응답 타임스탬프의 타임존 (예: `Asia/Seoul`, `+09:00`)

### 인증

> ⚠️ **보안**: 로그 노출 위험으로 인해 쿼리 매개변수를 통한 인증은 지원하지 않습니다.

인증은 `Sec-WebSocket-Protocol` 헤더를 통해 수행됩니다:

```
Sec-WebSocket-Protocol: authorization.bearer.<jwt_token>
```

서버는 WebSocket 핸드셰이크를 완료하기 위해 응답에 동일한 서브프로토콜을 반환합니다.

> ⚠️ **중요**: WebSocket 연결이 작동하려면 `CORS_ALLOWED_ORIGINS`에 WebSocket URL을 추가해야 합니다:
> - 개발: `ws://localhost:2614,ws://127.0.0.1:2614`
> - 프로덕션: `wss://your-domain.com`

## 메시지 유형

### 클라이언트 → 서버

| 메시지 유형 | 설명 | 페이로드 |
|-------------|------|----------|
| `timer.create` | 새 타이머 생성 및 시작 | `{ scheduleId?, todoId?, allocatedDuration }` |
| `timer.pause` | 실행 중인 타이머 일시정지 | `{ timerId }` |
| `timer.resume` | 일시정지된 타이머 재개 | `{ timerId }` |
| `timer.stop` | 타이머 중지 및 완료 | `{ timerId }` |
| `timer.sync` | 서버에서 활성 타이머 동기화 | `{}` |

### 서버 → 클라이언트

| 메시지 유형 | 설명 | 페이로드 |
|-------------|------|----------|
| `timer.created` | 타이머 생성됨 | `{ timer: TimerDTO }` |
| `timer.updated` | 타이머 수정됨 | `{ timer: TimerDTO }` |
| `timer.completed` | 타이머 완료됨 | `{ timer: TimerDTO }` |
| `timer.synced` | 활성 타이머 동기화됨 | `{ timers: TimerDTO[] }` |
| `error` | 오류 발생 | `{ code: string, message: string }` |

## 메시지 형식

모든 메시지는 JSON 형식입니다:

```json
{
  "type": "timer.create",
  "payload": {
    "scheduleId": "uuid-here",
    "allocatedDuration": 3600
  }
}
```

## 사용 예시

### JavaScript/TypeScript

```javascript
// Sec-WebSocket-Protocol 헤더를 통한 인증
const accessToken = 'your-jwt-token';
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers',
  [`authorization.bearer.${accessToken}`]  // 인증용 서브프로토콜
);

ws.onopen = () => {
  console.log('WebSocket 연결됨');
  
  // 타이머 생성
  ws.send(JSON.stringify({
    type: 'timer.create',
    payload: {
      scheduleId: 'schedule-uuid',
      allocatedDuration: 3600 // 1시간(초)
    }
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.type) {
    case 'timer.created':
      console.log('타이머 생성됨:', message.payload.timer);
      break;
    case 'timer.updated':
      console.log('타이머 수정됨:', message.payload.timer);
      break;
    case 'error':
      console.error('오류:', message.payload.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket 오류:', error);
};

ws.onclose = () => {
  console.log('WebSocket 연결 해제됨');
};
```

### 타임존 지정

```javascript
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers?timezone=Asia/Seoul',
  [`authorization.bearer.${accessToken}`]
);
```

### 타이머 생성

```javascript
ws.send(JSON.stringify({
  type: 'timer.create',
  payload: {
    scheduleId: 'schedule-uuid',
    allocatedDuration: 3600 // 초
  }
}));
```

### 타이머 일시정지

```javascript
ws.send(JSON.stringify({
  type: 'timer.pause',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### 타이머 재개

```javascript
ws.send(JSON.stringify({
  type: 'timer.resume',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### 타이머 중지

```javascript
ws.send(JSON.stringify({
  type: 'timer.stop',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### 활성 타이머 동기화

```javascript
ws.send(JSON.stringify({
  type: 'timer.sync',
  payload: {}
}));
```

## 에러 처리

에러는 메시지로 반환됩니다:

```json
{
  "type": "error",
  "payload": {
    "code": "TIMER_NOT_FOUND",
    "message": "타이머를 찾을 수 없습니다"
  }
}
```

일반적인 에러 코드:

- `TIMER_NOT_FOUND` - 타이머가 존재하지 않음
- `TIMER_ALREADY_COMPLETED` - 타이머가 이미 완료됨
- `TIMER_NOT_RUNNING` - 타이머가 실행 중이 아님
- `RATE_LIMIT_EXCEEDED` - 요청 한도 초과
- `UNAUTHORIZED` - 인증 실패

## Rate Limiting

WebSocket 연결과 메시지는 Rate Limiting이 적용됩니다:

- **연결**: 60초당 10회 연결
- **메시지**: 60초당 120개 메시지

> 📖 **상세 가이드**: [Rate Limiting 가이드](../development/rate-limit.ko.md)

## 재연결

자동 재연결 구현을 권장합니다:

```javascript
class TimerWebSocket {
  constructor(url, token) {
    this.url = url;
    this.token = token;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.connect();
  }

  connect() {
    // 인증 시 Sec-WebSocket-Protocol 사용 (쿼리 매개변수 아님)
    this.ws = new WebSocket(
      this.url,
      [`authorization.bearer.${this.token}`]
    );

    this.ws.onclose = (event) => {
      if (event.code === 4029) {
        // Rate limit - 지수 백오프
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
        setTimeout(() => this.connect(), delay);
        this.reconnectAttempts++;
      } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
        // 정상 연결 해제 - 재연결
        setTimeout(() => this.connect(), 1000);
        this.reconnectAttempts++;
      }
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0; // 성공적 연결 시 리셋
    };
  }
}
```

## 상세 가이드

전체 WebSocket API 문서는 [타이머 가이드](../guides/timer.ko.md)를 참조하세요.
