# WebSocket API

Timer creation and control operations are handled via WebSocket for real-time synchronization across devices and shared users.

## Connection

### Endpoint

```
Development: ws://localhost:2614/v1/ws/timers
Production:  wss://your-domain.com/v1/ws/timers
```

### Test Links

**WebSocket Playground** (development only):

- **WebSocket Playground**: [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground)

Open the link above in your browser and enter your JWT to test the Timer WebSocket API. (Enabled only in development, like Swagger UI.)

For direct connection:

- **Connection URL**: `ws://localhost:2614/v1/ws/timers`
- **With timezone**: `ws://localhost:2614/v1/ws/timers?timezone=Asia/Seoul`

You can also use [Postman](https://www.postman.com/), [wscat](https://github.com/websockets/wscat), etc., with Bearer token in the `Sec-WebSocket-Protocol` header. See [Example Usage](#example-usage) below.

Optional query parameter:
- `timezone`: Timezone for response timestamps (e.g., `Asia/Seoul`, `+09:00`)

### Authentication

> ⚠️ **Security**: Authentication via query parameter is NOT supported due to log exposure risks.

Authentication is done via `Sec-WebSocket-Protocol` header:

```
Sec-WebSocket-Protocol: authorization.bearer.<jwt_token>
```

The server will echo back the same subprotocol in the response to complete the WebSocket handshake.

> ⚠️ **Important**: For WebSocket connections to work, you must add WebSocket URLs to `CORS_ALLOWED_ORIGINS`:
> - Development: `ws://localhost:2614,ws://127.0.0.1:2614`
> - Production: `wss://your-domain.com`

## Message Types

### Client → Server

| Message Type | Description | Payload |
|--------------|-------------|---------|
| `timer.create` | Create and start a new timer | `{ scheduleId?, todoId?, allocatedDuration }` |
| `timer.pause` | Pause a running timer | `{ timerId }` |
| `timer.resume` | Resume a paused timer | `{ timerId }` |
| `timer.stop` | Stop and complete a timer | `{ timerId }` |
| `timer.sync` | Sync active timers from server | `{}` |

### Server → Client

| Message Type | Description | Payload |
|--------------|-------------|---------|
| `timer.created` | Timer created | `{ timer: TimerDTO }` |
| `timer.updated` | Timer updated | `{ timer: TimerDTO }` |
| `timer.completed` | Timer completed | `{ timer: TimerDTO }` |
| `timer.synced` | Active timers synced | `{ timers: TimerDTO[] }` |
| `error` | Error occurred | `{ code: string, message: string }` |

## Message Format

All messages are JSON:

```json
{
  "type": "timer.create",
  "payload": {
    "scheduleId": "uuid-here",
    "allocatedDuration": 3600
  }
}
```

## Example Usage

### JavaScript/TypeScript

```javascript
// Authentication via Sec-WebSocket-Protocol header
const accessToken = 'your-jwt-token';
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers',
  [`authorization.bearer.${accessToken}`]  // Subprotocol for auth
);

ws.onopen = () => {
  console.log('WebSocket connected');
  
  // Create a timer
  ws.send(JSON.stringify({
    type: 'timer.create',
    payload: {
      scheduleId: 'schedule-uuid',
      allocatedDuration: 3600 // 1 hour in seconds
    }
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.type) {
    case 'timer.created':
      console.log('Timer created:', message.payload.timer);
      break;
    case 'timer.updated':
      console.log('Timer updated:', message.payload.timer);
      break;
    case 'error':
      console.error('Error:', message.payload.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket disconnected');
};
```

### With Timezone

```javascript
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers?timezone=Asia/Seoul',
  [`authorization.bearer.${accessToken}`]
);
```

### Create Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.create',
  payload: {
    scheduleId: 'schedule-uuid',
    allocatedDuration: 3600 // seconds
  }
}));
```

### Pause Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.pause',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### Resume Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.resume',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### Stop Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.stop',
  payload: {
    timerId: 'timer-uuid'
  }
}));
```

### Sync Active Timers

```javascript
ws.send(JSON.stringify({
  type: 'timer.sync',
  payload: {}
}));
```

## Error Handling

Errors are returned as messages:

```json
{
  "type": "error",
  "payload": {
    "code": "TIMER_NOT_FOUND",
    "message": "Timer not found"
  }
}
```

Common error codes:

- `TIMER_NOT_FOUND` - Timer does not exist
- `TIMER_ALREADY_COMPLETED` - Timer is already completed
- `TIMER_NOT_RUNNING` - Timer is not in running state
- `RATE_LIMIT_EXCEEDED` - Rate limit exceeded
- `UNAUTHORIZED` - Authentication failed

## Rate Limiting

WebSocket connections and messages are subject to rate limiting:

- **Connection**: 10 connections per 60 seconds
- **Messages**: 120 messages per 60 seconds

> 📖 **Detailed Guide**: [Rate Limiting Guide](../development/rate-limit.md)

## Reconnection

It's recommended to implement automatic reconnection:

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
    // Use Sec-WebSocket-Protocol for authentication (NOT query parameter)
    this.ws = new WebSocket(
      this.url,
      [`authorization.bearer.${this.token}`]
    );

    this.ws.onclose = (event) => {
      if (event.code === 4029) {
        // Rate limit - exponential backoff
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
        setTimeout(() => this.connect(), delay);
        this.reconnectAttempts++;
      } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
        // Normal disconnect - reconnect
        setTimeout(() => this.connect(), 1000);
        this.reconnectAttempts++;
      }
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0; // Reset on successful connection
    };
  }
}
```

## Detailed Guide

For comprehensive WebSocket API documentation, see the [Timer Guide](../guides/timer.ko.md).
