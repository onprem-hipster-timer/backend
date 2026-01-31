# Friend & Visibility API 가이드 (프론트엔드 개발자용)

> **최종 업데이트**: 2026-01-23

## 개요

Friend & Visibility API는 사용자 간 **친구 관계**와 **리소스 공유**를 관리합니다.

### 핵심 개념

| 개념 | 설명 |
|------|------|
| **Friendship** | 두 사용자 간의 친구 관계. 요청/수락 워크플로우를 통해 생성. |
| **Visibility** | 리소스(Schedule, Timer, Todo)의 공개 범위 설정. |
| **AllowList** | SELECTED_FRIENDS 레벨에서 접근을 허용할 친구 목록. |

### 친구 관계 워크플로우

```mermaid
stateDiagram-v2
    direction LR
    [*] --> PENDING: 친구 요청
    PENDING --> ACCEPTED: 수락
    PENDING --> [*]: 거절 (삭제됨)
    ACCEPTED --> [*]: 친구 삭제
```

### 가시성 레벨

| 레벨 | 설명 |
|------|------|
| `PRIVATE` | 본인만 접근 가능 (기본값) |
| `FRIENDS` | 모든 친구 접근 가능 |
| `SELECTED_FRIENDS` | 선택한 친구만 접근 가능 |
| `PUBLIC` | 모든 사용자 접근 가능 |

---

## 데이터 모델

### FriendshipStatus

```typescript
type FriendshipStatus = 
  | "pending"   // 요청 대기 중
  | "accepted"  // 친구 관계 수립
  | "blocked";  // 차단됨
```

### Friendship

```typescript
interface Friendship {
  id: string;              // UUID
  requester_id: string;    // 요청자 ID
  addressee_id: string;    // 수신자 ID
  status: FriendshipStatus;
  blocked_by?: string;     // 차단한 사용자 ID (blocked 상태일 때)
  created_at: string;      // ISO 8601
  updated_at: string;      // ISO 8601
}
```

### Friend

```typescript
interface Friend {
  user_id: string;         // 친구 사용자 ID
  friendship_id: string;   // 친구 관계 ID
  since: string;           // 친구가 된 시점 (ISO 8601)
}
```

### PendingRequest

```typescript
interface PendingRequest {
  id: string;              // 친구 관계 ID
  requester_id: string;    // 요청자 ID
  addressee_id: string;    // 수신자 ID
  created_at: string;      // ISO 8601
}
```

### VisibilityLevel

```typescript
type VisibilityLevel = 
  | "private"   // 본인만 (기본값)
  | "friends"   // 모든 친구
  | "selected"  // 선택한 친구
  | "public";   // 전체 공개
```

### VisibilitySettings

```typescript
interface VisibilitySettings {
  level: VisibilityLevel;
  allowed_user_ids?: string[];  // SELECTED_FRIENDS 레벨에서만 사용
}
```

---

## Friend REST API

### Base URL

```
/api/v1/friends
```

### 친구 목록

#### GET /friends

현재 사용자의 친구 목록을 조회합니다.

**Response 200:**
```json
[
  {
    "user_id": "friend-user-id",
    "friendship_id": "uuid",
    "since": "2026-01-23T10:00:00Z"
  }
]
```

#### GET /friends/ids

친구 ID 목록만 조회합니다 (효율적인 쿼리).

**Response 200:**
```json
["friend-id-1", "friend-id-2", "friend-id-3"]
```

#### GET /friends/check/{user_id}

특정 사용자와 친구인지 확인합니다.

**Response 200:**
```json
true
```
또는
```json
false
```

---

### 친구 요청

#### POST /friends/requests

친구 요청을 보냅니다.

**Request Body:**
```json
{
  "addressee_id": "target-user-id"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "requester_id": "my-user-id",
  "addressee_id": "target-user-id",
  "status": "pending",
  "created_at": "2026-01-23T10:00:00Z",
  "updated_at": "2026-01-23T10:00:00Z"
}
```

**Error Responses:**
- `400`: 자기 자신에게 요청
- `409`: 이미 친구이거나 대기 중인 요청 존재
- `403`: 차단 관계

#### GET /friends/requests/received

받은 친구 요청 목록을 조회합니다.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "requester_id": "other-user-id",
    "addressee_id": "my-user-id",
    "created_at": "2026-01-23T10:00:00Z"
  }
]
```

#### GET /friends/requests/sent

보낸 친구 요청 목록을 조회합니다.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "requester_id": "my-user-id",
    "addressee_id": "other-user-id",
    "created_at": "2026-01-23T10:00:00Z"
  }
]
```

#### POST /friends/requests/{friendship_id}/accept

친구 요청을 수락합니다.

**Response 200:**
```json
{
  "id": "uuid",
  "requester_id": "other-user-id",
  "addressee_id": "my-user-id",
  "status": "accepted",
  "created_at": "2026-01-23T10:00:00Z",
  "updated_at": "2026-01-23T10:05:00Z"
}
```

**Error Responses:**
- `403`: 요청 수신자가 아님
- `400`: 대기 중인 요청이 아님
- `404`: 요청을 찾을 수 없음

#### POST /friends/requests/{friendship_id}/reject

친구 요청을 거절합니다 (요청 삭제).

**Response 200:**
```json
{
  "ok": true,
  "message": "Friend request rejected"
}
```

#### DELETE /friends/requests/{friendship_id}

보낸 친구 요청을 취소합니다.

**Response 200:**
```json
{
  "ok": true,
  "message": "Friend request cancelled"
}
```

---

### 친구 관리

#### DELETE /friends/{friendship_id}

친구 관계를 삭제합니다.

**Response 200:**
```json
{
  "ok": true,
  "message": "Friend removed"
}
```

---

### 차단 관리

#### POST /friends/block/{user_id}

사용자를 차단합니다.

**Response 200:**
```json
{
  "id": "uuid",
  "requester_id": "my-user-id",
  "addressee_id": "blocked-user-id",
  "status": "blocked",
  "blocked_by": "my-user-id",
  "created_at": "2026-01-23T10:00:00Z",
  "updated_at": "2026-01-23T10:00:00Z"
}
```

**차단 효과:**
- 차단된 사용자는 친구 요청을 보낼 수 없음
- 차단된 사용자는 공유된 콘텐츠에 접근할 수 없음
- 기존 친구 관계가 있었다면 차단 상태로 변경됨

#### DELETE /friends/block/{user_id}

차단을 해제합니다.

**Response 200:**
```json
{
  "ok": true,
  "message": "User unblocked"
}
```

**Note:** 본인이 차단한 경우에만 해제할 수 있습니다.

---

## 가시성(Visibility) 설정

### 리소스 생성/수정 시 가시성 설정

Schedule, Timer, Todo 생성/수정 시 `visibility` 필드를 포함할 수 있습니다.

#### Schedule 생성 예시

**POST /v1/schedules**
```json
{
  "title": "팀 회의",
  "start_time": "2026-01-23T10:00:00Z",
  "end_time": "2026-01-23T11:00:00Z",
  "visibility": {
    "level": "friends"
  }
}
```

#### 선택한 친구에게만 공유

```json
{
  "title": "비밀 프로젝트",
  "start_time": "2026-01-23T10:00:00Z",
  "end_time": "2026-01-23T11:00:00Z",
  "visibility": {
    "level": "selected",
    "allowed_user_ids": ["friend-id-1", "friend-id-2"]
  }
}
```

**Note:** `allowed_user_ids`에 포함된 사용자는 모두 **친구**여야 합니다.

### 가시성 레벨별 접근 권한

| 레벨 | 소유자 | 친구 | 비친구 |
|------|--------|------|--------|
| `private` | ✅ | ❌ | ❌ |
| `friends` | ✅ | ✅ | ❌ |
| `selected` | ✅ | AllowList만 | ❌ |
| `public` | ✅ | ✅ | ✅ |

### 응답에서 가시성 정보 확인

공유된 리소스를 조회할 때 추가 필드가 포함됩니다:

```json
{
  "id": "uuid",
  "title": "친구의 일정",
  "owner_id": "friend-user-id",
  "visibility_level": "friends",
  "is_shared": true,
  ...
}
```

---

## TypeScript 타입 정의

```typescript
// Friend Types
type FriendshipStatus = "pending" | "accepted" | "blocked";

interface Friendship {
  id: string;
  requester_id: string;
  addressee_id: string;
  status: FriendshipStatus;
  blocked_by?: string;
  created_at: string;
  updated_at: string;
}

interface Friend {
  user_id: string;
  friendship_id: string;
  since: string;
}

interface PendingRequest {
  id: string;
  requester_id: string;
  addressee_id: string;
  created_at: string;
}

interface FriendRequest {
  addressee_id: string;
}

// Visibility Types
type VisibilityLevel = "private" | "friends" | "selected" | "public";

interface VisibilitySettings {
  level: VisibilityLevel;
  allowed_user_ids?: string[];
}

// Extended Resource Types (with visibility)
interface ScheduleWithVisibility extends Schedule {
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

interface TimerWithVisibility extends Timer {
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

interface TodoWithVisibility extends Todo {
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

// Create/Update Types with Visibility
interface ScheduleCreateWithVisibility extends ScheduleCreate {
  visibility?: VisibilitySettings;
}

interface TimerCreateWithVisibility extends TimerCreate {
  visibility?: VisibilitySettings;
}

interface TodoCreateWithVisibility extends TodoCreate {
  visibility?: VisibilitySettings;
}
```

---

## 사용 예시

### 친구 추가 흐름

```typescript
// 1. 친구 요청 보내기
const response = await fetch('/api/v1/friends/requests', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ addressee_id: 'target-user-id' }),
});
const friendship = await response.json();
console.log('요청 보냄:', friendship.id);

// 2. 받은 요청 확인 (상대방)
const requests = await fetch('/api/v1/friends/requests/received');
const pendingRequests = await requests.json();

// 3. 요청 수락 (상대방)
await fetch(`/api/v1/friends/requests/${pendingRequests[0].id}/accept`, {
  method: 'POST',
});

// 4. 친구 목록 확인
const friends = await fetch('/api/v1/friends');
const friendList = await friends.json();
console.log('친구 목록:', friendList);
```

### 일정 공유

```typescript
// 모든 친구에게 공유되는 일정 생성
const schedule = await fetch('/api/v1/schedules', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: '팀 회의',
    start_time: '2026-01-23T10:00:00Z',
    end_time: '2026-01-23T11:00:00Z',
    visibility: {
      level: 'friends',
    },
  }),
});

// 특정 친구에게만 공유
const privateSchedule = await fetch('/api/v1/schedules', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: '비밀 미팅',
    start_time: '2026-01-23T14:00:00Z',
    end_time: '2026-01-23T15:00:00Z',
    visibility: {
      level: 'selected',
      allowed_user_ids: ['trusted-friend-id'],
    },
  }),
});
```

### 가시성 변경

```typescript
// 기존 일정의 가시성 변경
await fetch(`/api/v1/schedules/${scheduleId}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    visibility: {
      level: 'public',
    },
  }),
});
```

---

## 주의사항

### 1. 가시성 기본값

리소스 생성 시 `visibility`를 지정하지 않으면 **PRIVATE**으로 설정됩니다.

### 2. SELECTED_FRIENDS 검증

`selected` 레벨에서 `allowed_user_ids`에 포함된 사용자는 모두 **친구**여야 합니다. 친구가 아닌 사용자를 포함하면 `400 Bad Request`가 반환됩니다.

### 3. 차단 시 접근 제한

차단 관계에서는 양방향으로 접근이 제한됩니다:
- 차단한 사용자 → 차단된 사용자의 PUBLIC 콘텐츠도 접근 불가
- 차단된 사용자 → 차단한 사용자의 모든 콘텐츠 접근 불가

### 4. 친구 관계 삭제 시

친구 관계가 삭제되면:
- 해당 친구에게 `friends` 레벨로 공유된 콘텐츠는 더 이상 접근 불가
- `selected` 레벨의 AllowList에 있었다면 해당 항목도 자동으로 접근 불가

### 5. 소유자 우선

리소스 소유자는 가시성 설정과 관계없이 항상 자신의 리소스에 접근할 수 있습니다.

---

## 에러 코드

| 코드 | 설명 |
|------|------|
| 400 | 잘못된 요청 (자기 자신에게 요청, 친구가 아닌 사용자 AllowList 추가 등) |
| 403 | 접근 거부 (권한 없음, 차단됨) |
| 404 | 리소스를 찾을 수 없음 |
| 409 | 충돌 (이미 친구, 중복 요청) |
