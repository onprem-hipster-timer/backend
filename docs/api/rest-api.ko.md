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

!!! warning "주의"
    **참고**: 타이머 생성 및 제어(생성, 일시정지, 재개, 중지)는 WebSocket API를 통해 처리됩니다.

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

### 접근권한 (Visibility)

```http
PUT    /v1/visibility/{resource_type}/{resource_id}   # 접근권한 설정/변경
GET    /v1/visibility/{resource_type}/{resource_id}   # 접근권한 조회
DELETE /v1/visibility/{resource_type}/{resource_id}   # 접근권한 삭제 (PRIVATE 복귀)
```

!!! info "`resource_type`"
    `schedule`, `timer`, `todo`, `meeting` 중 하나를 사용합니다.

### 친구 (Friends)

```http
GET    /v1/friends                       # 친구 목록 (display_name·avatar_url 포함)
GET    /v1/friends/ids                    # 친구 ID 목록
GET    /v1/friends/check/{user_id}        # 친구 여부 확인
POST   /v1/friends/requests               # 친구 요청 (email 또는 friend_code)
GET    /v1/friends/requests/received      # 받은 요청 (requester_display_name 포함)
GET    /v1/friends/requests/sent          # 보낸 요청
POST   /v1/friends/requests/{id}/accept   # 요청 수락
POST   /v1/friends/requests/{id}/reject   # 요청 거절
DELETE /v1/friends/requests/{id}          # 보낸 요청 취소
DELETE /v1/friends/{id}                   # 친구 삭제
POST   /v1/friends/block/{user_id}        # 차단
DELETE /v1/friends/block/{user_id}        # 차단 해제
```

!!! info "친구 요청 (`POST /v1/friends/requests`)"
    바디는 `{ "email": "..." }` 또는 `{ "friend_code": "..." }` 중 **정확히 하나**를 보냅니다 — **이메일**(저장된 검증 이메일과 normalize 후 매칭, 계정 열거 방지를 위해 항상 `202` 균일 응답) 또는 **친구코드**(무작위 공유 코드 직접 매칭, 미존재 시 `404`). 둘 다 보내거나 둘 다 비우거나 `null`을 보내면 `422`. 사용자 검색/디렉터리는 제공하지 않습니다. 친구코드는 `GET /v1/users/me`로 확인합니다.

### 사용자 (Users)

```http
GET    /v1/users/me                       # 본인 표시정보 + 친구코드(공유용)
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
