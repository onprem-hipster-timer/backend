# 일정 타입 구분 가이드 (프론트엔드 개발자용)

## 개요

이 백엔드 API는 **일반 일정**과 **반복 일정**을 구분하여 처리합니다. 
프론트엔드에서 일정을 올바르게 표시하고 수정/삭제하려면 이 구분 방법을 이해해야 합니다.

## 일정 타입 구분 방법

### 1. 일반 일정 (Regular Schedule)

일반 일정은 한 번만 발생하는 일정입니다.

**구분 조건:**
- `recurrence_rule`이 `null` 또는 `undefined`
- `parent_id`가 `null` 또는 `undefined`

**예시:**
```typescript
interface Schedule {
  id: string;
  title: string;
  description: string | null;
  start_time: string; // ISO 8601 형식
  end_time: string;   // ISO 8601 형식
  recurrence_rule: null;        // ✅ null이면 일반 일정
  recurrence_end: null;
  parent_id: null;              // ✅ null이면 일반 일정
  created_at: string;
  tags: Tag[];
}

// 일반 일정 예시
const regularSchedule: Schedule = {
  id: "123e4567-e89b-12d3-a456-426614174000",
  title: "회의",
  description: "프로젝트 회의",
  start_time: "2024-01-15T10:00:00",
  end_time: "2024-01-15T12:00:00",
  recurrence_rule: null,  // ✅ 일반 일정
  recurrence_end: null,
  parent_id: null,        // ✅ 일반 일정
  created_at: "2024-01-01T00:00:00",
  tags: []
};
```

### 2. 반복 일정 (Recurring Schedule)

반복 일정은 주기적으로 반복되는 일정입니다. 두 가지 형태가 있습니다:

#### 2-1. 원본 반복 일정 (Parent Recurring Schedule)

반복 일정의 원본입니다. 이 일정은 DB에 저장되며, 조회 시 가상 인스턴스로 확장됩니다.

**구분 조건:**
- `recurrence_rule`이 `null`이 아님 (RRULE 형식 문자열)
- `parent_id`가 `null` 또는 `undefined`

**예시:**
```typescript
// 원본 반복 일정 예시
const parentRecurringSchedule: Schedule = {
  id: "223e4567-e89b-12d3-a456-426614174000",
  title: "주간 회의",
  description: "매주 월요일 회의",
  start_time: "2024-01-01T10:00:00",  // 첫 번째 인스턴스 시작 시간
  end_time: "2024-01-01T12:00:00",
  recurrence_rule: "FREQ=WEEKLY;BYDAY=MO",  // ✅ 반복 규칙 있음
  recurrence_end: "2024-01-29T23:59:59",   // 반복 종료일
  parent_id: null,                         // ✅ 원본이므로 null
  created_at: "2024-01-01T00:00:00",
  tags: []
};
```

#### 2-2. 가상 인스턴스 (Virtual Instance)

반복 일정의 특정 날짜 인스턴스입니다. 날짜 범위 조회 시 자동으로 생성되어 반환됩니다.

**구분 조건:**
- `recurrence_rule`이 `null` 또는 `undefined` (가상 인스턴스는 반복 규칙 없음)
- `parent_id`가 `null`이 아님 (원본 일정의 ID)

**예시:**
```typescript
// 가상 인스턴스 예시 (원본 반복 일정의 2024-01-08 인스턴스)
const virtualInstance: Schedule = {
  id: "323e4567-e89b-12d3-a456-426614174000",  // 가상 인스턴스는 고유 ID를 가짐
  title: "주간 회의",
  description: "매주 월요일 회의",
  start_time: "2024-01-08T10:00:00",  // 이 인스턴스의 시작 시간
  end_time: "2024-01-08T12:00:00",
  recurrence_rule: null,              // ✅ 가상 인스턴스는 반복 규칙 없음
  recurrence_end: null,
  parent_id: "223e4567-e89b-12d3-a456-426614174000",  // ✅ 원본 일정 ID
  created_at: "2024-01-01T00:00:00",  // 원본 일정의 생성 시간
  tags: []
};
```

## TypeScript 헬퍼 함수

프론트엔드에서 일정 타입을 구분하는 헬퍼 함수 예시:

```typescript
interface Schedule {
  id: string;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string;
  recurrence_rule: string | null;
  recurrence_end: string | null;
  parent_id: string | null;
  created_at: string;
  tags: Tag[];
}

/**
 * 일반 일정인지 확인
 */
function isRegularSchedule(schedule: Schedule): boolean {
  return schedule.recurrence_rule === null && schedule.parent_id === null;
}

/**
 * 원본 반복 일정인지 확인
 */
function isParentRecurringSchedule(schedule: Schedule): boolean {
  return schedule.recurrence_rule !== null && schedule.parent_id === null;
}

/**
 * 가상 인스턴스인지 확인
 */
function isVirtualInstance(schedule: Schedule): boolean {
  return schedule.recurrence_rule === null && schedule.parent_id !== null;
}

/**
 * 반복 일정 관련 일정인지 확인 (원본 또는 가상 인스턴스)
 */
function isRecurringSchedule(schedule: Schedule): boolean {
  return schedule.recurrence_rule !== null || schedule.parent_id !== null;
}

// 사용 예시
const schedule: Schedule = /* API 응답 */;

if (isRegularSchedule(schedule)) {
  console.log("일반 일정입니다");
  // 일반 일정 수정/삭제 로직
} else if (isParentRecurringSchedule(schedule)) {
  console.log("원본 반복 일정입니다");
  // 원본 반복 일정 수정/삭제 로직 (모든 인스턴스에 영향)
} else if (isVirtualInstance(schedule)) {
  console.log("가상 인스턴스입니다");
  // 가상 인스턴스 수정/삭제 로직 (특정 인스턴스만 영향)
}
```

## API 사용 가이드

### 일정 조회

날짜 범위로 일정을 조회하면 반복 일정은 자동으로 가상 인스턴스로 확장되어 반환됩니다.

```typescript
// GET /api/v1/schedules?start_date=2024-01-01T00:00:00&end_date=2024-01-31T23:59:59
const response = await fetch(
  `/api/v1/schedules?start_date=2024-01-01T00:00:00&end_date=2024-01-31T23:59:59`
);
const schedules: Schedule[] = await response.json();

// 반환된 schedules 배열에는:
// - 일반 일정들
// - 반복 일정의 가상 인스턴스들 (각 날짜별로)
// 이 포함됩니다.
```

### 일정 수정

#### 일반 일정 수정
```typescript
// PATCH /api/v1/schedules/{schedule_id}
const response = await fetch(`/api/v1/schedules/${schedule.id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: "수정된 제목",
    start_time: "2024-01-15T11:00:00",
    end_time: "2024-01-15T13:00:00"
  })
});
```

#### 반복 일정 전체 수정
```typescript
// PATCH /api/v1/schedules/{parent_id}
// instance_start 없이 호출하면 원본 반복 일정 전체가 수정됩니다 (모든 인스턴스에 영향)
const response = await fetch(`/api/v1/schedules/${schedule.id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: "수정된 제목",
    recurrence_rule: "FREQ=WEEKLY;BYDAY=TU",  // 반복 규칙 변경
    recurrence_end: "2024-12-31T23:59:59"      // 종료일 변경
  })
});
```

#### 반복 일정의 특정 인스턴스 수정
```typescript
// PATCH /api/v1/schedules/{parent_id}?instance_start={instance_start_time}
// 가상 인스턴스를 수정할 때는 parent_id와 instance_start를 함께 전송
const response = await fetch(
  `/api/v1/schedules/${schedule.parent_id}?instance_start=${schedule.start_time}`,
  {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: "이 인스턴스만 수정된 제목",
      start_time: "2024-01-08T11:00:00",
      end_time: "2024-01-08T13:00:00"
    })
  }
);
```

### 일정 삭제

#### 일반 일정 삭제
```typescript
// DELETE /api/v1/schedules/{schedule_id}
const response = await fetch(`/api/v1/schedules/${schedule.id}`, {
  method: 'DELETE'
});
```

#### 반복 일정 전체 삭제
```typescript
// DELETE /api/v1/schedules/{parent_id}
// instance_start 없이 호출하면 원본 반복 일정 전체가 삭제됩니다 (모든 인스턴스 포함)
const response = await fetch(`/api/v1/schedules/${schedule.id}`, {
  method: 'DELETE'
});
```

#### 반복 일정의 특정 인스턴스 삭제
```typescript
// DELETE /api/v1/schedules/{parent_id}?instance_start={instance_start_time}
// 가상 인스턴스를 삭제할 때는 parent_id와 instance_start를 함께 전송
const response = await fetch(
  `/api/v1/schedules/${schedule.parent_id}?instance_start=${schedule.start_time}`,
  {
    method: 'DELETE'
  }
);
```

## UI 표시 가이드

### 캘린더 뷰

```typescript
// 캘린더에 일정 표시 시
schedules.forEach(schedule => {
  if (isRegularSchedule(schedule)) {
    // 일반 일정: 단순히 표시
    displaySchedule(schedule);
  } else if (isVirtualInstance(schedule)) {
    // 가상 인스턴스: 반복 일정 아이콘과 함께 표시
    displayRecurringInstance(schedule);
  }
});
```

### 일정 상세 뷰

```typescript
// 일정 상세 정보 표시
function renderScheduleDetails(schedule: Schedule) {
  if (isRegularSchedule(schedule)) {
    return (
      <div>
        <h2>{schedule.title}</h2>
        <p>일반 일정</p>
        {/* 일반 일정 정보 */}
      </div>
    );
  } else if (isParentRecurringSchedule(schedule)) {
    return (
      <div>
        <h2>{schedule.title}</h2>
        <p>반복 일정 (원본)</p>
        <p>반복 규칙: {schedule.recurrence_rule}</p>
        {/* 원본 반복 일정 정보 */}
      </div>
    );
  } else if (isVirtualInstance(schedule)) {
    return (
      <div>
        <h2>{schedule.title}</h2>
        <p>반복 일정 (인스턴스)</p>
        <p>원본 ID: {schedule.parent_id}</p>
        {/* 가상 인스턴스 정보 */}
      </div>
    );
  }
}
```

## 주의사항

1. **가상 인스턴스는 DB에 저장되지 않습니다**
   - 날짜 범위 조회 시에만 동적으로 생성됩니다
   - 각 가상 인스턴스는 고유한 ID를 가지지만, 이는 조회 시에만 유효합니다

2. **가상 인스턴스 수정/삭제 시**
   - `parent_id`와 `instance_start`를 함께 전송해야 합니다
   - 이렇게 하면 해당 인스턴스만 수정/삭제되고, 다른 인스턴스는 영향받지 않습니다

3. **원본 반복 일정 수정/삭제 시**
   - `instance_start` 쿼리 파라미터 없이 원본 일정 ID로 수정/삭제하면 모든 인스턴스에 영향을 줍니다
   - 반복 규칙(`recurrence_rule`), 종료일(`recurrence_end`), 제목, 설명 등을 수정하면 모든 인스턴스가 변경됩니다
   - 특정 인스턴스만 수정/삭제하려면 `instance_start` 쿼리 파라미터를 포함하여 가상 인스턴스 API를 사용하세요

4. **반복 규칙 형식**
   - `recurrence_rule`은 RRULE 형식을 따릅니다
   - 예: `"FREQ=WEEKLY;BYDAY=MO"` (매주 월요일)
   - 예: `"FREQ=DAILY;INTERVAL=2"` (2일마다)

## 요약

| 일정 타입 | `recurrence_rule` | `parent_id` | 설명 |
|---------|------------------|-------------|------|
| 일반 일정 | `null` | `null` | 한 번만 발생하는 일정 |
| 원본 반복 일정 | `"FREQ=..."` | `null` | 반복 일정의 원본 (DB에 저장) |
| 가상 인스턴스 | `null` | 원본 ID | 반복 일정의 특정 날짜 인스턴스 (조회 시 생성) |

이 가이드를 참고하여 프론트엔드에서 일정을 올바르게 처리하세요!
