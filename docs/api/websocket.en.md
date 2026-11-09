# WebSocket API

A **receive-only** socket for real-time timer changes. Timer commands (create, pause, resume, stop, update, delete) go through the [REST API](../guides/timer.md); once committed, each change is delivered over this socket to the owner's other devices and to friends who may see the timer.

For the deployment structure and the full contract, see [Realtime Delivery](../development/realtime-adapter.md) (Korean).

## Connection

### Endpoint

The address depends on the delivery mode (`REALTIME_BACKEND`). The message format is the same.

| Mode | Address |
|------|---------|
| `inprocess` (default) | `ws://localhost:2614/v1/ws/timers`, `wss://your-domain.com/v1/ws/timers` |
| `cloudflare` (separate Worker) | `wss://your-domain.com/realtime/ws` |

### Test Links

**WebSocket Playground** (development only, `inprocess`):

- **WebSocket Playground**: [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground)

Enter your JWT and connect to see incoming messages and send `ping`. Call the REST timer commands (e.g. from Swagger UI) and their events show up there.

You can also connect directly with [wscat](https://github.com/websockets/wscat) or similar, putting the token in the `Sec-WebSocket-Protocol` header.

### Authentication

!!! warning "Warning"
    **Security**: Query parameter authentication is not supported due to log exposure risks.

Authentication is performed via the `Sec-WebSocket-Protocol` header:

```
Sec-WebSocket-Protocol: authorization.bearer.<jwt_token>
```

The server echoes the same subprotocol in its response to complete the handshake. The JWT is verified only when connecting.

!!! warning "Warning"
    **Important**: You must add WebSocket URLs to `CORS_ALLOWED_ORIGINS` for WebSocket connections to work:
    - Development: `ws://localhost:2614,ws://127.0.0.1:2614`
    - Production: `wss://your-domain.com`

## Messages

### Client → Server

| Message | Description |
|---------|-------------|
| `ping` (string) | Keep-alive. The server replies with `pong` |

Any other message is ignored.

### Server → Client

Every message uses the same envelope:

```json
{
  "id": "6f1c0c1e-8a53-4d6e-9d0a-2b1f5f0c9a11",
  "type": "timer.updated",
  "from_user": "<actor sub>",
  "timestamp": "2026-11-06T10:30:00+0000",
  "payload": {
    "action": "pause",
    "actor_name": "Jane Doe",
    "timer": { "id": "…", "status": "PAUSED", "elapsed_time": 1800, "…": "…" }
  }
}
```

| `type` | `payload` |
|--------|-----------|
| `connected` | `{}` — once, right after connecting |
| `timer.created` | `{ action: "start", actor_name, timer }` |
| `timer.updated` | `{ action: "pause" \| "resume" \| "stop" \| "cancel" \| "update" \| "expire", actor_name, timer }` |
| `timer.deleted` | `{ action: "delete", actor_name, timer: null, timer_id }` |

- `id`: message ID. Drop a message you have already handled.
- `from_user`: `sub` of the user who made the change (`null` for `connected`). If it is not your `sub`, it is a friend's activity.
- `expire`: a command (`pause`, `stop`, `cancel`, a successful `PATCH`) or a change on the Todo or schedule side (applying a Todo status, deleting with `unlink`) found a RUNNING timer past its allocated duration and stored it as PAUSED. Nothing is sent at the expiry instant itself, nor for a `resume` that returns 400 or a `PATCH` that returns 422. A `stop`, `cancel` or `update` event for the same request may follow (rules: the "만료" section of the [timer guide](../guides/timer.md)).
- `timer`: the committed timer. All times are UTC, in the same format as REST responses (`timezone=UTC`). `elapsed_time` is the stored total (for RUNNING timers, add `now - started_at` when displaying).

!!! note "Field Names"
    Payload fields use `snake_case`, the same as the server DTOs. Examples: `elapsed_time`, `timer_id`, `actor_name`.

## Resynchronization

The socket does not resend messages from before the connection or while it was down. Clients should:

1. Reload timers over REST right after every connect and reconnect (`timezone=UTC`).
2. Drop duplicates by `id`.
3. Drop an event whose `timer.updated_at` is older than the one you hold; apply it when equal or newer. Use the same rule for REST responses.
4. Drop earlier events for a timer you received `timer.deleted` for.

## Example Usage

### JavaScript/TypeScript

```javascript
const ws = new WebSocket(
  'ws://localhost:2614/v1/ws/timers',
  [`authorization.bearer.${accessToken}`]  // subprotocol for authentication
);

ws.onopen = () => {
  resyncTimersFromRest();  // reload over REST
};

ws.onmessage = (event) => {
  if (event.data === 'pong') return;
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'timer.created':
    case 'timer.updated':
      applyTimer(message);  // check id and updated_at before applying
      break;
    case 'timer.deleted':
      removeTimer(message.payload.timer_id);
      break;
  }
};

// keep-alive
setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 45000);
```

## Rate Limiting

The `inprocess` socket limits connections (default: 10 per 60 seconds, `WS_CONNECT_MAX`/`WS_CONNECT_WINDOW`). Beyond that, the server closes with `4029`.

> 📖 **Detailed Guide**: [Rate Limiting Guide](../development/rate-limit.md)

## Close Codes

| Close Code | Name | Description | Reconnect |
|-----------|------|-------------|-----------|
| `1000` | Normal Closure | Normal closure | Optional |
| `1008` | Policy Violation | Authentication failed (missing, expired, or invalid token) | :x: Retry after refreshing the token |
| `1011` | Internal Error | Server error | :white_check_mark: Retry with exponential backoff |
| `4000` | Reconnect | Socket lifetime (24 hours) expired (`cloudflare`) | :white_check_mark: Reconnect immediately |
| `4029` | Rate Limit Exceeded | Connection rate limit exceeded (`inprocess`) | :white_check_mark: Retry with exponential backoff |

!!! tip "Frontend Implementation Guide"
    - **`1008`**: Do not reconnect until you have refreshed the token.
    - **`4000`**: Reconnect right away.
    - **Others**: Reconnect with exponential backoff and jitter.
    - After reconnecting, reload over REST.

## Detailed Guides

- [Timer Guide](../guides/timer.md) — REST commands and the data model
- [Realtime Delivery](../development/realtime-adapter.md) — modes, contract, and recipient rules (Korean)
