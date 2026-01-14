<div align="center">

<a id="top"></a>

# ⏱️ Hipster Timer Backend

**일정, 타이머, 할일을 통합 관리하는 생산성 백엔드 API**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![GraphQL](https://img.shields.io/badge/GraphQL-Strawberry-E10098?style=flat-square&logo=graphql&logoColor=white)](https://strawberry.rocks)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supported-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

[Features](#features) •
[Quick Start](#quick-start) •
[API Reference](#api-reference) •
[Architecture](#architecture) •
[Testing](#testing) •
[Configuration](#configuration) •
[For Developers](#for-developers)

**🌐 [English](README.md)**

</div>

---

<a id="overview"></a>

## 📖 Overview

**Hipster Timer Backend**는 개인 생산성 관리를 위한 올인원 백엔드 API입니다. 일정 관리, 포모도로 스타일 타이머, 계층형 할일 목록, 유연한 태그 시스템을 하나의 API로 제공합니다.

> 💡 **Note**: 이 프로젝트는 400개 이상의 테스트와 함께 실사용 환경을 고려하여 설계되었습니다.

### 왜 Hipster Timer인가?

- 🔄 **반복 일정**: iCalendar RRULE 표준으로 복잡한 반복 패턴 지원 — 예외 날짜 처리, 가상 인스턴스 확장까지 구현
- ⏰ **타이머 세션**: 일정에 연결된 시간 추적으로 실제 작업 시간 측정
- 🌳 **계층형 Todo**: 트리 구조로 복잡한 프로젝트를 체계적으로 관리 — 순환 참조 방지, 조상 자동 포함 등 엣지 케이스 처리
- 🏷️ **통합 태그 시스템**: 일정, 타이머, 할일을 태그로 연결하고 필터링
- 🌏 **타임존 지원**: KST ↔ UTC 변환, 다양한 타임존 포맷 지원
- 📡 **듀얼 API**: REST와 GraphQL 중 선호하는 방식으로 사용

---

<a id="features"></a>

## ✨ Features

### 📅 Schedule (일정 관리)

| 기능 | 설명 |
|------|------|
| **CRUD** | 일정 생성, 조회, 수정, 삭제 |
| **반복 일정** | RRULE 형식 (`FREQ=DAILY`, `FREQ=WEEKLY;BYDAY=MO,WE,FR`) |
| **가상 인스턴스** | 날짜 범위 조회 시 반복 일정 자동 확장 |
| **예외 처리** | 특정 날짜만 수정하거나 건너뛰기 |
| **태그 필터링** | 태그 ID, 그룹 ID로 AND 조건 필터링 |
| **타임존** | Asia/Seoul, +09:00 등 다양한 형식 지원 |

### ⏱️ Timer (타이머 세션)

| 기능 | 설명 |
|------|------|
| **상태 관리** | `running` → `paused` → `completed` |
| **시간 추적** | 할당 시간 대비 실제 경과 시간 측정 |
| **일시정지/재개** | 중단 후 이어서 진행 |
| **태그 상속** | 부모 Schedule의 태그 자동 상속 옵션 |

### ✅ Todo (할일 관리)

| 기능 | 설명 |
|------|------|
| **트리 구조** | 무제한 깊이의 부모-자식 관계 |
| **마감 시간** | deadline 설정 시 Schedule 자동 생성 |
| **무결성 검증** | 순환 참조, 자기 참조, 그룹 불일치 방지 |
| **조상 포함** | 필터 시 매칭 노드의 조상도 자동 포함 |
| **통계 API** | 태그별 Todo 개수 집계 |

### 🏷️ Tag System (태그 시스템)

| 기능 | 설명 |
|------|------|
| **그룹 기반** | TagGroup으로 태그를 논리적으로 분류 |
| **색상 지원** | `#RRGGBB` 형식의 커스텀 색상 |
| **고유성 보장** | 그룹 내 태그 이름 중복 방지 |
| **자동 정리** | 마지막 태그 삭제 시 빈 그룹 자동 삭제 |

### 🗓️ Holiday (공휴일)

| 기능 | 설명 |
|------|------|
| **API 연동** | 한국천문연구원 공공데이터 API |
| **백그라운드 동기화** | 앱 시작 시 자동으로 공휴일 데이터 갱신 |

---

<a id="quick-start"></a>

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- pip 또는 uv

### Installation

```bash
# 저장소 클론
git clone https://github.com/your-username/hipster-timer-backend.git
cd hipster-timer-backend

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정 (선택사항)
cp .env.example .env
```

### Run

```bash
# 개발 서버 실행
uvicorn app.main:app --port 2614 --reload

# 또는 Docker로 실행
docker compose up
```

서버가 시작되면:
- 📖 REST API: http://localhost:2614/docs (Swagger UI)
- 🔮 GraphQL: http://localhost:2614/v1/graphql (Apollo Sandbox)

---

<a id="api-reference"></a>

## 📚 API Reference

### REST API Endpoints

모든 엔드포인트는 `/v1` prefix를 사용합니다.

#### Schedules

```http
GET    /v1/schedules                    # 날짜 범위로 일정 조회
POST   /v1/schedules                    # 새 일정 생성
GET    /v1/schedules/{id}               # 특정 일정 조회
PATCH  /v1/schedules/{id}               # 일정 수정
DELETE /v1/schedules/{id}               # 일정 삭제
GET    /v1/schedules/{id}/timers        # 일정의 타이머 목록
GET    /v1/schedules/{id}/timers/active # 활성 타이머 조회
```

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `start_date` | datetime | 조회 시작일 (필수) |
| `end_date` | datetime | 조회 종료일 (필수) |
| `timezone` | string | 타임존 (예: `Asia/Seoul`, `+09:00`) |
| `tag_ids` | UUID[] | 태그 ID 필터 (AND 조건) |
| `group_ids` | UUID[] | 태그 그룹 ID 필터 |

**Example:**
```bash
# 일정 생성
curl -X POST http://localhost:2614/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "title": "주간 회의",
    "start_time": "2024-01-01T10:00:00Z",
    "end_time": "2024-01-01T12:00:00Z",
    "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
    "recurrence_end": "2024-03-31T23:59:59Z"
  }'

# 날짜 범위로 조회 (타임존 적용)
curl "http://localhost:2614/v1/schedules?start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z&timezone=Asia/Seoul"
```

#### Timers

```http
POST   /v1/timers                # 타이머 생성 (자동 시작)
GET    /v1/timers/{id}           # 타이머 조회
PATCH  /v1/timers/{id}           # 타이머 수정
DELETE /v1/timers/{id}           # 타이머 삭제
PATCH  /v1/timers/{id}/pause     # 일시정지
PATCH  /v1/timers/{id}/resume    # 재개
POST   /v1/timers/{id}/stop      # 종료
```

**Query Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `include_schedule` | bool | 연결된 Schedule 포함 여부 |
| `tag_include_mode` | string | `none`, `timer_only`, `inherit_from_schedule` |

**Example:**
```bash
# 타이머 생성 (30분 할당)
curl -X POST http://localhost:2614/v1/timers \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_id": "uuid-here",
    "title": "집중 작업",
    "allocated_duration": 1800
  }'

# 타이머 일시정지
curl -X PATCH http://localhost:2614/v1/timers/{id}/pause
```

#### Todos

```http
GET    /v1/todos          # Todo 목록 조회
POST   /v1/todos          # Todo 생성
GET    /v1/todos/{id}     # 특정 Todo 조회
PATCH  /v1/todos/{id}     # Todo 수정
DELETE /v1/todos/{id}     # Todo 삭제
GET    /v1/todos/stats    # 통계 조회
```

**Example:**
```bash
# 마감 시간이 있는 Todo 생성 (Schedule 자동 생성)
curl -X POST http://localhost:2614/v1/todos \
  -H "Content-Type: application/json" \
  -d '{
    "title": "보고서 작성",
    "tag_group_id": "group-uuid",
    "deadline": "2024-01-15T18:00:00Z"
  }'

# 하위 Todo 생성
curl -X POST http://localhost:2614/v1/todos \
  -H "Content-Type: application/json" \
  -d '{
    "title": "자료 수집",
    "tag_group_id": "group-uuid",
    "parent_id": "parent-todo-uuid"
  }'
```

#### Tags

```http
GET    /v1/tags/groups           # 태그 그룹 목록
POST   /v1/tags/groups           # 태그 그룹 생성
GET    /v1/tags/groups/{id}      # 특정 그룹 조회
PATCH  /v1/tags/groups/{id}      # 그룹 수정
DELETE /v1/tags/groups/{id}      # 그룹 삭제
GET    /v1/tags                  # 태그 목록
POST   /v1/tags                  # 태그 생성
DELETE /v1/tags/{id}             # 태그 삭제
```

#### Holidays

```http
GET    /v1/holidays              # 공휴일 목록 조회
```

### GraphQL API

`/v1/graphql` 엔드포인트에서 Apollo Sandbox를 통해 스키마를 탐색할 수 있습니다.

---

<a id="architecture"></a>

## 🏗️ Architecture

### Design Philosophy

이 프로젝트는 **Layered Architecture**를 따릅니다:

- **Router Layer** (`api/`): HTTP 요청 처리, 입력 검증
- **Service Layer** (`domain/*/service.py`): 비즈니스 로직 캡슐화
- **Domain Layer** (`domain/*/schema/`): DTO, 타입 정의
- **Data Layer** (`models/`, `crud/`): 영속성 처리

각 레이어는 명확한 책임을 가지며, 의존성은 항상 안쪽(Domain)으로 향합니다. 이를 통해 비즈니스 로직 수정 시 영향 범위를 최소화하고, 테스트 작성을 용이하게 합니다.

### Project Structure

```
hipster-timer-backend/
├── app/
│   ├── api/
│   │   └── v1/                    # API 라우터
│   │       ├── schedules.py
│   │       ├── timers.py
│   │       ├── todos.py
│   │       ├── tags.py
│   │       ├── holidays.py
│   │       └── graphql.py
│   ├── core/                      # 핵심 설정
│   │   ├── config.py              # 환경 변수 설정
│   │   ├── logging.py             # 로깅 설정
│   │   └── error_handlers.py      # 예외 처리
│   ├── crud/                      # CRUD 유틸리티
│   ├── db/                        # 데이터베이스 세션
│   ├── domain/                    # 도메인 로직 (DDD)
│   │   ├── schedule/
│   │   │   ├── service.py         # 비즈니스 로직
│   │   │   ├── schema/            # DTO, Types
│   │   │   └── exceptions.py      # 도메인 예외
│   │   ├── timer/
│   │   ├── todo/
│   │   ├── tag/
│   │   ├── holiday/
│   │   └── dateutil/              # 날짜/타임존 유틸리티
│   ├── models/                    # SQLModel 엔티티
│   │   ├── schedule.py
│   │   ├── timer.py
│   │   ├── todo.py
│   │   └── tag.py
│   ├── middleware/                # 미들웨어
│   └── main.py                    # 앱 진입점
├── alembic/                       # DB 마이그레이션
├── tests/                         # 테스트
│   ├── domain/                    # 단위 테스트
│   ├── test_*_e2e.py              # E2E 테스트
│   └── test_*_integration.py      # 통합 테스트
├── requirements.txt
├── Dockerfile
├── compose.yaml
└── README.md
```

### Data Model

```mermaid
erDiagram
    TagGroup ||--o{ Tag : contains
    TagGroup ||--o{ Todo : "groups"
    
    Todo ||--o{ Todo : "parent-child"
    Todo ||--o{ Schedule : "creates (deadline)"
    Todo }o--o{ Tag : "tagged"
    
    Schedule ||--o{ TimerSession : has
    Schedule ||--o{ ScheduleException : "exceptions"
    Schedule }o--o{ Tag : "tagged"
    
    TimerSession }o--o{ Tag : "tagged"

    TagGroup {
        uuid id PK
        string name
        string color
        boolean is_todo_group
    }
    
    Tag {
        uuid id PK
        uuid group_id FK
        string name
        string color
    }
    
    Schedule {
        uuid id PK
        string title
        datetime start_time
        datetime end_time
        string recurrence_rule
        datetime recurrence_end
        uuid source_todo_id FK
        enum state
    }
    
    Todo {
        uuid id PK
        uuid tag_group_id FK
        uuid parent_id FK
        string title
        datetime deadline
        enum status
    }
    
    TimerSession {
        uuid id PK
        uuid schedule_id FK
        int allocated_duration
        int elapsed_time
        enum status
    }
```

### Tech Stack

| Category | Technology |
|----------|------------|
| **Framework** | FastAPI 0.120 |
| **ORM** | SQLModel 0.0.29 + SQLAlchemy 2.0 |
| **GraphQL** | Strawberry 0.288 |
| **Database** | SQLite (개발), PostgreSQL 호환 |
| **Migration** | Alembic |
| **Validation** | Pydantic 2.12 |
| **Testing** | pytest, pytest-asyncio |
| **Container** | Docker, Docker Compose |

---

<a id="testing"></a>

## 🧪 Testing

이 프로젝트는 **401개의 테스트**로 핵심 로직을 검증합니다. 반복 일정의 예외 처리, 타임존 경계 케이스, 트리 구조의 무결성 등 실제 서비스에서 발생할 수 있는 다양한 시나리오를 커버합니다.

```bash
# 전체 테스트 실행
pytest

# E2E 테스트만 실행
pytest -m e2e

# 통합 테스트만 실행
pytest -m integration

# 특정 도메인 테스트
pytest tests/domain/schedule/

# 커버리지 리포트
pytest --cov=app --cov-report=html
```

### PostgreSQL 테스트

기본적으로 테스트는 SQLite 인메모리 데이터베이스에서 실행됩니다. PostgreSQL로 테스트하려면:

```bash
# 1. PostgreSQL 컨테이너 시작
docker compose -f docker-compose.test.yaml up -d

# 2. PostgreSQL 준비 완료 대기
docker compose -f docker-compose.test.yaml ps

# 3. PostgreSQL로 테스트 실행
# Windows PowerShell
$env:TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"
pytest

# Linux/macOS
TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb" pytest

# 4. 정리
docker compose -f docker-compose.test.yaml down -v
```

| 환경 변수 | 설명 | 기본값 |
|----------|------|--------|
| `TEST_DATABASE_URL` | 테스트 DB 연결 문자열 | SQLite 인메모리 |

### Test Structure

| 테스트 유형 | 위치 | 설명 |
|-------------|------|------|
| **Unit** | `tests/domain/` | 개별 서비스 로직, 엣지 케이스 검증 |
| **Integration** | `tests/test_*_integration.py` | DB 연동, 트랜잭션 롤백 테스트 |
| **E2E** | `tests/test_*_e2e.py` | HTTP API 전체 흐름 테스트 |

### Coverage Report

```
Name                                                Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------------
app\__init__.py                                         0      0   100%
app\api\__init__.py                                     0      0   100%
app\api\v1\__init__.py                                 15      0   100%
app\api\v1\graphql.py                                  27     10    63%   56-71
app\api\v1\holidays.py                                 22     10    55%   41-56
app\api\v1\schedules.py                                86      2    98%   181, 213
app\api\v1\tags.py                                     51      9    82%   54-55, 77-78, 88-90, 137-138
app\api\v1\timers.py                                  120     17    86%   74, 211-214, 261-264, 311-314, 361-364
app\api\v1\todos.py                                    38      0   100%
app\core\__init__.py                                    0      0   100%
app\core\auth.py                                      115     14    88%   95, 146, 237, 287-305
app\core\base_model.py                                 15      2    87%   39-40
app\core\config.py                                     26      0   100%
app\core\constants.py                                  14      0   100%
app\core\error_handlers.py                             74     18    76%   109-126, 149-150, 177-183, 218-221, 230-236
app\core\logging.py                                    24     17    29%   14-39, 44-63
app\crud\__init__.py                                    2      0   100%
app\crud\holiday.py                                    72     34    53%   36-37, 83-97, 115, 173-184, 212-258
app\crud\schedule.py                                   68      3    96%   37-39
app\crud\tag.py                                       126      8    94%   237, 256-260, 276, 305-310, 327
app\crud\timer.py                                      23      0   100%
app\crud\todo.py                                       45      2    96%   75, 90
app\db\__init__.py                                      0      0   100%
app\db\session.py                                     100     38    62%   22, 36-40, 55-57, 63-72, 77-86, 99, 108, 121-122, 125, 168-180, 194-206, 233-239, 248-254
app\domain\__init__.py                                  0      0   100%
app\domain\dateutil\__init__.py                         0      0   100%
app\domain\dateutil\exceptions.py                       4      0   100%
app\domain\dateutil\service.py                         77      0   100%
app\domain\holiday\__init__.py                          7      0   100%
app\domain\holiday\client.py                          125     97    22%   47-48, 57-72, 81, 92-102, 113-115, 125-129, 139-143, 156, 178, 199-229, 241-271, 284, 306, 327-357, 369-399
app\domain\holiday\enums.py                            12      3    75%   23-29, 33
app\domain\holiday\exceptions.py                       10      0   100%
app\domain\holiday\logger.py                           65     30    54%   45, 135-153, 163-167, 177-179, 189-190, 216-224, 235, 245
app\domain\holiday\model.py                            25      0   100%
app\domain\holiday\schema\__init__.py                   2      0   100%
app\domain\holiday\schema\dto.py                       84     29    65%   50-67, 78, 91-98, 103-107, 122-124, 145, 150, 154
app\domain\holiday\service.py                         127     37    71%   93-104, 122-125, 135-136, 147, 163, 179, 195, 213-214, 225-239, 250, 408-410, 460-480
app\domain\holiday\sync_guard.py                       42      0   100%
app\domain\holiday\tasks.py                            31     18    42%   50-79
app\domain\schedule\__init__.py                         0      0   100%
app\domain\schedule\dependencies.py                    20     20     0%   9-70
app\domain\schedule\enums.py                            5      0   100%
app\domain\schedule\exceptions.py                      19      0   100%
app\domain\schedule\model.py                            2      0   100%
app\domain\schedule\schema\__init__.py                  0      0   100%
app\domain\schedule\schema\dto.py                      80      1    99%   97
app\domain\schedule\schema\query.py                    65      3    95%   88, 156-159
app\domain\schedule\schema\types.py                    33      1    97%   52
app\domain\schedule\service.py                        256     45    82%   120, 139-145, 210, 230-231, 352, 364-375, 409, 462, 464, 466, 473-475, 503-505, 538, 553-554, 582, 596, 643, 669-687
app\domain\tag\__init__.py                              0      0   100%
app\domain\tag\dependencies.py                         17     17     0%   9-65
app\domain\tag\exceptions.py                           11      0   100%
app\domain\tag\model.py                                 5      0   100%
app\domain\tag\schema\__init__.py                       2      0   100%
app\domain\tag\schema\dto.py                           67      0   100%
app\domain\tag\schema\types.py                         33      1    97%   56
app\domain\tag\service.py                             191     32    83%   79, 98, 124, 148, 160, 182, 215, 240, 259, 283, 301-310, 314-316, 328, 346-355, 359-361, 373
app\domain\timer\__init__.py                            0      0   100%
app\domain\timer\dependencies.py                       12     12     0%   9-41
app\domain\timer\exceptions.py                         13      0   100%
app\domain\timer\model.py                               2      0   100%
app\domain\timer\schema\__init__.py                     0      0   100%
app\domain\timer\schema\dto.py                         75      6    92%   129-130, 138-144
app\domain\timer\service.py                           128      6    95%   160, 198, 232, 267, 288, 321
app\domain\todo\__init__.py                             0      0   100%
app\domain\todo\dependencies.py                        11     11     0%   6-32
app\domain\todo\enums.py                                6      0   100%
app\domain\todo\exceptions.py                          16      0   100%
app\domain\todo\model.py                                2      0   100%
app\domain\todo\schema\__init__.py                      2      0   100%
app\domain\todo\schema\dto.py                          49      0   100%
app\domain\todo\service.py                            200     21    90%   128, 135, 263, 293, 304-308, 389-402, 413-416
app\main.py                                            69     42    39%   38-102
app\middleware\__init__.py                              0      0   100%
app\middleware\request_logger.py                       13      0   100%
app\models\__init__.py                                  7      0   100%
app\models\base.py                                      8      0   100%
app\models\schedule.py                                 34      0   100%
app\models\tag.py                                      43      0   100%
app\models\timer.py                                    20      0   100%
app\models\todo.py                                     22      0   100%
app\ratelimit\__init__.py                               0      0   100%
app\ratelimit\config.py                                22      0   100%
app\ratelimit\exceptions.py                             7      7     0%   4-14
app\ratelimit\limiter.py                               25      7    72%   56-58, 68-69, 77, 95
app\ratelimit\middleware.py                            38      6    84%   51, 103-109
app\ratelimit\storage\__init__.py                       3      0   100%
app\ratelimit\storage\base.py                          24      4    83%   51, 62, 71, 80
app\ratelimit\storage\memory.py                        64      5    92%   71, 89, 145, 148-149
app\schemas\__init__.py                                 0      0   100%
app\utils\__init__.py                                   0      0   100%
app\utils\recurrence.py                                47      8    83%   40-42, 60-64, 91
app\utils\validators.py                                11      0   100%
app\valid\schedule.py                                   7      0   100%
app\valid\tag.py                                       11      0   100%
tests\__init__.py                                       0      0   100%
tests\conftest.py                                     109      7    94%   63-65, 84, 115-117
tests\core\__init__.py                                  0      0   100%
tests\core\test_auth.py                               351      1    99%   78
tests\domain\__init__.py                                0      0   100%
tests\domain\dateutil\__init__.py                       0      0   100%
tests\domain\dateutil\test_datetime_service.py        135      0   100%
tests\domain\dateutil\test_locdate_service.py         160      0   100%
tests\domain\dateutil\test_timezone_conversion.py     133     18    86%   58-62, 151-154, 210, 216, 232, 238-243, 258, 264
tests\domain\dateutil\test_timezone_service.py         57      2    96%   81-83
tests\domain\holiday\__init__.py                        0      0   100%
tests\domain\holiday\conftest.py                        8      0   100%
tests\domain\holiday\test_service.py                  289      0   100%
tests\domain\holiday\test_sync_guard.py                73      0   100%
tests\domain\schedule\__init__.py                       0      0   100%
tests\domain\schedule\test_recurring_schedule.py      402      0   100%
tests\domain\schedule\test_service.py                 236      0   100%
tests\domain\tag\__init__.py                            0      0   100%
tests\domain\tag\test_service.py                      385      1    99%   79
tests\domain\timer\__init__.py                          0      0   100%
tests\domain\timer\test_service.py                    157      0   100%
tests\domain\todo\__init__.py                           0      0   100%
tests\domain\todo\test_service.py                     533      0   100%
tests\ratelimit\__init__.py                             0      0   100%
tests\ratelimit\conftest.py                            34      0   100%
tests\ratelimit\test_config.py                         57      0   100%
tests\ratelimit\test_middleware.py                     58      0   100%
tests\ratelimit\test_storage.py                        62      0   100%
tests\test_auth_e2e.py                                 95      0   100%
tests\test_graphql.py                                 331      0   100%
tests\test_schedules_e2e.py                           422      0   100%
tests\test_schedules_integration.py                    72      0   100%
tests\test_tags_e2e.py                                110      0   100%
tests\test_timers_e2e.py                              471      0   100%
tests\test_timers_integration.py                      253      0   100%
tests\test_todos_e2e.py                               399      0   100%
tests\utils\__init__.py                                 0      0   100%
tests\utils\test_validators.py                         41      0   100%
---------------------------------------------------------------------------------
TOTAL                                                8904    682    92%
```

---

## ⚙️ Configuration

### Environment Variables

`.env` 파일 또는 환경 변수로 설정합니다.

#### 환경 모드

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | 실행 환경 (`development`, `staging`, `production`) | `development` |

> ⚠️ **프로덕션 모드**: `ENVIRONMENT=production` 설정 시 아래 설정이 자동으로 적용됩니다:
> - `DEBUG` → `False`
> - `OPENAPI_URL` → `""` (비활성화)
> - `DOCS_URL` → `""` (비활성화)
> - `REDOC_URL` → `""` (비활성화)
> - `GRAPHQL_ENABLE_PLAYGROUND` → `False`
> - `GRAPHQL_ENABLE_INTROSPECTION` → `False`

**빠른 설정:**

```bash
# 개발 환경 (기본)
ENVIRONMENT=development

# 프로덕션 환경
ENVIRONMENT=production
```

#### 기본 설정

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | 디버그 모드 활성화 | `True` |
| `OPENAPI_URL` | OpenAPI 스키마 URL (빈 문자열로 비활성화) | `/openapi.json` |
| `DOCS_URL` | Swagger UI URL (빈 문자열로 비활성화) | `/docs` |
| `REDOC_URL` | ReDoc URL (빈 문자열로 비활성화) | `/redoc` |
| `LOG_LEVEL` | 로그 레벨 | `INFO` |
| `HOLIDAY_API_SERVICE_KEY` | 공공데이터포털 API 키 | - |
| `GRAPHQL_ENABLE_PLAYGROUND` | GraphQL Sandbox 활성화 | `True` |
| `GRAPHQL_ENABLE_INTROSPECTION` | GraphQL Introspection 허용 | `True` |

#### 데이터베이스

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | DB 연결 문자열 | `sqlite:///./schedule.db` |
| `POOL_SIZE` | 커넥션 풀 크기 | `5` |
| `MAX_OVERFLOW` | 최대 초과 연결 수 | `10` |
| `DB_POOL_PRE_PING` | 연결 유효성 검사 | `True` |
| `DB_POOL_RECYCLE` | 연결 재활용 시간 (초) | `3600` |

**데이터베이스 URL 예시:**

```bash
# SQLite (개발 환경)
DATABASE_URL=sqlite:///./schedule.db

# PostgreSQL (프로덕션)
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

#### 인증 (OIDC)

> 📖 **상세 가이드**: [FRONTEND_AUTH_GUIDE.md](FRONTEND_AUTH_GUIDE.md)

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_ENABLED` | OIDC 인증 활성화 | `True` |
| `OIDC_ISSUER_URL` | OIDC Provider의 Issuer URL | - |
| `OIDC_AUDIENCE` | 토큰 검증용 Client ID | - |
| `OIDC_DISCOVERY_URL` | 커스텀 Discovery 엔드포인트 | 자동 생성 |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS 캐시 TTL (초) | `3600` |

**빠른 설정:**

```bash
# 개발 환경 (인증 비활성화)
OIDC_ENABLED=false

# 프로덕션 환경
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm
OIDC_AUDIENCE=my-frontend-app
```

#### Rate Limit (요청 제한)

> 📖 **상세 가이드**: [RATE_LIMIT_GUIDE.md](RATE_LIMIT_GUIDE.md)

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Rate Limit 활성화 | `True` |
| `RATE_LIMIT_DEFAULT_WINDOW` | 기본 윈도우 크기 (초) | `60` |
| `RATE_LIMIT_DEFAULT_REQUESTS` | 윈도우당 최대 요청 수 | `60` |

**빠른 설정:**

```bash
# 개발 환경 (Rate Limit 비활성화)
RATE_LIMIT_ENABLED=false

# 프로덕션 환경 (기본 설정)
RATE_LIMIT_ENABLED=true
```

#### 프록시 설정 (Cloudflare / Trusted Proxy)

| Variable | Description | Default |
|----------|-------------|---------|
| `CF_ENABLED` | Cloudflare 프록시 모드 활성화 | `False` |
| `CF_IP_CACHE_TTL` | Cloudflare IP 목록 캐시 TTL (초) | `86400` |
| `TRUSTED_PROXY_IPS` | 신뢰할 프록시 IP (콤마 구분, CIDR 지원) | `""` |

> ⚠️ **보안 경고**: 프록시 뒤에서 운영할 때 잘못된 설정은 공격자가 클라이언트 IP를 스푸핑하여 Rate Limit을 우회할 수 있게 합니다. 환경에 맞게 정확히 설정하세요.

**빠른 설정:**

```bash
# Cloudflare 환경
CF_ENABLED=true

# Nginx / 로드밸런서 환경
CF_ENABLED=false
TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16

# 직접 연결 (개발 환경)
# 기본값 사용 - 설정 불필요
```

**동작 매트릭스:**

| CF_ENABLED | TRUSTED_PROXY_IPS | 요청 출처 | IP 추출 방식 |
|------------|-------------------|----------|-------------|
| `true` | (무시됨) | Cloudflare IP | `CF-Connecting-IP` 헤더 |
| `true` | (무시됨) | 다른 IP | `request.client.host` |
| `false` | 설정됨 | Trusted IP | `X-Forwarded-For` 헤더 |
| `false` | 설정됨 | 다른 IP | `request.client.host` |
| `false` | 비어있음 | 어디든 | `request.client.host` |

#### CORS (Cross-Origin Resource Sharing)

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ALLOWED_ORIGINS` | 허용할 origin (콤마로 구분) | `*` |
| `CORS_ALLOW_CREDENTIALS` | 자격 증명(쿠키 등) 허용 여부 | `False` |
| `CORS_ALLOW_METHODS` | 허용할 HTTP 메서드 (콤마로 구분) | `*` |
| `CORS_ALLOW_HEADERS` | 허용할 헤더 (콤마로 구분) | `*` |

> ⚠️ **주의**: `CORS_ALLOWED_ORIGINS="*"`와 `CORS_ALLOW_CREDENTIALS=true`는 함께 사용할 수 없습니다.
> credentials를 허용하려면 반드시 특정 origin을 지정해야 합니다.

**빠른 설정:**

```bash
# 개발 환경 (모든 origin 허용)
CORS_ALLOWED_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false

# 프로덕션 환경 (특정 도메인만 허용)
CORS_ALLOWED_ORIGINS=https://example.com,https://app.example.com
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
CORS_ALLOW_HEADERS=Authorization,Content-Type
```

### Database Migration

```bash
# 새 마이그레이션 생성
alembic revision --autogenerate -m "description"

# 마이그레이션 적용
alembic upgrade head

# 롤백
alembic downgrade -1
```

---

## 🐳 Docker

### 빌드된 이미지 사용 (권장)

GitHub Container Registry에서 빌드된 이미지를 받아 실행합니다:

```bash
# 최신 이미지 받기
docker pull ghcr.io/onprem-hipster-timer/backend:latest

# 또는 특정 버전 받기
docker pull ghcr.io/onprem-hipster-timer/backend:v2026.01.13-f81a7c0

# 컨테이너 실행
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=sqlite:///./data/schedule.db \
  -e OIDC_ENABLED=false \
  -v hipster-timer-data:/app/data \
  ghcr.io/onprem-hipster-timer/backend:latest
```

**PostgreSQL과 함께 사용:**

```bash
# PostgreSQL로 실행
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=postgresql://user:password@host:5432/dbname \
  -e OIDC_ENABLED=false \
  -e ENVIRONMENT=production \
  ghcr.io/onprem-hipster-timer/backend:latest
```

**Docker Compose로 실행:**

```yaml
# compose.yaml
services:
  backend:
    image: ghcr.io/onprem-hipster-timer/backend:latest
    ports:
      - "2614:2614"
    environment:
      - DATABASE_URL=sqlite:///./data/schedule.db
      - OIDC_ENABLED=false
    volumes:
      - hipster-timer-data:/app/data

volumes:
  hipster-timer-data:
```

```bash
docker compose up -d
```

### 소스에서 직접 빌드

```bash
# 빌드 및 실행
docker compose up --build

# 백그라운드 실행
docker compose up -d

# 로그 확인
docker compose logs -f
```

**Exposed Port:** `2614`

---

<a id="for-developers"></a>

## 🛠️ For Developers

이 코드베이스를 Fork하거나 학습 목적으로 활용하실 분들을 위한 안내입니다.

### 커스터마이징 포인트

| 목적 | 위치 | 설명 |
|------|------|------|
| 새 도메인 추가 | `app/domain/` | 기존 도메인 구조를 참고하여 확장 |
| DB 변경 | `app/db/session.py` | SQLite/PostgreSQL 자동 감지, 최적화된 풀 설정 |
| 인증 추가 | `app/middleware/` | 미들웨어 레이어에서 JWT 등 인증 로직 추가 |
| API 버전 추가 | `app/api/` | v2 라우터 생성 후 `main.py`에서 마운트 |

### 참고할 만한 구현

- **RRULE 반복 일정**: `app/domain/schedule/` — 가상 인스턴스 확장, 예외 처리 로직
- **계층형 데이터**: `app/domain/todo/` — 순환 참조 검증, 조상 자동 포함
- **타임존 처리**: `app/domain/dateutil/` — KST/UTC 변환 유틸리티
- **GraphQL + REST 공존**: `app/api/v1/graphql.py` — Strawberry와 FastAPI 통합

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">

**[⬆ Back to Top](#top)**


</div>
