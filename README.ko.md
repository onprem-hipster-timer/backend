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

### Test Structure

| 테스트 유형 | 위치 | 설명 |
|-------------|------|------|
| **Unit** | `tests/domain/` | 개별 서비스 로직, 엣지 케이스 검증 |
| **Integration** | `tests/test_*_integration.py` | DB 연동, 트랜잭션 롤백 테스트 |
| **E2E** | `tests/test_*_e2e.py` | HTTP API 전체 흐름 테스트 |

---

## ⚙️ Configuration

### Environment Variables

`.env` 파일 또는 환경 변수로 설정합니다.

#### 기본 설정

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | 디버그 모드 활성화 | `False` |
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
