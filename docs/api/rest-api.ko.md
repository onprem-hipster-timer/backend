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
GET    /v1/todos                 # 투두 목록 조회
POST   /v1/todos                 # 투두 생성
GET    /v1/todos/{id}            # 특정 투두 조회
PATCH  /v1/todos/{id}            # 투두 수정 (해야 할 일 목록 이동 포함)
DELETE /v1/todos/{id}            # 투두 삭제
GET    /v1/todos/stats           # 통계 조회
GET    /v1/todos/groups          # 해야 할 일 목록 전체 조회 (기본 목록이 없으면 생성)
POST   /v1/todos/groups          # 해야 할 일 목록 생성
GET    /v1/todos/groups/{id}     # 특정 해야 할 일 목록 조회
PATCH  /v1/todos/groups/{id}     # 해야 할 일 목록 수정
DELETE /v1/todos/groups/{id}     # 해야 할 일 목록 삭제 (투두는 기본 목록으로 이동)
```

### 태그 (Tags)

```http
GET    /v1/tags/groups           # 태그 그룹 목록 조회 (태그 포함)
POST   /v1/tags/groups           # 태그 그룹 생성
GET    /v1/tags/groups/{id}      # 특정 태그 그룹 조회
PATCH  /v1/tags/groups/{id}      # 태그 그룹 수정
DELETE /v1/tags/groups/{id}      # 태그 그룹 삭제 (그룹의 태그도 삭제)
GET    /v1/tags                  # 태그 목록 조회
POST   /v1/tags                  # 태그 생성
DELETE /v1/tags/{id}             # 태그 삭제
```

### 미팅 (Meetings)

```http
POST   /v1/meetings                                     # 미팅 생성
GET    /v1/meetings                                     # 내가 만든 미팅 목록
GET    /v1/meetings/{id}                                # 미팅 조회 (public이면 로그인 없이)
PATCH  /v1/meetings/{id}                                # 미팅 수정 (생성자)
DELETE /v1/meetings/{id}                                # 미팅 삭제 (생성자). 그 미팅의 게스트도 폐기
POST   /v1/meetings/{id}/participate                    # 참여 등록 (회원, 그 미팅의 게스트)
DELETE /v1/meetings/{id}/participants/{participant_id}  # 참여자 빼기 (생성자). 게스트 참여자는 그 게스트를 폐기
PUT    /v1/meetings/{id}/availability                   # 자기 참여자의 가능 시간 설정
GET    /v1/meetings/{id}/availability                   # 참여자별 가능 시간
GET    /v1/meetings/{id}/result                         # 칸마다 가능한 인원 수 (public이면 로그인 없이)
```

자세한 내용은 [미팅 가이드](../guides/meeting.ko.md)를 봅니다.

### 접근권한 (Visibility)

```http
PUT    /v1/visibility/{resource_type}/{resource_id}   # 접근권한 설정/변경
GET    /v1/visibility/{resource_type}/{resource_id}   # 접근권한 조회
DELETE /v1/visibility/{resource_type}/{resource_id}   # 접근권한 삭제 (PRIVATE 복귀)
```

!!! info "`resource_type`"
    `schedule`, `timer`, `todo`, `meeting` 중 하나를 사용합니다.

!!! info "접근할 수 없는 리소스"
    일정·타이머·투두·미팅 경로는 접근할 수 없는 리소스에 그 리소스가 없을 때와 같은 `404`를 돌려줍니다. 접근권한 경로는 리소스가 없거나 소유자가 아니면 `404`입니다. 자세한 내용은 [공개 범위 가이드](../guides/visibility.ko.md#접근-제어-규칙)를 봅니다.

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
    바디는 `{ "email": "..." }` 또는 `{ "friend_code": "..." }` 중 **정확히 하나**를 보냅니다 — **이메일**(형식 검증, 저장된 검증 이메일과 매칭, 계정 열거 방지를 위해 항상 `202` 균일 응답) 또는 **친구코드**(무작위 공유 코드 직접 매칭, 미존재 시 `404`). 둘 다 보내거나 둘 다 비우거나 `null`을 보내면 `422`. 사용자 검색/디렉터리는 제공하지 않습니다. 친구코드는 `GET /v1/users/me`로 확인합니다.

### 사용자 (Users)

```http
GET    /v1/users/me                       # 본인 표시정보 + 친구코드(공유용)
POST   /v1/users/me/deletion              # 회원 탈퇴 신청 (휴면)
DELETE /v1/users/me/deletion              # 회원 탈퇴 신청 취소
```

!!! info "회원 탈퇴"
    신청하면 계정이 휴면이 되고 모든 기기의 로그인 세션이 끊깁니다. 휴면 계정의 데이터는 다른 사용자에게 보이지 않고, 위 세 경로 외의 인증 요청은 `423`(`message: "account_deletion_pending"`)입니다. 다시 로그인해 취소할 수 있으며, 응답의 `deletion_scheduled_at`(신청 + `ACCOUNT_DELETION_GRACE_DAYS`일)이 지나면 다음 파기 실행이 모든 데이터와 로그인 계정을 지웁니다. 파기한 계정의 토큰은 `401`(`message: "account_deleted"`)입니다.

### 게스트 (Guests)

`GUEST_ENABLED=true`일 때만 응답합니다(꺼져 있으면 404).

```http
POST   /v1/guests/lookup                  # 리소스에서 그 이름의 게스트 로그인 식별자(handle) 찾기 (인증 없음). 현재 약관 버전도 반환
POST   /v1/guests                         # 게스트 생성 (인증 없음, 약관 동의 consent 필요). handle 반환
DELETE /v1/guests/me                      # 게스트가 자기를 폐기 (게스트 JWT)
PUT    /v1/guests/me/consent              # 게스트의 약관 동의 기록 (게스트 JWT)
```

게스트는 `handle`과 비밀번호로 회원처럼 `/auth`에서 로그인하고 JWT를 받습니다. 이름 찾기·생성·자기 삭제와 게스트의 로그인 제출, 게스트 세션의 설정 제출에는 Turnstile 토큰(`X-Turnstile-Token` 헤더)이 필요하고, 토큰은 한 번만 쓸 수 있습니다. 약관 동의 기록은 토큰을 받지 않습니다. `CONSENT_ENFORCED`면 현재 약관 버전에 동의하지 않은 게스트는 동의 기록과 자기 삭제 밖의 게스트 경로가 `428`(`message: "consent_required"`)입니다. 게스트 토큰은 위 경로와 게스트를 받는 리소스 경로(미팅의 조회·참여·가능 시간·결과, [미팅 가이드](../guides/meeting.ko.md#접근-권한)) 외의 모든 인증 경로에서 `403`입니다. 자세한 내용은 [게스트 가이드](../guides/guest.ko.md)를 봅니다.

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
