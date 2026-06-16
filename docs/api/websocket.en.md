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

!!! warning "Warning"
    **Security**: Authentication via query parameter is NOT supported due to log exposure risks.

Authentication is done via `Sec-WebSocket-Protocol` header:

```
Sec-WebSocket-Protocol: authorization.bearer.<jwt_token>
```

The server will echo back the same subprotocol in the response to complete the WebSocket handshake.

!!! warning "Warning"
    **Important**: For WebSocket connections to work, you must add WebSocket URLs to `CORS_ALLOWED_ORIGINS`:
    - Development: `ws://localhost:2614,ws://127.0.0.1:2614`
    - Production: `wss://your-domain.com`

## Message Types

### Client → Server

| Message Type | Description | Payload |
|--------------|-------------|---------|
| `timer.create` | Create and start a new timer | `{ allocated_duration, schedule_id?, todo_id?, title?, description?, tag_ids? }` |
| `timer.pause` | Pause a running timer | `{ timer_id }` |
| `timer.resume` | Resume a paused timer | `{ timer_id }` |
| `timer.stop` | Stop and complete a timer | `{ timer_id }` |
| `timer.sync` | Sync timers from server | `{ timer_id?, scope? }` |

### Server → Client

| Message Type | Description | Payload |
|--------------|-------------|---------|
| `connected` | Connection accepted | `{ user_id, message }` |
| `timer.created` | Timer created | `{ timer: TimerDTO, action: "start" }` |
| `timer.updated` | Timer updated | `{ timer: TimerDTO \| null, action: "pause" \| "resume" \| "stop" \| "sync" }` |
| `timer.sync_result` | Timer list synced | `{ timers: TimerDTO[], count: number }` |
| `timer.friend_activity` | Friend timer activity notification | `{ friend_id, display_name?, action, timer_id, timer_title? }` |
| `error` | Error occurred | `{ code: string, message: string }` |

## Message Format

All messages are JSON:

```json
{
  "type": "timer.create",
  "payload": {
    "schedule_id": "uuid-here",
    "allocated_duration": 3600
  }
}
```

!!! note "Field names"
    WebSocket payload fields use the same `snake_case` names as the server DTOs. Examples: `allocated_duration`, `timer_id`, `schedule_id`.

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
      schedule_id: 'schedule-uuid',
      allocated_duration: 3600 // 1 hour in seconds
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
    schedule_id: 'schedule-uuid',
    allocated_duration: 3600 // seconds
  }
}));
```

### Pause Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.pause',
  payload: {
    timer_id: 'timer-uuid'
  }
}));
```

### Resume Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.resume',
  payload: {
    timer_id: 'timer-uuid'
  }
}));
```

### Stop Timer

```javascript
ws.send(JSON.stringify({
  type: 'timer.stop',
  payload: {
    timer_id: 'timer-uuid'
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

When `scope` is omitted, the server treats it as `"active"`, so `payload: {}` and `payload: { scope: 'active' }` are equivalent.

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

- `INVALID_MESSAGE` - Invalid JSON or message schema
- `UNKNOWN_TYPE` - Unknown message type
- `CREATE_FAILED` - Timer creation failed
- `PAUSE_FAILED` - Timer pause failed
- `RESUME_FAILED` - Timer resume failed
- `STOP_FAILED` - Timer stop failed
- `SYNC_FAILED` - Timer sync failed
- `HANDLER_ERROR` - Unexpected error while handling a message
- `RATE_LIMIT_EXCEEDED` - Rate limit exceeded

Authentication failures close the WebSocket with close code `1008` instead of returning an error message.

## Rate Limiting

WebSocket connections and messages are subject to rate limiting:

- **Connection**: 10 connections per 60 seconds
- **Messages**: 120 messages per 60 seconds

> 📖 **Detailed Guide**: [Rate Limiting Guide](../development/rate-limit.md)

## Close Codes

List of close codes returned by the server when terminating a WebSocket connection. Clients should use these codes to determine whether to reconnect.

| Close Code | Name | Description | Reconnect |
|-----------|------|-------------|-----------|
| `1000` | Normal Closure | Graceful shutdown | Optional |
| `1008` | Policy Violation | Authentication failure (missing token, expired token, invalid token, missing `sub` claim) | :x: Do NOT reconnect — refresh token first |
| `1011` | Internal Error | Server internal error | :white_check_mark: Retry with exponential backoff |
| `4029` | Rate Limit Exceeded | Connection rate limit exceeded (default: 10 per 60s) | :white_check_mark: Retry with exponential backoff |

!!! tip "Frontend Implementation Guide"
    - **`1008` (Auth failure)**: Do NOT reconnect. Retrying with an expired token causes unnecessary server load. Refresh the token before reconnecting.
    - **`4029` (Rate limit)**: Reconnect with exponential backoff.
    - **`1011` (Server error)**: Reconnect with exponential backoff.
    - **`1000` (Normal closure)**: Server intentionally closed the connection. Reconnect if needed.

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
      if (event.code === 1008) {
        // Auth failure - do NOT reconnect, refresh token first
        console.error('Authentication failed:', event.reason);
        this.onAuthFailure?.(event.reason);
        return;
      }

      if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

      if (event.code === 4029 || event.code === 1011) {
        // Rate limit or server error - exponential backoff
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
        setTimeout(() => this.connect(), delay);
      } else {
        // Other disconnect - reconnect
        setTimeout(() => this.connect(), 1000);
      }
      this.reconnectAttempts++;
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0; // Reset on successful connection
    };
  }
}
```

## Detailed Guide

For comprehensive WebSocket API documentation, see the [Timer Guide](../guides/timer.md).
