# REST API Reference

전체 API 스펙을 Redoc 형식으로 확인할 수 있습니다.

!!swagger openapi.json!!

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

> ⚠️ **Note**: Timer creation and control (create, pause, resume, stop) are handled via WebSocket API.

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
