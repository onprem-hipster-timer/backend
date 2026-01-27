# Visibility (가시성) API 가이드 (프론트엔드 개발자용)

> **최종 업데이트**: 2026-01-28

## 목차

1. [개요](#개요)
2. [데이터 모델](#데이터-모델)
3. [가시성 설정 방법](#가시성-설정-방법)
4. [공유 리소스 조회](#공유-리소스-조회)
5. [TypeScript 타입 정의](#typescript-타입-정의)
6. [사용 예시](#사용-예시)
7. [UI/UX 가이드라인](#uiux-가이드라인)
8. [주의사항](#주의사항)
9. [에러 처리](#에러-처리)

---

## 개요

Visibility(가시성) 시스템은 리소스(Schedule, Timer, Todo)의 **공유 범위**를 제어합니다.

### 지원 리소스

| 리소스 | 설명 |
|--------|------|
| **Schedule** | 일정 |
| **Timer** | 타이머 |
| **Todo** | 할 일 |

### 가시성 레벨

```
┌─────────────────────────────────────────────────────────────────────┐
│  Visibility Levels (접근 범위)                                       │
│                                                                     │
│  ┌────────────┐                                                    │
│  │  PRIVATE   │──→ 본인만 접근 가능 (기본값)                         │
│  └────────────┘                                                    │
│        │                                                           │
│        ↓ 확장                                                       │
│  ┌────────────┐                                                    │
│  │  SELECTED  │──→ 선택한 친구만 접근 가능 (AllowList 기반)          │
│  └────────────┘                                                    │
│        │                                                           │
│        ↓ 확장                                                       │
│  ┌────────────┐                                                    │
│  │  FRIENDS   │──→ 모든 친구 접근 가능                               │
│  └────────────┘                                                    │
│        │                                                           │
│        ↓ 확장                                                       │
│  ┌────────────┐                                                    │
│  │  PUBLIC    │──→ 모든 사용자 접근 가능                             │
│  └────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 접근 제어 규칙

```
┌─────────────────────────────────────────────────────────────────────┐
│  접근 권한 결정 흐름                                                  │
│                                                                     │
│  1. 소유자인가? ──────────→ ✅ 항상 접근 가능                         │
│           ↓ 아니오                                                  │
│  2. 차단 관계인가? ────────→ ❌ 접근 불가 (양방향 체크)                 │
│           ↓ 아니오                                                  │
│  3. 가시성 레벨 확인:                                                │
│     - PUBLIC ────────────→ ✅ 접근 가능                              │
│     - FRIENDS ───────────→ 친구인가? → ✅ 접근 가능 / ❌ 접근 불가     │
│     - SELECTED ──────────→ AllowList에 있는가? → ✅/❌               │
│     - PRIVATE ───────────→ ❌ 접근 불가                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 데이터 모델

### VisibilityLevel (가시성 레벨)

```typescript
type VisibilityLevel = 
  | "private"   // 본인만 (기본값)
  | "friends"   // 모든 친구
  | "selected"  // 선택한 친구만 (AllowList)
  | "public";   // 전체 공개
```

### ResourceType (리소스 타입)

```typescript
type ResourceType = 
  | "schedule"
  | "timer"
  | "todo";
```

### VisibilitySettings (가시성 설정 - 입력용)

```typescript
interface VisibilitySettings {
  level: VisibilityLevel;
  allowed_user_ids?: string[];  // "selected" 레벨에서만 사용
}
```

### VisibilityRead (가시성 조회 결과)

```typescript
interface VisibilityRead {
  id: string;                   // UUID
  resource_type: ResourceType;
  resource_id: string;          // UUID
  owner_id: string;             // 소유자 ID
  level: VisibilityLevel;
  allowed_user_ids: string[];   // AllowList 사용자 목록
  created_at: string;           // ISO 8601
  updated_at: string;           // ISO 8601
}
```

### 공유된 리소스 응답 필드

모든 리소스(Schedule, Timer, Todo) 조회 시 가시성 관련 필드가 포함됩니다:

```typescript
interface ResourceWithVisibility {
  // ... 기본 리소스 필드 ...
  
  owner_id?: string;                // 소유자 ID (공유된 리소스일 때)
  visibility_level?: VisibilityLevel;  // 가시성 레벨
  is_shared: boolean;               // 공유된 리소스인지 (타인 소유)
}
```

---

## 가시성 설정 방법

### 리소스 생성 시 가시성 설정

모든 리소스(Schedule, Timer, Todo) 생성 시 `visibility` 필드를 포함할 수 있습니다.

#### 예시: Schedule 생성

**POST /api/v1/schedules**

```json
{
  "title": "팀 회의",
  "start_time": "2026-01-28T10:00:00Z",
  "end_time": "2026-01-28T11:00:00Z",
  "visibility": {
    "level": "friends"
  }
}
```

#### 예시: Timer 생성 (선택한 친구에게만)

**POST /api/v1/timers**

```json
{
  "schedule_id": "uuid-here",
  "visibility": {
    "level": "selected",
    "allowed_user_ids": ["friend-id-1", "friend-id-2"]
  }
}
```

#### 예시: Todo 생성 (전체 공개)

**POST /api/v1/todos**

```json
{
  "title": "공개 할 일",
  "tag_group_id": "uuid-here",
  "visibility": {
    "level": "public"
  }
}
```

### 리소스 수정 시 가시성 변경

**PATCH /api/v1/schedules/{id}**

```json
{
  "visibility": {
    "level": "private"
  }
}
```

### 가시성 기본값

`visibility` 필드를 지정하지 않으면 **PRIVATE**으로 설정됩니다.

---

## 공유 리소스 조회

### scope 파라미터

리소스 조회 API에서 `scope` 파라미터를 사용하여 조회 범위를 지정합니다:

| scope | 설명 |
|-------|------|
| `mine` | 내 리소스만 (기본값) |
| `shared` | 공유된 타인의 리소스만 |
| `all` | 내 리소스 + 공유된 리소스 |

#### Schedule 조회 예시

**GET /api/v1/schedules?start_date=2026-01-01&end_date=2026-01-31&scope=all**

```json
[
  {
    "id": "my-schedule-id",
    "title": "내 일정",
    "owner_id": "my-user-id",
    "is_shared": false,
    "visibility_level": null
  },
  {
    "id": "shared-schedule-id",
    "title": "친구의 공유 일정",
    "owner_id": "friend-user-id",
    "is_shared": true,
    "visibility_level": "friends"
  }
]
```

#### Timer 조회 예시

**GET /api/v1/timers?scope=shared**

```json
[
  {
    "id": "timer-id",
    "owner_id": "friend-user-id",
    "is_shared": true,
    "visibility_level": "public"
  }
]
```

#### Todo 조회 예시

**GET /api/v1/todos/{group_id}?scope=all**

```json
{
  "items": [
    {
      "id": "todo-id",
      "title": "공유된 할 일",
      "owner_id": "friend-user-id",
      "is_shared": true,
      "visibility_level": "selected"
    }
  ]
}
```

---

## TypeScript 타입 정의

```typescript
// ===== 가시성 타입 =====

type VisibilityLevel = "private" | "friends" | "selected" | "public";

type ResourceType = "schedule" | "timer" | "todo";

type ResourceScope = "mine" | "shared" | "all";

// 가시성 설정 (생성/수정 시 사용)
interface VisibilitySettings {
  level: VisibilityLevel;
  allowed_user_ids?: string[];
}

// 가시성 조회 결과
interface VisibilityRead {
  id: string;
  resource_type: ResourceType;
  resource_id: string;
  owner_id: string;
  level: VisibilityLevel;
  allowed_user_ids: string[];
  created_at: string;
  updated_at: string;
}

// ===== 리소스 생성 타입 (가시성 포함) =====

interface ScheduleCreate {
  title: string;
  description?: string;
  start_time: string;  // ISO 8601
  end_time: string;    // ISO 8601
  recurrence_rule?: string;
  recurrence_end?: string;
  tag_ids?: string[];
  visibility?: VisibilitySettings;
}

interface TimerCreate {
  schedule_id?: string;
  todo_id?: string;
  visibility?: VisibilitySettings;
}

interface TodoCreate {
  title: string;
  description?: string;
  tag_group_id: string;
  deadline?: string;
  parent_id?: string;
  visibility?: VisibilitySettings;
}

// ===== 리소스 수정 타입 (가시성 포함) =====

interface ScheduleUpdate {
  title?: string;
  description?: string;
  start_time?: string;
  end_time?: string;
  visibility?: VisibilitySettings;
}

interface TimerUpdate {
  // Timer 필드...
  visibility?: VisibilitySettings;
}

interface TodoUpdate {
  title?: string;
  description?: string;
  deadline?: string;
  visibility?: VisibilitySettings;
}

// ===== 리소스 조회 타입 (가시성 정보 포함) =====

interface ScheduleRead {
  id: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  created_at: string;
  // 가시성 관련 필드
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

interface TimerRead {
  id: string;
  started_at?: string;
  ended_at?: string;
  elapsed_seconds: number;
  is_running: boolean;
  // 가시성 관련 필드
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

interface TodoRead {
  id: string;
  title: string;
  description?: string;
  deadline?: string;
  status: string;
  created_at: string;
  // 가시성 관련 필드
  owner_id?: string;
  visibility_level?: VisibilityLevel;
  is_shared: boolean;
}

// ===== 유틸리티 타입 =====

// 가시성 레벨 표시 텍스트
const VISIBILITY_LABELS: Record<VisibilityLevel, string> = {
  private: "비공개",
  friends: "친구 공개",
  selected: "일부 친구 공개",
  public: "전체 공개",
};

// 가시성 레벨 아이콘 (예시)
const VISIBILITY_ICONS: Record<VisibilityLevel, string> = {
  private: "🔒",
  friends: "👥",
  selected: "👤",
  public: "🌐",
};
```

---

## 사용 예시

### 가시성 설정 UI 컴포넌트

```typescript
// 가시성 선택 드롭다운
async function VisibilitySelector({
  value,
  onChange,
  friends,
}: {
  value: VisibilitySettings;
  onChange: (settings: VisibilitySettings) => void;
  friends: Friend[];
}) {
  const handleLevelChange = (level: VisibilityLevel) => {
    onChange({
      level,
      allowed_user_ids: level === "selected" ? [] : undefined,
    });
  };

  const handleAllowedUsersChange = (userIds: string[]) => {
    onChange({
      level: "selected",
      allowed_user_ids: userIds,
    });
  };

  return (
    <div>
      <select value={value.level} onChange={(e) => handleLevelChange(e.target.value)}>
        <option value="private">🔒 비공개</option>
        <option value="friends">👥 모든 친구</option>
        <option value="selected">👤 일부 친구</option>
        <option value="public">🌐 전체 공개</option>
      </select>

      {value.level === "selected" && (
        <FriendMultiSelect
          friends={friends}
          selected={value.allowed_user_ids || []}
          onChange={handleAllowedUsersChange}
        />
      )}
    </div>
  );
}
```

### 일정 생성 (가시성 포함)

```typescript
async function createScheduleWithVisibility(
  schedule: Omit<ScheduleCreate, 'visibility'>,
  visibility: VisibilitySettings
): Promise<ScheduleRead> {
  const response = await fetch('/api/v1/schedules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...schedule,
      visibility,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }

  return response.json();
}

// 사용 예시
const schedule = await createScheduleWithVisibility(
  {
    title: "팀 미팅",
    start_time: "2026-01-28T10:00:00Z",
    end_time: "2026-01-28T11:00:00Z",
  },
  {
    level: "selected",
    allowed_user_ids: ["colleague-id-1", "colleague-id-2"],
  }
);
```

### 가시성 변경

```typescript
async function updateVisibility(
  resourceType: ResourceType,
  resourceId: string,
  visibility: VisibilitySettings
): Promise<void> {
  const endpoints: Record<ResourceType, string> = {
    schedule: `/api/v1/schedules/${resourceId}`,
    timer: `/api/v1/timers/${resourceId}`,
    todo: `/api/v1/todos/${resourceId}`,
  };

  const response = await fetch(endpoints[resourceType], {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visibility }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
}

// 사용 예시: 일정을 친구 공개로 변경
await updateVisibility('schedule', scheduleId, { level: 'friends' });

// 사용 예시: 할 일을 비공개로 변경
await updateVisibility('todo', todoId, { level: 'private' });
```

### 공유된 리소스 조회

```typescript
async function fetchSchedules(
  startDate: Date,
  endDate: Date,
  scope: ResourceScope = 'mine'
): Promise<ScheduleRead[]> {
  const params = new URLSearchParams({
    start_date: startDate.toISOString(),
    end_date: endDate.toISOString(),
    scope,
  });

  const response = await fetch(`/api/v1/schedules?${params}`);
  return response.json();
}

// 내 일정만 조회
const mySchedules = await fetchSchedules(start, end, 'mine');

// 공유된 일정만 조회
const sharedSchedules = await fetchSchedules(start, end, 'shared');

// 모든 일정 조회 (내 것 + 공유된 것)
const allSchedules = await fetchSchedules(start, end, 'all');
```

### 공유된 리소스와 내 리소스 구분하여 표시

```typescript
function ScheduleList({ schedules }: { schedules: ScheduleRead[] }) {
  const mySchedules = schedules.filter(s => !s.is_shared);
  const sharedSchedules = schedules.filter(s => s.is_shared);

  return (
    <div>
      <section>
        <h2>내 일정</h2>
        {mySchedules.map(schedule => (
          <ScheduleItem key={schedule.id} schedule={schedule} />
        ))}
      </section>

      {sharedSchedules.length > 0 && (
        <section>
          <h2>공유된 일정</h2>
          {sharedSchedules.map(schedule => (
            <ScheduleItem 
              key={schedule.id} 
              schedule={schedule}
              showOwner={true}
            />
          ))}
        </section>
      )}
    </div>
  );
}

function ScheduleItem({ 
  schedule, 
  showOwner = false 
}: { 
  schedule: ScheduleRead; 
  showOwner?: boolean;
}) {
  return (
    <div className={schedule.is_shared ? 'shared-item' : ''}>
      <h3>{schedule.title}</h3>
      {showOwner && <span>by {schedule.owner_id}</span>}
      {schedule.visibility_level && (
        <span className="visibility-badge">
          {VISIBILITY_ICONS[schedule.visibility_level]}
        </span>
      )}
    </div>
  );
}
```

---

## UI/UX 가이드라인

### 가시성 표시 아이콘

| 레벨 | 아이콘 | 설명 |
|------|--------|------|
| `private` | 🔒 | 자물쇠 - 비공개 |
| `friends` | 👥 | 사람들 - 친구 공개 |
| `selected` | 👤 | 한 사람 - 선택한 친구 |
| `public` | 🌐 | 지구본 - 전체 공개 |

### 가시성 선택 UI 권장사항

1. **기본값 명시**: "비공개(기본)"으로 표시
2. **친구 선택 UI**: `selected` 레벨 선택 시 친구 멀티 선택 UI 표시
3. **경고 표시**: `public` 선택 시 "모든 사용자가 볼 수 있습니다" 경고
4. **친구 제한**: AllowList에 친구만 추가 가능함을 안내

### 공유된 리소스 표시 권장사항

1. **시각적 구분**: 공유된 리소스는 배경색/테두리로 구분
2. **소유자 표시**: 공유된 리소스에는 소유자 정보 표시
3. **읽기 전용 표시**: 공유된 리소스는 수정 불가능함을 표시
4. **가시성 배지**: 리소스의 가시성 레벨을 아이콘으로 표시

### 예시: 캘린더 뷰

```
┌────────────────────────────────────────────────────────────────┐
│  January 2026                                                  │
├────────────────────────────────────────────────────────────────┤
│  28 (Mon)                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 🔒 내 개인 일정                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 👥 팀 회의                        shared by @friend      │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 🌐 공개 이벤트                    shared by @organizer   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 주의사항

### 1. 가시성 기본값

리소스 생성 시 `visibility`를 지정하지 않으면 **PRIVATE**으로 설정됩니다.

### 2. SELECTED 레벨 제약사항

- `allowed_user_ids`에 포함된 사용자는 모두 **친구**여야 합니다.
- 친구가 아닌 사용자를 포함하면 `400 Bad Request` 에러가 발생합니다.
- 친구 관계가 삭제되면 해당 친구는 AllowList에서 자동으로 접근 권한을 잃습니다.

### 3. 차단 시 접근 제한

차단 관계에서는 **양방향**으로 접근이 제한됩니다:
- 차단한 사용자 → 차단된 사용자의 PUBLIC 콘텐츠도 접근 불가
- 차단된 사용자 → 차단한 사용자의 모든 콘텐츠 접근 불가

### 4. 친구 관계 삭제 시

친구 관계가 삭제되면:
- 해당 친구에게 `friends` 레벨로 공유된 콘텐츠 접근 불가
- `selected` 레벨의 AllowList에 있었다면 해당 항목도 접근 불가

### 5. 소유자 우선 권한

리소스 소유자는 가시성 설정과 관계없이 **항상** 자신의 리소스에 접근할 수 있습니다.

### 6. 공유된 리소스는 읽기 전용

공유된 리소스(`is_shared: true`)는 수정하거나 삭제할 수 없습니다. 소유자만 수정 권한이 있습니다.

### 7. 연관 리소스의 가시성

- Todo의 Schedule이 공유되면, 해당 Schedule에서 Todo 정보를 볼 수 있습니다.
- Timer가 공유되면, 연관된 Schedule/Todo 정보도 함께 조회됩니다.

---

## 에러 처리

### 에러 코드

| 코드 | 상황 | 설명 |
|------|------|------|
| `400` | 잘못된 요청 | 친구가 아닌 사용자를 AllowList에 추가 시도 |
| `403` | 접근 거부 | 가시성 권한이 없는 리소스 접근 시도 |
| `404` | 찾을 수 없음 | 존재하지 않는 리소스 또는 가시성 설정 |

### 에러 응답 예시

#### 친구가 아닌 사용자 AllowList 추가 시

**400 Bad Request**

```json
{
  "detail": "Cannot share with non-friend users in SELECTED_FRIENDS mode"
}
```

#### 권한이 없는 리소스 접근 시

**403 Forbidden**

```json
{
  "detail": "You don't have permission to access this resource"
}
```

### 에러 처리 예시 코드

```typescript
async function handleVisibilityError(response: Response): Promise<never> {
  const error = await response.json();
  
  switch (response.status) {
    case 400:
      if (error.detail.includes('non-friend')) {
        throw new Error('선택한 사용자 중 친구가 아닌 사람이 있습니다.');
      }
      throw new Error('잘못된 요청입니다.');
    
    case 403:
      throw new Error('이 리소스에 접근할 권한이 없습니다.');
    
    case 404:
      throw new Error('리소스를 찾을 수 없습니다.');
    
    default:
      throw new Error(error.detail || '알 수 없는 오류가 발생했습니다.');
  }
}

// 사용 예시
async function updateScheduleVisibility(id: string, visibility: VisibilitySettings) {
  const response = await fetch(`/api/v1/schedules/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visibility }),
  });

  if (!response.ok) {
    await handleVisibilityError(response);
  }

  return response.json();
}
```

---

## 관련 문서

- [Friend API 가이드](./FRONTEND_FRIEND_GUIDE.md) - 친구 관계 관리
- [Schedule API 가이드](./FRONTEND_SCHEDULE_GUIDE.md) - 일정 관리
- [Timer API 가이드](./FRONTEND_TIMER_GUIDE.md) - 타이머 관리
- [Todo API 가이드](./FRONTEND_TODO_GUIDE.md) - 할 일 관리
