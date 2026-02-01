# API Overview

Hipster Timer Backend provides three types of APIs:

1. **REST API** - Traditional HTTP endpoints
2. **GraphQL API** - Flexible query language
3. **WebSocket API** - Real-time communication

## Base URL

All APIs are served under the `/v1` prefix:

- **Development**: `http://localhost:2614/v1`
- **Production**: `https://your-domain.com/v1`

## Authentication

All API endpoints (except health check) require authentication via OIDC Bearer token:

```
Authorization: Bearer <access_token>
```

> 📖 **Detailed Guide**: [Authentication Guide](../guides/auth.ko.md)

## API Types

### REST API

Traditional RESTful endpoints for CRUD operations:

- **Schedules**: `/v1/schedules`
- **Timers**: `/v1/timers`
- **Todos**: `/v1/todos`
- **Tags**: `/v1/tags`
- **Holidays**: `/v1/holidays`

> 📖 **Detailed Guide**: [REST API Reference](rest-api.en.md)

### GraphQL API

Flexible query language for efficient data fetching:

- **Endpoint**: `/v1/graphql`
- **Playground**: Available at `/v1/graphql` (development only)

> 📖 **Detailed Guide**: [GraphQL Guide](graphql.en.md)

### WebSocket API

Real-time communication for timer control:

- **Endpoint**: `/v1/ws/timers`
- **Protocol**: WebSocket with JSON messages

> 📖 **Detailed Guide**: [WebSocket Guide](websocket.en.md)

## Rate Limiting

All APIs are subject to rate limiting:

- **Default**: 60 requests per 60 seconds per user
- **Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

> 📖 **Detailed Guide**: [Rate Limiting Guide](../development/rate-limit.md)

## Error Handling

All APIs return consistent error responses:

```json
{
  "detail": "Error message here"
}
```

Common HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Too Many Requests
- `500` - Internal Server Error

## Data Formats

- **Request**: JSON (`Content-Type: application/json`)
- **Response**: JSON (`Content-Type: application/json`)
- **Dates**: ISO 8601 format (`2024-01-15T10:00:00Z`)
- **UUIDs**: Standard UUID v4 format

## Interactive Documentation (Test Links)

When running the local dev server, you can test the API at these URLs:

| Item | Test Link (Development) |
|------|--------------------------|
| **Swagger UI** | [http://localhost:2614/docs](http://localhost:2614/docs) |
| **ReDoc** | [http://localhost:2614/redoc](http://localhost:2614/redoc) |
| **GraphQL Playground** | [http://localhost:2614/v1/graphql](http://localhost:2614/v1/graphql) |
| **WebSocket Playground** | [http://localhost:2614/ws-playground](http://localhost:2614/ws-playground) |
| **WebSocket (Timer endpoint)** | `ws://localhost:2614/v1/ws/timers` |

!!! warning "Warning"
    These links are only available in development (`DOCS_ENABLED=true`). WebSocket Playground is a built-in page where you can test the Timer WebSocket API in the browser after entering your JWT.
