# GraphQL API

Hipster Timer Backend는 유연한 데이터 조회를 위해 REST API와 함께 GraphQL API를 제공합니다.

## 엔드포인트

```
POST /v1/graphql
```

## 대화형 플레이그라운드

개발 모드에서 다음 주소로 GraphQL Playground에 접근할 수 있습니다:

```
http://localhost:2614/v1/graphql
```

## 인증

모든 GraphQL 쿼리는 인증이 필요합니다:

```javascript
const response = await fetch('http://localhost:2614/v1/graphql', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query: `
      query {
        calendar(startDate: "2024-01-01", endDate: "2024-01-31") {
          days {
            date
            events {
              id
              title
            }
          }
        }
      }
    `,
  }),
});
```

## 스키마 개요

### Queries (쿼리)

- `calendar` - 일정이 포함된 캘린더 뷰 조회
- `todo` - 단일 투두 조회
- `todos` - 필터링된 투두 목록 조회

### Mutations (뮤테이션)

- `createSchedule` - 새 일정 생성
- `updateSchedule` - 기존 일정 수정
- `deleteSchedule` - 일정 삭제
- `createTodo` - 새 투두 생성
- `updateTodo` - 기존 투두 수정
- `deleteTodo` - 투두 삭제

## 쿼리 예시

### 캘린더 조회

```graphql
query GetCalendar($startDate: Date!, $endDate: Date!) {
  calendar(startDate: $startDate, endDate: $endDate) {
    days {
      date
      events {
        id
        title
        startTime
        endTime
        tags {
          id
          name
          color
        }
      }
    }
  }
}
```

Variables:
```json
{
  "startDate": "2024-01-01",
  "endDate": "2024-01-31"
}
```

### 투두 조회

```graphql
query GetTodos($tagGroupId: UUID) {
  todos(tagGroupId: $tagGroupId) {
    id
    title
    status
    deadline
    parent {
      id
      title
    }
    children {
      id
      title
    }
    tags {
      id
      name
    }
  }
}
```

## 뮤테이션 예시

### 일정 생성

```graphql
mutation CreateSchedule($input: ScheduleInput!) {
  createSchedule(input: $input) {
    id
    title
    startTime
    endTime
  }
}
```

Variables:
```json
{
  "input": {
    "title": "주간 회의",
    "startTime": "2024-01-15T10:00:00Z",
    "endTime": "2024-01-15T12:00:00Z",
    "recurrenceRule": "FREQ=WEEKLY;BYDAY=MO"
  }
}
```

## 에러 처리

GraphQL은 에러를 `errors` 배열로 반환합니다:

```json
{
  "data": null,
  "errors": [
    {
      "message": "인증이 필요합니다. Authorization 헤더에 Bearer 토큰을 제공해주세요.",
      "locations": [{"line": 2, "column": 3}],
      "path": ["calendar"]
    }
  ]
}
```

## Rate Limiting

GraphQL 쿼리는 Rate Limiting이 적용됩니다:

- **기본값**: 사용자당 60초에 60회 요청
- REST API와 동일한 Rate Limit 헤더

## 모범 사례

1. **변수 사용**: 문자열 보간 대신 항상 변수를 사용하세요
2. **필요한 필드만 요청**: GraphQL은 필요한 필드만 요청할 수 있습니다
3. **쿼리 배치**: 단일 요청에 여러 쿼리를 조합하세요
4. **에러 처리**: 응답의 `errors` 배열을 항상 확인하세요
