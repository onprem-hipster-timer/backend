# GraphQL API

Hipster Timer Backend provides a GraphQL API alongside the REST API for flexible data querying.

## Endpoint

```
POST /v1/graphql
```

## Interactive Playground

In development mode, you can access the GraphQL Playground at:

```
http://localhost:2614/v1/graphql
```

## Authentication

All GraphQL queries require authentication:

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

## Schema Overview

### Queries

- `calendar` - Get calendar view with schedules
- `todo` - Get a single todo
- `todos` - List todos with filtering

### Mutations

- `createSchedule` - Create a new schedule
- `updateSchedule` - Update an existing schedule
- `deleteSchedule` - Delete a schedule
- `createTodo` - Create a new todo
- `updateTodo` - Update an existing todo
- `deleteTodo` - Delete a todo

## Example Queries

### Get Calendar

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

### Get Todos

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

## Example Mutations

### Create Schedule

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
    "title": "Weekly Meeting",
    "startTime": "2024-01-15T10:00:00Z",
    "endTime": "2024-01-15T12:00:00Z",
    "recurrenceRule": "FREQ=WEEKLY;BYDAY=MO"
  }
}
```

## Error Handling

GraphQL returns errors in the `errors` array:

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

GraphQL queries are subject to rate limiting:

- **Default**: 60 requests per 60 seconds per user
- Same rate limit headers as REST API

## Best Practices

1. **Use Variables**: Always use variables instead of string interpolation
2. **Request Only Needed Fields**: GraphQL allows you to request only the fields you need
3. **Batch Queries**: Combine multiple queries in a single request
4. **Handle Errors**: Always check the `errors` array in responses
