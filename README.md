<div align="center">

<a id="top"></a>

# ⏱️ Hipster Timer Backend

**All-in-one productivity backend API for schedules, timers, and todos**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![GraphQL](https://img.shields.io/badge/GraphQL-Strawberry-E10098?style=flat-square&logo=graphql&logoColor=white)](https://strawberry.rocks)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supported-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Docs](https://img.shields.io/badge/Docs-Online-009688?style=flat-square&logo=readme&logoColor=white)](https://onprem-hipster-timer.github.io/backend/)

[Features](#features) •
[Quick Start](#quick-start) •
[API Reference](#api-reference) •
[Architecture](#architecture) •
[Testing](#testing) •
[Configuration](#configuration) •
[For Developers](#for-developers)

**📚 [Official Documentation](https://onprem-hipster-timer.github.io/backend/)**

**🌐 [한국어](README.ko.md)**

</div>

---

<!-- docs:start -->

<a id="overview"></a>

## 📖 Overview

**Hipster Timer Backend** is an all-in-one backend API for personal productivity management. It provides schedule management, pomodoro-style timers, hierarchical todo lists, and a flexible tag system through a unified API.

> 💡 **Note**: This project is designed for production use, backed by 700+ tests.

### Why Hipster Timer?

- 🔄 **Recurring Schedules**: Full iCalendar RRULE support — exception dates, virtual instance expansion included
- ⏰ **Timer Sessions**: Time tracking linked to schedules for measuring actual work time
- 🌳 **Hierarchical Todos**: Tree structure for complex projects — cycle detection, automatic ancestor inclusion
- 🏷️ **Unified Tag System**: Connect and filter schedules, timers, and todos with tags
- 🌏 **Timezone Support**: KST ↔ UTC conversion with various timezone formats
- 📡 **Dual API**: Use REST or GraphQL based on your preference
- 👥 **Friends**: Request/accept workflow for user friendships — integrates with Visibility for resource sharing
- 🔒 **Visibility**: Fine-grained sharing for Schedule, Timer, Todo, Meeting — PRIVATE to PUBLIC, selected friends, allowed emails
- 📅 **Meeting**: Poll for common availability — participants submit slots, API returns overlapping times

---

<a id="features"></a>

## ✨ Features

### 📅 Schedule

| Feature | Description |
|---------|-------------|
| **CRUD** | Create, read, update, delete schedules |
| **Recurrence** | RRULE format (`FREQ=DAILY`, `FREQ=WEEKLY;BYDAY=MO,WE,FR`) |
| **Virtual Instances** | Auto-expand recurring schedules on date range queries |
| **Exceptions** | Modify or skip specific occurrences |
| **Tag Filtering** | Filter by tag IDs or group IDs with AND conditions |
| **Timezone** | Support for `Asia/Seoul`, `+09:00`, and more |

### ⏱️ Timer

| Feature | Description |
|---------|-------------|
| **State Management** | `running` → `paused` → `completed` |
| **Time Tracking** | Measure elapsed time against allocated duration |
| **Pause/Resume** | Stop and continue sessions |
| **Tag Inheritance** | Optionally inherit tags from parent Schedule |

### ✅ Todo

| Feature | Description |
|---------|-------------|
| **Tree Structure** | Unlimited depth parent-child relationships |
| **Deadlines** | Auto-create Schedule when deadline is set |
| **Integrity Checks** | Prevent cycles, self-references, group mismatches |
| **Ancestor Inclusion** | Auto-include ancestors when filtering |
| **Stats API** | Aggregate todo counts by tag |

### 🏷️ Tag System

| Feature | Description |
|---------|-------------|
| **Group-based** | Organize tags logically with TagGroups |
| **Custom Colors** | `#RRGGBB` format color support |
| **Uniqueness** | Prevent duplicate tag names within a group |
| **Auto Cleanup** | Delete empty groups when last tag is removed |

### 🗓️ Holiday

| Feature | Description |
|---------|-------------|
| **API Integration** | Korea Astronomy and Space Science Institute public API |
| **Background Sync** | Auto-refresh holiday data on app startup |

### 👥 Friend

| Feature | Description |
|---------|-------------|
| **Request/Accept/Reject** | Workflow to create friendships via request and accept/reject |
| **Bidirectional Uniqueness** | One Friendship per (A,B) pair; (B,A) prevented |
| **Block** | Block requester or addressee via blocked status |
| **List APIs** | Friends list, received/sent request lists |

### 📅 Meeting

| Feature | Description |
|---------|-------------|
| **Create Poll** | Set date range, available weekdays, time range, slot duration |
| **Participants** | Join via share link, set display name |
| **Availability** | Each participant selects time slots |
| **Common Slots** | API returns overlapping slots and counts per slot |
| **Access** | public / allowed_emails / private |

### 🔒 Visibility

| Feature | Description |
|---------|-------------|
| **Per-Resource** | Applied to Schedule, Timer, Todo, Meeting |
| **Levels** | PRIVATE, FRIENDS, SELECTED_FRIENDS, ALLOWED_EMAILS, PUBLIC |
| **AllowList** | Allowed friends when level is SELECTED_FRIENDS |
| **AllowEmail** | Allowed emails/domains when level is ALLOWED_EMAILS |

---

<a id="quick-start"></a>

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Installation

```bash
# Clone repository
git clone https://github.com/your-username/hipster-timer-backend.git
cd hipster-timer-backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# Install dependencies (production)
pip install -r requirements.txt

# Install dependencies (development - includes test tools)
pip install -r requirements-dev.txt

# Set environment variables (optional)
cp .env.example .env
```

### Run

```bash
# Start development server
uvicorn app.main:app --port 2614 --reload

# Or run with Docker
docker compose up
```

Once the server starts:
- 📖 REST API: http://localhost:2614/docs (Swagger UI)
- 🔮 GraphQL: http://localhost:2614/v1/graphql (Apollo Sandbox)

---

<a id="api-reference"></a>

## 📚 API Reference

### REST API Endpoints

All endpoints use the `/v1` prefix. For the complete API spec (Schedules, Timers, Todos, Tags, Holidays, Friends, Meetings), see the official documentation.

> 📖 **REST API Reference**: [https://onprem-hipster-timer.github.io/backend/api/rest-api](https://onprem-hipster-timer.github.io/backend/api/rest-api)

Detailed guides for each domain:
- [Schedule Guide](https://onprem-hipster-timer.github.io/backend/guides/schedule/)
- [Timer Guide](https://onprem-hipster-timer.github.io/backend/guides/timer/)
- [Todo Guide](https://onprem-hipster-timer.github.io/backend/guides/todo/)
- [Friend Guide](https://onprem-hipster-timer.github.io/backend/guides/friend/)
- [Visibility Guide](https://onprem-hipster-timer.github.io/backend/guides/visibility/)
- [Meeting Guide](https://onprem-hipster-timer.github.io/backend/guides/meeting/)

### GraphQL API

Explore the schema at `/v1/graphql` endpoint via Apollo Sandbox.

---

<a id="architecture"></a>

## 🏗️ Architecture

### Design Philosophy

This project follows **Layered Architecture**:

- **Router Layer** (`api/`): HTTP request handling, input validation
- **Service Layer** (`domain/*/service.py`): Business logic encapsulation
- **Domain Layer** (`domain/*/schema/`): DTOs, type definitions
- **Data Layer** (`models/`, `crud/`): Persistence handling

Each layer has clear responsibilities, with dependencies always pointing inward (toward Domain). This minimizes the impact of business logic changes and simplifies testing.

### Project Structure

```
hipster-timer-backend/
├── app/
│   ├── api/
│   │   └── v1/                    # API routers
│   │       ├── schedules.py       # Schedule REST API
│   │       ├── timers.py          # Timer REST API
│   │       ├── timers_ws.py       # Timer WebSocket API
│   │       ├── todos.py           # Todo REST API
│   │       ├── tags.py            # Tag REST API
│   │       ├── holidays.py        # Holiday REST API
│   │       ├── friends.py         # Friend REST API
│   │       ├── meetings.py        # Meeting REST API
│   │       └── graphql.py         # GraphQL API
│   ├── core/                      # Core configuration
│   │   ├── config.py              # Environment settings
│   │   ├── logging.py             # Logging setup
│   │   └── error_handlers.py      # Exception handling
│   ├── crud/                      # CRUD utilities
│   ├── db/                        # Database session
│   ├── domain/                    # Domain logic (DDD)
│   │   ├── schedule/
│   │   │   ├── service.py         # Business logic
│   │   │   ├── schema/            # DTOs, Types
│   │   │   └── exceptions.py      # Domain exceptions
│   │   ├── timer/
│   │   │   ├── service.py         # Business logic
│   │   │   ├── ws_handler.py      # WebSocket handler
│   │   │   └── schema/
│   │   │       ├── dto.py         # REST DTOs
│   │   │       └── ws.py          # WebSocket schemas
│   │   ├── todo/
│   │   ├── tag/
│   │   ├── holiday/
│   │   ├── friend/                # Friends (service, schema, exceptions)
│   │   ├── meeting/               # Meeting polls (service, schema)
│   │   ├── visibility/            # Resource visibility (service, schema)
│   │   └── dateutil/              # Date/timezone utilities
│   ├── models/                    # SQLModel entities
│   │   ├── schedule.py
│   │   ├── timer.py
│   │   ├── todo.py
│   │   └── tag.py
│   ├── middleware/                # Middleware
│   ├── websocket/                 # WebSocket infrastructure (shared)
│   │   ├── base.py                # Common message schemas
│   │   ├── manager.py             # Connection management
│   │   └── auth.py                # WebSocket authentication
│   └── main.py                    # App entrypoint
├── alembic/                       # DB migrations
├── tests/                         # Tests
│   ├── domain/                    # Unit tests
│   ├── test_*_e2e.py              # E2E tests
│   └── test_*_integration.py      # Integration tests
├── requirements.in               # Direct production dependencies
├── requirements.txt              # Full production deps (auto-generated)
├── requirements-dev.in           # Direct dev dependencies
├── requirements-dev.txt          # Full dev deps (auto-generated)
├── Dockerfile
├── compose.yaml
└── README.md
```

### Data Model

```mermaid
erDiagram
    %% ---------------------------------------------------------
    %% 1. Core Domains (Schedule & Todo)
    %% ---------------------------------------------------------
    SCHEDULE {
        string title
        datetime start_time
        datetime end_time
        string recurrence_rule
        string state
    }

    TODO {
        string title
        datetime deadline
        string status
        boolean is_finished
    }

    SCHEDULE_EXCEPTION {
        datetime exception_date
        string title
        datetime start_time
    }

    %% ---------------------------------------------------------
    %% 2. Time Tracking
    %% ---------------------------------------------------------
    TIMER_SESSION {
        int allocated_duration
        int elapsed_time
        string status
        datetime started_at
        datetime ended_at
    }

    %% ---------------------------------------------------------
    %% 3. Categorization
    %% ---------------------------------------------------------
    TAG_GROUP {
        string name
        string color
        json goal_ratios
    }

    TAG {
        string name
        string color
        string description
    }

    %% ---------------------------------------------------------
    %% 4. Social & System
    %% ---------------------------------------------------------
    FRIENDSHIP {
        id requester_id
        id addressee_id
        string status
    }

    RESOURCE_VISIBILITY {
        string resource_type
        string level
        string owner_id
    }

    %% ---------------------------------------------------------
    %% 5. Meeting (Meeting Poll)
    %% ---------------------------------------------------------
    MEETING {
        string title
        date start_date
        date end_date
        string access_level
    }

    MEETING_PARTICIPANT {
        string display_name
        uuid meeting_id
    }

    MEETING_TIME_SLOT {
        date slot_date
        string start_time
        string end_time
    }

    %% ---------------------------------------------------------
    %% Relationships
    %% ---------------------------------------------------------
    
    %% Categorization Relations
    TAG_GROUP ||--|{ TAG : "contains"
    TAG }o--o{ SCHEDULE : "labels"
    TAG }o--o{ TODO : "labels"
    TAG }o--o{ TIMER_SESSION : "labels"

    %% Core Relations
    SCHEDULE ||--o{ SCHEDULE_EXCEPTION : "has"
    TODO |o--o{ SCHEDULE : "generates"
    TODO |o--o{ TODO : "sub-task of"

    %% Timer Relations
    SCHEDULE ||--o{ TIMER_SESSION : "tracked by"
    TODO ||--o{ TIMER_SESSION : "tracked by"

    %% Social & Visibility
    RESOURCE_VISIBILITY ||--o{ VISIBILITY_ALLOW_LIST : "permits"

    %% Meeting
    MEETING ||--o{ MEETING_PARTICIPANT : "has"
    MEETING_PARTICIPANT ||--o{ MEETING_TIME_SLOT : "selects"
```

### Tech Stack

| Category | Technology |
|----------|------------|
| **Framework** | FastAPI 0.120 |
| **ORM** | SQLModel 0.0.29 + SQLAlchemy 2.0 |
| **GraphQL** | Strawberry 0.288 |
| **Database** | SQLite (dev), PostgreSQL compatible |
| **Migration** | Alembic |
| **Validation** | Pydantic 2.12 |
| **Testing** | pytest, pytest-asyncio |
| **Container** | Docker, Docker Compose |

---

<a id="testing"></a>

## 🧪 Testing

This project validates core logic with **401 tests**. It covers various real-world scenarios including recurrence exception handling, timezone edge cases, and tree structure integrity.

```bash
# Run all tests
pytest

# Run E2E tests only
pytest -m e2e

# Run integration tests only
pytest -m integration

# Run specific domain tests
pytest tests/domain/schedule/

# Generate coverage report
pytest --cov=app --cov-report=html
```

### PostgreSQL Testing

By default, tests run on SQLite in-memory database. To test with PostgreSQL:

```bash
# 1. Start PostgreSQL container
docker compose -f docker-compose.test.yaml up -d

# 2. Wait for PostgreSQL to be ready
docker compose -f docker-compose.test.yaml ps

# 3. Run tests with PostgreSQL
# Windows PowerShell
$env:TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"
pytest

# Linux/macOS
TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb" pytest

# 4. Stop and clean up
docker compose -f docker-compose.test.yaml down -v
```

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `TEST_DATABASE_URL` | Test database connection string | SQLite in-memory |

### Python Version Compatibility Testing

> **Detailed Guide**: [PYTHON_VERSION_TEST_GUIDE.md](PYTHON_VERSION_TEST_GUIDE.md)

Test across multiple Python versions using Docker:

```bash
# Test specific version
docker compose -f docker-compose.python-matrix.yaml up --build python313 --abort-on-container-exit
docker compose -f docker-compose.python-matrix.yaml up --build python312 --abort-on-container-exit

# Test all versions (script)
./scripts/test-python-versions.sh      # Linux/macOS
.\scripts\test-python-versions.ps1     # Windows
```

| Python Version | Status | Service Name |
|----------------|--------|--------------|
| 3.15 | Latest | `python315` |
| 3.14 | Supported | `python314` |
| 3.13 | Default (Production) | `python313` |
| 3.12 | Supported | `python312` |
| 3.11 | Minimum Supported | `python311` |

### Test Structure

| Type | Location | Description |
|------|----------|-------------|
| **Unit** | `tests/domain/` | Individual service logic, edge case validation |
| **Integration** | `tests/test_*_integration.py` | DB integration, transaction rollback tests |
| **E2E** | `tests/test_*_e2e.py` | Full HTTP API flow tests |

### Coverage Report

The table below is a representative sample of the coverage report. Additional domain modules such as `app/api/v1/friends.py`, `app/api/v1/meetings.py`, `app/domain/friend/`, `app/domain/meeting/`, and `app/domain/visibility/` are also covered. Run `pytest --cov=app --cov-report=term-missing` for the full output.

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

Configure via `.env` file or environment variables.

#### Environment Mode

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |

> ⚠️ **Production Mode**: When `ENVIRONMENT=production`, the following settings are automatically applied:
> - `DEBUG` → `False`
> - `OPENAPI_URL` → `""` (disabled)
> - `DOCS_URL` → `""` (disabled)
> - `REDOC_URL` → `""` (disabled)
> - `GRAPHQL_ENABLE_PLAYGROUND` → `False`
> - `GRAPHQL_ENABLE_INTROSPECTION` → `False`

**Quick Setup:**

```bash
# Development (default)
ENVIRONMENT=development

# Production
ENVIRONMENT=production
```

#### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCS_ENABLED` | Master switch for all API docs (Swagger, ReDoc, GraphQL Sandbox) | `True` |
| `DEBUG` | Enable debug mode | `True` |
| `OPENAPI_URL` | OpenAPI schema URL (empty string to disable) | `/openapi.json` |
| `DOCS_URL` | Swagger UI URL (empty string to disable) | `/docs` |
| `REDOC_URL` | ReDoc URL (empty string to disable) | `/redoc` |
| `LOG_LEVEL` | Log level | `INFO` |
| `HOLIDAY_API_SERVICE_KEY` | Korea Public Data Portal API key | - |
| `GRAPHQL_ENABLE_PLAYGROUND` | Enable GraphQL Sandbox | `True` |
| `GRAPHQL_ENABLE_INTROSPECTION` | Allow GraphQL introspection | `True` |

**Disable all docs at once:**

```bash
# One command to disable Swagger, ReDoc, OpenAPI schema, GraphQL Sandbox
DOCS_ENABLED=false
```

#### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | DB connection string | `sqlite:///./schedule.db` |
| `POOL_SIZE` | Connection pool size | `5` |
| `MAX_OVERFLOW` | Max overflow connections | `10` |
| `DB_POOL_PRE_PING` | Validate connections before use | `True` |
| `DB_POOL_RECYCLE` | Connection recycle time (seconds) | `3600` |

**Database URL Examples:**

```bash
# SQLite (development)
DATABASE_URL=sqlite:///./schedule.db

# PostgreSQL (production)
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

#### Authentication (OIDC)

> 📖 **Detailed Guide**: [Authentication Guide](docs/guides/auth.md)

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_ENABLED` | Enable OIDC authentication | `True` |
| `OIDC_ISSUER_URL` | OIDC Provider issuer URL | - |
| `OIDC_AUDIENCE` | Client ID for token validation | - |
| `OIDC_DISCOVERY_URL` | Custom discovery endpoint | Auto-generated |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS cache TTL | `3600` |

**Quick Setup:**

```bash
# Development (disable auth)
OIDC_ENABLED=false

# Production
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm
OIDC_AUDIENCE=my-frontend-app
```

#### Rate Limiting

> 📖 **Detailed Guide**: [Rate Limiting Guide](https://onprem-hipster-timer.github.io/backend/development/rate-limit/)

**HTTP Rate Limiting:**

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `True` |
| `RATE_LIMIT_DEFAULT_WINDOW` | Default window size (seconds) | `60` |
| `RATE_LIMIT_DEFAULT_REQUESTS` | Default max requests per window | `60` |

**WebSocket Rate Limiting:**

| Variable | Description | Default |
|----------|-------------|---------|
| `WS_RATE_LIMIT_ENABLED` | Enable WebSocket rate limiting | `True` |
| `WS_CONNECT_WINDOW` | Connection limit window (seconds) | `60` |
| `WS_CONNECT_MAX` | Max connections per window | `10` |
| `WS_MESSAGE_WINDOW` | Message limit window (seconds) | `60` |
| `WS_MESSAGE_MAX` | Max messages per window | `120` |

**Quick Setup:**

```bash
# Development (disable rate limit)
RATE_LIMIT_ENABLED=false
WS_RATE_LIMIT_ENABLED=false

# Production (default settings)
RATE_LIMIT_ENABLED=true
WS_RATE_LIMIT_ENABLED=true
```

#### Proxy Settings (Cloudflare / Trusted Proxy)

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXY_FORCE` | Enforce proxy usage (block direct access) | `False` |
| `CF_ENABLED` | Enable Cloudflare proxy mode | `False` |
| `CF_IP_CACHE_TTL` | Cloudflare IP list cache TTL (seconds) | `86400` |
| `TRUSTED_PROXY_IPS` | Trusted proxy IPs (comma-separated, CIDR supported) | `""` |
| `ORIGIN_VERIFY_HEADER` | Custom header name for origin verification (optional) | `""` |
| `ORIGIN_VERIFY_SECRET` | Secret value for origin verification header | `""` |

> ⚠️ **Security Warning**: When running behind a proxy, incorrect configuration can allow attackers to spoof client IPs and bypass rate limiting. Always configure proxy settings correctly for your environment.
>
> ⚠️ **PROXY_FORCE Warning**: `PROXY_FORCE=true` will **block** requests where `request.client.host` is not a Cloudflare IP (when `CF_ENABLED=true`) or not in `TRUSTED_PROXY_IPS`. This is the key security check - X-Forwarded-For headers are only trusted when the direct connection comes from a known proxy.

**How Proxy Detection Works:**

The application checks `request.client.host` (the IP that directly connected to the server):
- If it's a Cloudflare IP (`CF_ENABLED=true`) → Trust `CF-Connecting-IP` header
- If it's in `TRUSTED_PROXY_IPS` → Trust `X-Forwarded-For` header
- Otherwise → Use the direct IP (ignore headers to prevent spoofing)

**Quick Setup:**

```bash
# Cloudflare direct connection
CF_ENABLED=true
PROXY_FORCE=true

# Cloudflare + Load Balancer (LB subnet must be trusted)
CF_ENABLED=true
PROXY_FORCE=true
TRUSTED_PROXY_IPS=10.0.0.0/8

# Cloudflare + Load Balancer with extra security (recommended)
CF_ENABLED=true
PROXY_FORCE=true
TRUSTED_PROXY_IPS=10.0.0.0/8
ORIGIN_VERIFY_HEADER=X-Origin-Verify
ORIGIN_VERIFY_SECRET=your-secret-key-here

# Nginx / HAProxy / Other reverse proxy
CF_ENABLED=false
PROXY_FORCE=true
TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.1
ORIGIN_VERIFY_HEADER=X-Origin-Verify
ORIGIN_VERIFY_SECRET=your-secret-key-here

# Direct connection (development)
# Use defaults - no configuration needed
```

**Load Balancer Environment:**

When running behind a load balancer (e.g., AWS ALB, managed container services), `request.client.host` will be the load balancer's internal IP, not Cloudflare's IP. You must add the LB subnet to `TRUSTED_PROXY_IPS`:

```bash
# Example: ALB in 10.0.0.0/8 subnet
CF_ENABLED=true
TRUSTED_PROXY_IPS=10.0.0.0/8
```

**Origin Verify Header (Optional Extra Security):**

For additional security, you can configure your proxy to add a secret header that the application will verify. This works with any proxy (Cloudflare, Nginx, HAProxy, etc.):

**Cloudflare Transform Rules:**
1. Go to **Rules** > **Transform Rules** > **Modify Request Header**
2. Add header: `X-Origin-Verify` = `your-secret-key-here`

**Nginx:**
```nginx
proxy_set_header X-Origin-Verify "your-secret-key-here";
```

**Environment Variables:**
```bash
ORIGIN_VERIFY_HEADER=X-Origin-Verify
ORIGIN_VERIFY_SECRET=your-secret-key-here
```

This ensures that requests without the secret header will be rejected, even if an attacker somehow reaches your server directly.
#### CORS (Cross-Origin Resource Sharing)

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ALLOWED_ORIGINS` | Allowed origins (comma-separated) | Development defaults |
| `CORS_ALLOW_CREDENTIALS` | Allow credentials (cookies, etc.) | `False` |
| `CORS_ALLOW_METHODS` | Allowed HTTP methods (comma-separated) | `*` |
| `CORS_ALLOW_HEADERS` | Allowed headers (comma-separated) | `*` |

> ⚠️ **Note**: `CORS_ALLOWED_ORIGINS="*"` and `CORS_ALLOW_CREDENTIALS=true` cannot be used together.
> To allow credentials, you must specify explicit origins.

> ⚠️ **WebSocket Important**: WebSocket connections require their protocol to be in `CORS_ALLOWED_ORIGINS`:
> - For `ws://` (unencrypted): Add `ws://localhost:8000,ws://127.0.0.1:8000`
> - For `wss://` (encrypted): Add `wss://your-domain.com`

**Quick Setup:**

```bash
# Development (HTTP + WebSocket)
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000,ws://localhost:8000,ws://127.0.0.1:8000
CORS_ALLOW_CREDENTIALS=false

# Production (HTTPS + Secure WebSocket)
CORS_ALLOWED_ORIGINS=https://example.com,https://app.example.com,wss://api.example.com
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=GET,POST,PUT,PATCH,DELETE,OPTIONS
CORS_ALLOW_HEADERS=Authorization,Content-Type
```

### Database Migration

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 🐳 Docker

### Using Pre-built Image (Recommended)

Pull and run the pre-built image from GitHub Container Registry:

```bash
# Pull the latest image
docker pull ghcr.io/onprem-hipster-timer/backend:latest

# Or pull a specific version
docker pull ghcr.io/onprem-hipster-timer/backend:v2026.01.13-f81a7c0

# Run the container
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=sqlite:///./data/schedule.db \
  -e OIDC_ENABLED=false \
  -v hipster-timer-data:/app/data \
  ghcr.io/onprem-hipster-timer/backend:latest
```

**With PostgreSQL:**

```bash
# Run with PostgreSQL
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=postgresql://user:password@host:5432/dbname \
  -e OIDC_ENABLED=false \
  -e ENVIRONMENT=production \
  ghcr.io/onprem-hipster-timer/backend:latest
```

**With Docker Compose:**

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

### Building from Source

```bash
# Build and run
docker compose up --build

# Run in background
docker compose up -d

# View logs
docker compose logs -f
```

**Exposed Port:** `2614`

---

<a id="for-developers"></a>

## 🛠️ For Developers

A guide for those who want to fork this codebase or use it as a learning reference.

### Dependency Management (pip-tools)

This project uses [pip-tools](https://pip-tools.readthedocs.io/) to manage dependencies. This separates direct dependencies (what you explicitly need) from transitive dependencies (what your dependencies need).

#### File Structure

| File | Purpose |
|------|---------|
| `requirements.in` | Direct production dependencies (human-edited) |
| `requirements.txt` | Full dependency tree with pinned versions (auto-generated) |
| `requirements-dev.in` | Direct development/test dependencies (human-edited) |
| `requirements-dev.txt` | Full dev dependency tree (auto-generated) |

#### Common Commands

```bash
# Install pip-tools (in your venv)
pip install pip-tools

# Compile dependencies (after editing .in files)
pip-compile requirements.in
pip-compile requirements-dev.in

# Upgrade all dependencies to latest versions
pip-compile --upgrade requirements.in
pip-compile --upgrade requirements-dev.in

# Upgrade a specific package
pip-compile --upgrade-package fastapi requirements.in

# Sync your environment with requirements
pip-sync requirements-dev.txt  # Development
pip-sync requirements.txt      # Production
```

#### Adding New Dependencies

1. Add the package name to `requirements.in` (production) or `requirements-dev.in` (dev/test)
2. Run `pip-compile` to regenerate the `.txt` file
3. Run `pip-sync` to install

```bash
# Example: Add httpx
echo "httpx" >> requirements.in
pip-compile requirements.in
pip-sync requirements.txt
```

#### Why pip-tools?

- **Reproducible builds**: Pinned versions ensure consistent environments
- **Clean separation**: Direct vs transitive dependencies are clearly separated
- **Easy upgrades**: `--upgrade` flag updates all dependencies safely
- **Audit trail**: Generated `.txt` files show where each dependency comes from

### Customization Points

| Purpose | Location | Description |
|---------|----------|-------------|
| Add new domain | `app/domain/` | Extend following existing domain structure |
| Change DB | `app/db/session.py` | SQLite/PostgreSQL auto-detection, optimized pool settings |
| Add auth | `app/middleware/` | Add JWT or other auth logic in middleware layer |
| Add API version | `app/api/` | Create v2 router and mount in `main.py` |

### Notable Implementations

- **RRULE Recurrence**: `app/domain/schedule/` — Virtual instance expansion, exception handling
- **Hierarchical Data**: `app/domain/todo/` — Cycle detection, automatic ancestor inclusion
- **Timezone Handling**: `app/domain/dateutil/` — KST/UTC conversion utilities
- **GraphQL + REST Coexistence**: `app/api/v1/graphql.py` — Strawberry and FastAPI integration
- **Friends**: `app/domain/friend/` — Request/accept workflow, bidirectional uniqueness
- **Meeting Polls**: `app/domain/meeting/` — Date range, weekdays, slots, participants, common availability
- **Visibility**: `app/domain/visibility/` — AllowList/AllowEmail, per-resource level control

---

<!-- docs:end -->

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">

**[⬆ Back to Top](#top)**

</div>
