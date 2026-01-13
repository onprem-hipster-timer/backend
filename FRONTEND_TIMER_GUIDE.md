# Timer API 가이드 (프론트엔드 개발자용)

> **최종 업데이트**: 2026-01-14

## 목차

1. [개요](#개요)
2. [데이터 모델](#데이터-모델)
3. [REST API](#rest-api)
4. [양방향 등록 가이드](#양방향-등록-가이드)
5. [TypeScript 타입 정의](#typescript-타입-정의)
6. [사용 예시](#사용-예시)
7. [주의사항](#주의사항)

---

## 개요

Timer API는 **일정(Schedule)**, **할 일(Todo)**, 또는 **독립적으로** 타이머를 생성하고 관리할 수 있습니다.

### 핵심 개념

| 개념 | 설명 |
|------|------|
| **Timer** | 시간 측정 세션. Schedule, Todo, 또는 둘 다에 연결 가능. 독립 타이머도 가능. |
| **Schedule** | 캘린더 일정. 타이머를 통해 작업 시간 측정 가능. |
| **Todo** | 할 일 항목. 타이머를 통해 작업 시간 측정 가능. |

### Timer, Schedule, Todo의 관계

```
┌─────────────────────────────────────────────────────────────────────┐
│  Timer 생성 방법 (양방향 등록)                                        │
│                                                                     │
│  ┌──────────────┐        ┌──────────────┐        ┌──────────────┐  │
│  │   Schedule   │←──────→│    Timer     │←──────→│     Todo     │  │
│  │   (Optional) │        │              │        │   (Optional) │  │
│  └──────────────┘        └──────────────┘        └──────────────┘  │
│                                │                                    │
│                                ↓                                    │
│                     ┌──────────────────┐                            │
│                     │   독립 타이머     │                            │
│                     │  (둘 다 없음)     │                            │
│                     └──────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 데이터 모델

### Timer

```typescript
interface Timer {
  id: string;                   // UUID
  schedule_id?: string;         // Schedule ID (Optional)
  todo_id?: string;             // Todo ID (Optional)
  title?: string;               // 타이머 제목
  description?: string;         // 타이머 설명
  allocated_duration: number;   // 할당 시간 (초 단위)
  elapsed_time: number;         // 경과 시간 (초 단위)
  status: TimerStatus;          // 상태
  started_at?: string;          // 시작 시간 (ISO 8601)
  paused_at?: string;           // 일시정지 시간 (ISO 8601)
  ended_at?: string;            // 종료 시간 (ISO 8601)
  created_at: string;           // 생성 시간 (ISO 8601)
  updated_at: string;           // 수정 시간 (ISO 8601)
  schedule?: Schedule;          // Schedule 정보 (include_schedule=true일 때)
  todo?: Todo;                  // Todo 정보 (include_todo=true일 때)
  tags: Tag[];                  // 연결된 태그 목록
}

type TimerStatus = 
  | "RUNNING"    // 실행 중
  | "PAUSED"     // 일시정지
  | "COMPLETED"  // 완료
  | "CANCELLED"; // 취소됨
```

### TimerCreate

```typescript
interface TimerCreate {
  schedule_id?: string;         // Schedule ID (Optional)
  todo_id?: string;             // Todo ID (Optional)
  title?: string;               // 타이머 제목
  description?: string;         // 타이머 설명
  allocated_duration: number;   // 할당 시간 (초 단위, 양수 필수)
  tag_ids?: string[];           // 태그 ID 리스트
}
```

---

## REST API

### Base URL

```
/v1
```

### Timer API

#### 타이머 생성 및 시작

```http
POST /v1/timers
Content-Type: application/json

{
  "schedule_id": "uuid-or-null",
  "todo_id": "uuid-or-null",
  "title": "작업 타이머",
  "description": "프로젝트 작업",
  "allocated_duration": 3600,
  "tag_ids": ["tag-uuid-1"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `schedule_id` | UUID | ❌ | Schedule ID (Optional) |
| `todo_id` | UUID | ❌ | Todo ID (Optional) |
| `title` | string | ❌ | 타이머 제목 |
| `description` | string | ❌ | 타이머 설명 |
| `allocated_duration` | number | ✅ | 할당 시간 (초 단위, 양수 필수) |
| `tag_ids` | UUID[] | ❌ | 태그 ID 리스트 |

**Query Parameters:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `include_schedule` | boolean | false | Schedule 정보 포함 여부 |
| `include_todo` | boolean | false | Todo 정보 포함 여부 |
| `tag_include_mode` | string | none | 태그 포함 모드 (none, timer_only, inherit_from_schedule) |
| `timezone` | string | UTC | 타임존 (예: Asia/Seoul) |

**응답 (201 Created):**

```json
{
  "id": "timer-uuid",
  "schedule_id": "schedule-uuid",
  "todo_id": null,
  "title": "작업 타이머",
  "description": "프로젝트 작업",
  "allocated_duration": 3600,
  "elapsed_time": 0,
  "status": "RUNNING",
  "started_at": "2024-01-15T10:00:00Z",
  "paused_at": null,
  "ended_at": null,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "schedule": null,
  "todo": null,
  "tags": []
}
```

#### 타이머 조회

```http
GET /v1/timers/{timer_id}
```

#### 타이머 업데이트

```http
PATCH /v1/timers/{timer_id}
Content-Type: application/json

{
  "title": "업데이트된 제목",
  "description": "업데이트된 설명"
}
```

#### 타이머 일시정지

```http
PATCH /v1/timers/{timer_id}/pause
```

#### 타이머 재개

```http
PATCH /v1/timers/{timer_id}/resume
```

#### 타이머 종료

```http
POST /v1/timers/{timer_id}/stop
```

#### 타이머 삭제

```http
DELETE /v1/timers/{timer_id}
```

---

### Schedule 기반 타이머 엔드포인트

#### Schedule의 모든 타이머 조회

```http
GET /v1/schedules/{schedule_id}/timers
```

#### Schedule의 활성 타이머 조회

```http
GET /v1/schedules/{schedule_id}/timers/active
```

활성 타이머가 없으면 404를 반환합니다.

---

### Todo 기반 타이머 엔드포인트

#### Todo의 모든 타이머 조회

```http
GET /v1/todos/{todo_id}/timers
```

**Query Parameters:**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `include_todo` | boolean | false | Todo 정보 포함 여부 |
| `timezone` | string | UTC | 타임존 (예: Asia/Seoul) |

#### Todo의 활성 타이머 조회

```http
GET /v1/todos/{todo_id}/timers/active
```

활성 타이머가 없으면 404를 반환합니다.

---

## 양방향 등록 가이드

Timer는 Schedule, Todo, 또는 둘 다에 연결할 수 있습니다. 둘 다 없으면 독립 타이머가 됩니다.

### 1. Schedule에서 타이머 생성

```typescript
// Schedule에 연결된 타이머 생성
const response = await fetch('/v1/timers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    schedule_id: scheduleId,     // Schedule ID 지정
    allocated_duration: 3600,    // 1시간
    title: "회의 준비"
  })
});

const timer = await response.json();
console.log(timer.schedule_id);  // scheduleId
console.log(timer.todo_id);      // null
```

### 2. Todo에서 타이머 생성

```typescript
// Todo에 연결된 타이머 생성
const response = await fetch('/v1/timers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    todo_id: todoId,             // Todo ID 지정
    allocated_duration: 1800,    // 30분
    title: "Todo 작업"
  })
});

const timer = await response.json();
console.log(timer.schedule_id);  // null
console.log(timer.todo_id);      // todoId
```

### 3. Schedule과 Todo 모두에 연결

```typescript
// Schedule과 Todo 모두에 연결된 타이머 생성
const response = await fetch('/v1/timers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    schedule_id: scheduleId,
    todo_id: todoId,
    allocated_duration: 3600,
    title: "복합 작업"
  })
});

const timer = await response.json();
console.log(timer.schedule_id);  // scheduleId
console.log(timer.todo_id);      // todoId
```

### 4. 독립 타이머 생성

```typescript
// 독립 타이머 생성 (Schedule, Todo 모두 없음)
const response = await fetch('/v1/timers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    allocated_duration: 600,     // 10분
    title: "포모도로 타이머"
  })
});

const timer = await response.json();
console.log(timer.schedule_id);  // null
console.log(timer.todo_id);      // null
```

---

## TypeScript 타입 정의

```typescript
// ============================================================
// Enums
// ============================================================

export type TimerStatus = "RUNNING" | "PAUSED" | "COMPLETED" | "CANCELLED";

// ============================================================
// Timer Types
// ============================================================

export interface Timer {
  id: string;
  schedule_id?: string;
  todo_id?: string;
  title?: string;
  description?: string;
  allocated_duration: number;
  elapsed_time: number;
  status: TimerStatus;
  started_at?: string;
  paused_at?: string;
  ended_at?: string;
  created_at: string;
  updated_at: string;
  schedule?: Schedule;
  todo?: Todo;
  tags: Tag[];
}

export interface TimerCreate {
  schedule_id?: string;
  todo_id?: string;
  title?: string;
  description?: string;
  allocated_duration: number;
  tag_ids?: string[];
}

export interface TimerUpdate {
  title?: string;
  description?: string;
  tag_ids?: string[];
}

// ============================================================
// Query Parameters
// ============================================================

export interface TimerQueryParams {
  include_schedule?: boolean;
  include_todo?: boolean;
  tag_include_mode?: 'none' | 'timer_only' | 'inherit_from_schedule';
  timezone?: string;
}
```

---

## 사용 예시

### 전체 워크플로우 예시

```typescript
// 1. Todo에서 타이머 시작
const startResponse = await fetch('/v1/timers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    todo_id: todoId,
    allocated_duration: 1800,  // 30분
    title: "Todo 작업 시작"
  })
});
const timer = await startResponse.json();
console.log("타이머 시작:", timer.status);  // "RUNNING"

// 2. 타이머 일시정지
const pauseResponse = await fetch(`/v1/timers/${timer.id}/pause`, {
  method: 'PATCH'
});
const pausedTimer = await pauseResponse.json();
console.log("일시정지:", pausedTimer.status);  // "PAUSED"
console.log("경과 시간:", pausedTimer.elapsed_time);  // 경과 시간 (초)

// 3. 타이머 재개
const resumeResponse = await fetch(`/v1/timers/${timer.id}/resume`, {
  method: 'PATCH'
});
const resumedTimer = await resumeResponse.json();
console.log("재개:", resumedTimer.status);  // "RUNNING"

// 4. 타이머 종료
const stopResponse = await fetch(`/v1/timers/${timer.id}/stop`, {
  method: 'POST'
});
const stoppedTimer = await stopResponse.json();
console.log("종료:", stoppedTimer.status);  // "COMPLETED"
console.log("총 경과 시간:", stoppedTimer.elapsed_time);
```

### React Hook 예시

```typescript
import { useState, useEffect, useCallback } from 'react';

// 타이머 상태 관리 훅
function useTimer(timerId: string | null) {
  const [timer, setTimer] = useState<Timer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchTimer = useCallback(async () => {
    if (!timerId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`/v1/timers/${timerId}`);
      if (!response.ok) throw new Error('Failed to fetch timer');
      const data = await response.json();
      setTimer(data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [timerId]);

  const pause = useCallback(async () => {
    if (!timerId) return;
    const response = await fetch(`/v1/timers/${timerId}/pause`, {
      method: 'PATCH'
    });
    if (response.ok) {
      const updated = await response.json();
      setTimer(updated);
    }
  }, [timerId]);

  const resume = useCallback(async () => {
    if (!timerId) return;
    const response = await fetch(`/v1/timers/${timerId}/resume`, {
      method: 'PATCH'
    });
    if (response.ok) {
      const updated = await response.json();
      setTimer(updated);
    }
  }, [timerId]);

  const stop = useCallback(async () => {
    if (!timerId) return;
    const response = await fetch(`/v1/timers/${timerId}/stop`, {
      method: 'POST'
    });
    if (response.ok) {
      const updated = await response.json();
      setTimer(updated);
    }
  }, [timerId]);

  useEffect(() => {
    fetchTimer();
  }, [fetchTimer]);

  return { timer, loading, error, pause, resume, stop, refetch: fetchTimer };
}

// 타이머 생성 훅
function useCreateTimer() {
  const [loading, setLoading] = useState(false);

  const createTimer = async (data: TimerCreate): Promise<Timer> => {
    setLoading(true);
    try {
      const response = await fetch('/v1/timers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create timer');
      }
      
      return await response.json();
    } finally {
      setLoading(false);
    }
  };

  return { createTimer, loading };
}

// Todo 타이머 조회 훅
function useTodoTimers(todoId: string) {
  const [timers, setTimers] = useState<Timer[]>([]);
  const [activeTimer, setActiveTimer] = useState<Timer | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTimers = async () => {
      try {
        // 모든 타이머 조회
        const response = await fetch(`/v1/todos/${todoId}/timers`);
        if (response.ok) {
          const data = await response.json();
          setTimers(data);
        }

        // 활성 타이머 조회
        const activeResponse = await fetch(`/v1/todos/${todoId}/timers/active`);
        if (activeResponse.ok) {
          const activeData = await activeResponse.json();
          setActiveTimer(activeData);
        } else if (activeResponse.status === 404) {
          setActiveTimer(null);
        }
      } finally {
        setLoading(false);
      }
    };

    fetchTimers();
  }, [todoId]);

  return { timers, activeTimer, loading };
}

// 사용 예시
function TimerComponent({ todoId }: { todoId: string }) {
  const { timers, activeTimer, loading } = useTodoTimers(todoId);
  const { createTimer } = useCreateTimer();

  const handleStartTimer = async () => {
    const timer = await createTimer({
      todo_id: todoId,
      allocated_duration: 1800,  // 30분
      title: "작업 타이머"
    });
    console.log("타이머 시작:", timer);
  };

  if (loading) return <div>로딩 중...</div>;

  return (
    <div>
      {activeTimer ? (
        <div>
          <h3>현재 타이머: {activeTimer.title}</h3>
          <p>상태: {activeTimer.status}</p>
          <p>경과: {Math.floor(activeTimer.elapsed_time / 60)}분</p>
        </div>
      ) : (
        <button onClick={handleStartTimer}>타이머 시작</button>
      )}
      
      <h4>타이머 기록</h4>
      <ul>
        {timers.map(timer => (
          <li key={timer.id}>
            {timer.title} - {timer.status} ({Math.floor(timer.elapsed_time / 60)}분)
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## 주의사항

### 1. schedule_id, todo_id 모두 Optional

타이머 생성 시 둘 다 없어도 됩니다 (독립 타이머).

```typescript
// ✅ 모두 허용
{ schedule_id: "...", allocated_duration: 3600 }  // Schedule 연결
{ todo_id: "...", allocated_duration: 3600 }      // Todo 연결
{ schedule_id: "...", todo_id: "...", allocated_duration: 3600 }  // 둘 다 연결
{ allocated_duration: 3600 }  // 독립 타이머
```

### 2. 존재하지 않는 ID 사용 시 에러

```typescript
// ❌ 존재하지 않는 schedule_id: 404 Schedule Not Found
// ❌ 존재하지 않는 todo_id: 404 Todo Not Found
```

### 3. allocated_duration은 양수 필수

```typescript
// ❌ 에러: allocated_duration이 음수 또는 0
{ allocated_duration: -100 }  // 422 Validation Error
{ allocated_duration: 0 }     // 422 Validation Error

// ✅ 올바른 사용
{ allocated_duration: 60 }    // 최소 1초 이상
```

### 4. 태그 상속 모드

`tag_include_mode` 파라미터로 태그 포함 방식을 제어할 수 있습니다:

| 모드 | 설명 |
|------|------|
| `none` | 태그 포함하지 않음 (기본값) |
| `timer_only` | 타이머에 직접 연결된 태그만 포함 |
| `inherit_from_schedule` | 타이머 태그 + Schedule/Todo 태그 상속 |

```typescript
// 태그 상속 예시
const response = await fetch('/v1/timers/uuid?tag_include_mode=inherit_from_schedule');
```

> 💡 `inherit_from_schedule` 모드에서:
> - Schedule이 연결된 경우: 타이머 태그 + Schedule 태그
> - Todo만 연결된 경우: 타이머 태그 + Todo 태그
> - 둘 다 없는 경우: 타이머 태그만

### 5. 날짜/시간 형식

모든 datetime 필드는 **ISO 8601** 형식을 사용합니다.

```typescript
// ✅ 올바른 형식
"2024-01-20T10:00:00Z"      // UTC
"2024-01-20T19:00:00+09:00" // 타임존 포함
```

### 6. 타이머 상태 전이

```
           ┌──────────────────────────────────────┐
           │                                      │
           ↓                                      │
  ┌────────────────┐                              │
  │    RUNNING     │←──────────────┐              │
  └────────────────┘               │              │
           │                       │              │
           ↓ pause                 │ resume       │
  ┌────────────────┐               │              │
  │    PAUSED      │───────────────┘              │
  └────────────────┘                              │
           │                                      │
           ↓ stop                                 │ cancel
  ┌────────────────┐               ┌──────────────┴───┐
  │   COMPLETED    │               │    CANCELLED     │
  └────────────────┘               └──────────────────┘
```

---

## API 요약

### Timer API

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/v1/timers` | 타이머 생성 및 시작 |
| GET | `/v1/timers/{id}` | 타이머 조회 |
| PATCH | `/v1/timers/{id}` | 타이머 업데이트 |
| PATCH | `/v1/timers/{id}/pause` | 타이머 일시정지 |
| PATCH | `/v1/timers/{id}/resume` | 타이머 재개 |
| POST | `/v1/timers/{id}/stop` | 타이머 종료 |
| DELETE | `/v1/timers/{id}` | 타이머 삭제 |

### Schedule 기반 타이머 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/v1/schedules/{id}/timers` | Schedule의 모든 타이머 조회 |
| GET | `/v1/schedules/{id}/timers/active` | Schedule의 활성 타이머 조회 |

### Todo 기반 타이머 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/v1/todos/{id}/timers` | Todo의 모든 타이머 조회 |
| GET | `/v1/todos/{id}/timers/active` | Todo의 활성 타이머 조회 |

---

이 가이드를 참고하여 프론트엔드에서 Timer 기능을 구현하세요!
