# Todo-일정 변환 가이드 (프론트엔드 개발자용)

## 개요

이 백엔드 API는 **Todo**와 **일정(Schedule)** 간 양방향 변환을 지원합니다.
프론트엔드에서 Todo를 일정으로 변환하거나 일정을 Todo로 변환하려면 이 가이드를 참고하세요.

## Todo와 일정의 구분

### Todo

Todo는 `is_todo=true`인 일정입니다. 두 가지 유형이 있습니다:

1. **마감 시간이 없는 Todo**: `start_time`이 917초(1970-01-01T00:15:17Z)로 설정됨
2. **마감 시간이 있는 Todo**: 실제 마감 시간이 설정됨

**구분 조건:**
- `is_todo`가 `true`
- `start_time`이 917초이거나 실제 마감 시간

**예시:**
```typescript
interface Todo {
  id: string;
  title: string;
  description: string | null;
  is_todo: true;  // ✅ 항상 true
  start_time: string;  // 917초 또는 실제 마감 시간
  end_time: string;
  created_at: string;
  tags: Tag[];
}

// 마감 시간이 없는 Todo
const todoWithoutDeadline: Todo = {
  id: "123e4567-e89b-12d3-a456-426614174000",
  title: "할 일",
  description: "해야 할 일",
  is_todo: true,
  start_time: "1970-01-01T00:15:17Z",  // ✅ 917초
  end_time: "1970-01-01T00:30:34Z",
  created_at: "2024-01-01T00:00:00Z",
  tags: []
};

// 마감 시간이 있는 Todo
const todoWithDeadline: Todo = {
  id: "223e4567-e89b-12d3-a456-426614174000",
  title: "마감 있는 할 일",
  description: "2024-01-20까지 완료",
  is_todo: true,
  start_time: "2024-01-20T10:00:00Z",  // ✅ 실제 마감 시간
  end_time: "2024-01-20T12:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
  tags: []
};
```

### 일정 (Schedule)

일정은 `is_todo=false`인 항목입니다.

**구분 조건:**
- `is_todo`가 `false`
- `start_time`이 실제 시간 (917초가 아님)

**예시:**
```typescript
interface Schedule {
  id: string;
  title: string;
  description: string | null;
  is_todo: false;  // ✅ false
  start_time: string;  // 실제 시간
  end_time: string;
  created_at: string;
  tags: Tag[];
}

// 일반 일정
const schedule: Schedule = {
  id: "323e4567-e89b-12d3-a456-426614174000",
  title: "회의",
  description: "프로젝트 회의",
  is_todo: false,  // ✅ 일정
  start_time: "2024-01-15T10:00:00Z",
  end_time: "2024-01-15T12:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
  tags: []
};
```

## TypeScript 헬퍼 함수

프론트엔드에서 Todo와 일정을 구분하는 헬퍼 함수 예시:

```typescript
interface Schedule {
  id: string;
  title: string;
  description: string | null;
  is_todo: boolean;
  start_time: string;
  end_time: string;
  created_at: string;
  tags: Tag[];
}

// 917초 (마감 시간 없는 Todo 식별용)
const TODO_DATETIME = "1970-01-01T00:15:17Z";

/**
 * Todo인지 확인
 */
function isTodo(schedule: Schedule): boolean {
  return schedule.is_todo === true;
}

/**
 * 일정인지 확인
 */
function isSchedule(schedule: Schedule): boolean {
  return schedule.is_todo === false;
}

/**
 * 마감 시간이 있는 Todo인지 확인
 */
function isTodoWithDeadline(todo: Schedule): boolean {
  return todo.is_todo === true && todo.start_time !== TODO_DATETIME;
}

/**
 * 마감 시간이 없는 Todo인지 확인
 */
function isTodoWithoutDeadline(todo: Schedule): boolean {
  return todo.is_todo === true && todo.start_time === TODO_DATETIME;
}

// 사용 예시
const item: Schedule = /* API 응답 */;

if (isTodo(item)) {
  if (isTodoWithDeadline(item)) {
    console.log("마감 시간이 있는 Todo입니다");
    // 일정 목록에도 표시됨
  } else {
    console.log("마감 시간이 없는 Todo입니다");
    // Todo 목록에만 표시됨
  }
} else {
  console.log("일정입니다");
}
```

## API 사용 가이드

### Todo -> 일정 변환

Todo를 일정으로 변환하려면 `PATCH /v1/todos/{todo_id}`를 사용합니다.

#### 마감 시간이 있는 Todo -> 일정 변환

마감 시간이 이미 설정된 Todo는 `is_todo=false`만 전송하면 됩니다.

```typescript
// PATCH /v1/todos/{todo_id}
const response = await fetch(`/v1/todos/${todo.id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    is_todo: false
  })
});

const schedule = await response.json();
// 이제 일정이 되었습니다 (is_todo=false)
```

#### 마감 시간이 없는 Todo -> 일정 변환

마감 시간이 없는 Todo(917초)를 일정으로 변환하려면 **마감 시간이 필수**입니다.

```typescript
// PATCH /v1/todos/{todo_id}
const response = await fetch(`/v1/todos/${todo.id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    is_todo: false,
    start_time: "2024-01-20T10:00:00Z",  // 필수
    end_time: "2024-01-20T12:00:00Z"     // 필수
  })
});

const schedule = await response.json();
// 이제 일정이 되었습니다 (is_todo=false)
```

**에러 처리:**
```typescript
try {
  const response = await fetch(`/v1/todos/${todo.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      is_todo: false
      // start_time, end_time 없음
    })
  });
  
  if (!response.ok) {
    const error = await response.json();
    if (error.error_type === 'DeadlineRequiredForConversionError') {
      // 마감 시간이 필요합니다
      console.error("마감 시간을 설정해주세요");
    }
  }
} catch (error) {
  console.error("변환 실패", error);
}
```

### 일정 -> Todo 변환

일정을 Todo로 변환하려면 `PATCH /v1/schedules/{schedule_id}`를 사용합니다.

```typescript
// PATCH /v1/schedules/{schedule_id}
const response = await fetch(`/v1/schedules/${schedule.id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    is_todo: true
  })
});

const todo = await response.json();
// 이제 Todo가 되었습니다 (is_todo=true)
// start_time/end_time은 유지되어 마감 시간이 있는 Todo가 됩니다
```

## UI 표시 가이드

### Todo 목록 뷰

```typescript
// Todo 목록 표시
todos.forEach(todo => {
  if (isTodoWithDeadline(todo)) {
    // 마감 시간이 있는 Todo: 마감 시간 표시
    displayTodoWithDeadline(todo);
  } else {
    // 마감 시간이 없는 Todo: 마감 시간 없음 표시
    displayTodoWithoutDeadline(todo);
  }
});
```

### 일정 목록 뷰

```typescript
// 일정 목록 표시 (마감 시간이 있는 Todo도 포함)
schedules.forEach(item => {
  if (isSchedule(item)) {
    // 일반 일정
    displaySchedule(item);
  } else if (isTodoWithDeadline(item)) {
    // 마감 시간이 있는 Todo (일정 목록에도 표시됨)
    displayTodoAsSchedule(item);
  }
});
```

### 변환 버튼 UI

```typescript
// Todo -> 일정 변환 버튼
function TodoToScheduleButton({ todo }: { todo: Schedule }) {
  const [isConverting, setIsConverting] = useState(false);
  
  const handleConvert = async () => {
    if (isTodoWithoutDeadline(todo)) {
      // 마감 시간이 없는 Todo: 마감 시간 입력 모달 표시
      const deadline = await showDeadlineInputModal();
      if (!deadline) return;
      
      setIsConverting(true);
      try {
        await fetch(`/v1/todos/${todo.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            is_todo: false,
            start_time: deadline.start_time,
            end_time: deadline.end_time
          })
        });
        // 성공: 일정 목록으로 이동
      } catch (error) {
        // 에러 처리
      } finally {
        setIsConverting(false);
      }
    } else {
      // 마감 시간이 있는 Todo: 바로 변환
      setIsConverting(true);
      try {
        await fetch(`/v1/todos/${todo.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            is_todo: false
          })
        });
        // 성공: 일정 목록으로 이동
      } catch (error) {
        // 에러 처리
      } finally {
        setIsConverting(false);
      }
    }
  };
  
  return (
    <button onClick={handleConvert} disabled={isConverting}>
      {isTodoWithoutDeadline(todo) 
        ? "마감 시간 설정하고 일정으로 변환"
        : "일정으로 변환"}
    </button>
  );
}

// 일정 -> Todo 변환 버튼
function ScheduleToTodoButton({ schedule }: { schedule: Schedule }) {
  const [isConverting, setIsConverting] = useState(false);
  
  const handleConvert = async () => {
    setIsConverting(true);
    try {
      await fetch(`/v1/schedules/${schedule.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          is_todo: true
        })
      });
      // 성공: Todo 목록으로 이동
    } catch (error) {
      // 에러 처리
    } finally {
      setIsConverting(false);
    }
  };
  
  return (
    <button onClick={handleConvert} disabled={isConverting}>
      Todo로 변환
    </button>
  );
}
```

## 주의사항

1. **마감 시간이 없는 Todo 변환**
   - 마감 시간이 없는 Todo(917초)를 일정으로 변환하려면 반드시 `start_time`과 `end_time`을 함께 전송해야 합니다.
   - 마감 시간 없이 변환을 시도하면 `400 Bad Request` 에러가 발생합니다.

2. **마감 시간이 있는 Todo 변환**
   - 마감 시간이 이미 설정된 Todo는 `is_todo=false`만 전송하면 됩니다.
   - 기존 마감 시간이 유지됩니다.

3. **일정 -> Todo 변환**
   - 일정을 Todo로 변환하면 `is_todo=true`가 되지만, `start_time`/`end_time`은 유지됩니다.
   - 따라서 마감 시간이 있는 Todo가 됩니다.

4. **일정 목록에서 Todo 표시**
   - 마감 시간이 있는 Todo는 자동으로 일정 목록에도 표시됩니다.
   - `GET /v1/schedules?start_date=...&end_date=...` 조회 시 포함됩니다.

5. **917초 상수**
   - 마감 시간이 없는 Todo는 `start_time`이 `1970-01-01T00:15:17Z` (917초)로 설정됩니다.
   - 이 값을 상수로 정의하여 비교에 사용하세요.

## 요약

| 변환 방향 | API | 필수 필드 | 설명 |
|---------|-----|----------|------|
| Todo(마감시간 있음) -> 일정 | `PATCH /v1/todos/{id}` | `is_todo: false` | 마감 시간 유지 |
| Todo(마감시간 없음) -> 일정 | `PATCH /v1/todos/{id}` | `is_todo: false`, `start_time`, `end_time` | 마감 시간 필수 |
| 일정 -> Todo | `PATCH /v1/schedules/{id}` | `is_todo: true` | 마감 시간 유지 (있는 Todo가 됨) |

이 가이드를 참고하여 프론트엔드에서 Todo와 일정 변환을 올바르게 처리하세요!

