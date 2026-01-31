# REST API 레퍼런스

전체 API 스펙을 Swagger UI 형식으로 확인할 수 있습니다.

<swagger-ui src="openapi.json"/>

## 주요 엔드포인트

### 일정 (Schedules)

```http
GET    /v1/schedules                    # 날짜 범위로 일정 조회
POST   /v1/schedules                    # 새 일정 생성
GET    /v1/schedules/{id}               # 특정 일정 조회
PATCH  /v1/schedules/{id}               # 일정 수정
DELETE /v1/schedules/{id}               # 일정 삭제
GET    /v1/schedules/{id}/timers        # 일정의 타이머 조회
GET    /v1/schedules/{id}/timers/active # 활성 타이머 조회
```

### 타이머 (Timers)

```http
GET    /v1/timers/{id}           # 타이머 조회
PATCH  /v1/timers/{id}           # 타이머 수정
DELETE /v1/timers/{id}           # 타이머 삭제
```

> ⚠️ **참고**: 타이머 생성 및 제어(생성, 일시정지, 재개, 중지)는 WebSocket API를 통해 처리됩니다.

### 투두 (Todos)

```http
GET    /v1/todos          # 투두 목록 조회
POST   /v1/todos          # 투두 생성
GET    /v1/todos/{id}     # 특정 투두 조회
PATCH  /v1/todos/{id}     # 투두 수정
DELETE /v1/todos/{id}     # 투두 삭제
GET    /v1/todos/stats    # 통계 조회
```

### 태그 (Tags)

```http
GET    /v1/tags/groups           # 태그 그룹 목록 조회
POST   /v1/tags/groups           # 태그 그룹 생성
GET    /v1/tags/groups/{id}      # 특정 그룹 조회
PATCH  /v1/tags/groups/{id}      # 그룹 수정
DELETE /v1/tags/groups/{id}      # 그룹 삭제
GET    /v1/tags                  # 태그 목록 조회
POST   /v1/tags                  # 태그 생성
DELETE /v1/tags/{id}             # 태그 삭제
```

### 공휴일 (Holidays)

```http
GET    /v1/holidays              # 공휴일 목록 조회
```

## 상세 가이드

각 API에 대한 상세한 사용법은 다음 가이드를 참조하세요:

- [일정 가이드](../guides/schedule.ko.md)
- [타이머 가이드](../guides/timer.ko.md)
- [투두 가이드](../guides/todo.ko.md)
- [친구 가이드](../guides/friend.ko.md)
- [공개 설정 가이드](../guides/visibility.ko.md)
- [미팅 가이드](../guides/meeting.ko.md)
