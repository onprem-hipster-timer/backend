# REST API Reference

View the complete API spec in Swagger UI format.

<swagger-ui src="openapi.json"/>

## 주요 엔드포인트

### Schedules

```http
GET    /v1/schedules                    # Get schedules by date range
POST   /v1/schedules                    # Create new schedule
GET    /v1/schedules/{id}               # Get specific schedule
PATCH  /v1/schedules/{id}               # Update schedule
DELETE /v1/schedules/{id}               # Delete schedule
GET    /v1/schedules/{id}/timers        # Get timers for schedule
GET    /v1/schedules/{id}/timers/active # Get active timer
```

### Timers

```http
GET    /v1/timers/{id}           # Get timer
PATCH  /v1/timers/{id}           # Update timer
DELETE /v1/timers/{id}           # Delete timer
```

!!! warning "Warning"
    **Note**: Timer creation and control (create, pause, resume, stop) are handled via WebSocket API.

### Todos

```http
GET    /v1/todos          # List todos
POST   /v1/todos          # Create todo
GET    /v1/todos/{id}     # Get specific todo
PATCH  /v1/todos/{id}     # Update todo
DELETE /v1/todos/{id}     # Delete todo
GET    /v1/todos/stats    # Get statistics
```

### Tags

```http
GET    /v1/tags/groups           # List tag groups
POST   /v1/tags/groups           # Create tag group
GET    /v1/tags/groups/{id}      # Get specific group
PATCH  /v1/tags/groups/{id}      # Update group
DELETE /v1/tags/groups/{id}      # Delete group
GET    /v1/tags                  # List tags
POST   /v1/tags                  # Create tag
DELETE /v1/tags/{id}             # Delete tag
```

### Visibility

```http
PUT    /v1/visibility/{resource_type}/{resource_id}   # Set/update visibility
GET    /v1/visibility/{resource_type}/{resource_id}   # Get visibility settings
DELETE /v1/visibility/{resource_type}/{resource_id}   # Delete visibility (revert to PRIVATE)
```

!!! info "`resource_type`"
    One of `schedule`, `timer`, `todo`, `meeting`.

### Friends

```http
GET    /v1/friends                       # Friend list (includes display_name, avatar_url)
GET    /v1/friends/ids                    # Friend id list
GET    /v1/friends/check/{user_id}        # Check friendship
POST   /v1/friends/requests               # Friend request (identifier: email or friend code)
GET    /v1/friends/requests/received      # Received requests (includes requester_display_name)
GET    /v1/friends/requests/sent          # Sent requests
POST   /v1/friends/requests/{id}/accept   # Accept request
POST   /v1/friends/requests/{id}/reject   # Reject request
DELETE /v1/friends/requests/{id}          # Cancel sent request
DELETE /v1/friends/{id}                   # Remove friend
POST   /v1/friends/block/{user_id}        # Block user
DELETE /v1/friends/block/{user_id}        # Unblock user
```

!!! info "Friend request (`POST /v1/friends/requests`)"
    The body `{ "identifier": "..." }` is dispatched by whether it contains `@` — an **email** (matched against verified users; always returns a uniform `202` to prevent account enumeration) or a **friend code** (direct match; `404` if unknown). No user search/directory is provided. Get your friend code from `GET /v1/users/me`.

### Users

```http
GET    /v1/users/me                       # Own display info + friend code (for sharing)
```

### Holidays

```http
GET    /v1/holidays              # List holidays
```

## 상세 가이드

각 API에 대한 상세한 사용법은 다음 가이드를 참조하세요:

- [Schedule Guide](../guides/schedule.ko.md)
- [Timer Guide](../guides/timer.ko.md)
- [Todo Guide](../guides/todo.ko.md)
- [Friend Guide](../guides/friend.ko.md)
- [Visibility Guide](../guides/visibility.ko.md)
- [Meeting Guide](../guides/meeting.ko.md)
