# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

---

## [v2026.03.05-6194559] - 2026-03-05

### Added

- **Automated versioning and release pipeline**: Merging to `main` now automatically generates a CalVer tag (`v{YYYY}.{MM}.{DD}-{SHORT_HASH}`), builds and pushes the Docker image, updates this CHANGELOG, and creates a GitHub Release.
- **License and liability notice in `/health`**: The health check response now includes AGPL-3.0 license notice and infrastructure liability disclaimer.

### Changed

- **Production information hardening**: `/health` no longer exposes `version` or `environment` fields in production environments.

---

## [v2026.03.04-d027c48] - 2026-03-04

### Changed

- **Meeting result availability grid structure** (`d027c48`): Changed `availability_grid` response from a nested map (`Map<date, Map<time, count>>`) to a typed array grouped by date (`List[AvailabilityDateGroup]`). Improves type safety and eliminates `additionalProperties` in OpenAPI schema.
  - **Breaking change**: Clients consuming `GET /v1/meetings/{id}/result` must update their parsing logic.
  - Before: `{ "2024-02-01": { "09:00": 1 } }`
  - After: `[{ "date": "2024-02-01", "slots": [{ "time": "09:00", "count": 1 }] }]`

---

## [v2026.03.03-5609ccd] - 2026-03-03

### Removed

- **`TagGroup.is_todo_group` field** (`5609ccd`): Removed unused boolean flag from `TagGroup` model, DTOs, and database schema. The field had no business logic enforcing it and was only referenced in a one-time migration script.
  - **Breaking change**: `is_todo_group` field is no longer present in `TagGroup` API responses.

---

## [v2026.02.23-e582adc] - 2026-02-23

### Fixed

- **TimerService elapsed time calculation** (`e582adc`): Fixed incorrect accumulation of elapsed time during pause/resume cycles. Refactored to use a dedicated method and added tests for pause/resume cycles.
- **Upgrade notice**: Patches before `2026.02.23-e582adc` contain the above bug. **Upgrade to `2026.02.23-e582adc` or later is recommended.**

---

## [v2026.01.30] - 2026-01-30

### Added

#### Core Features
- **Schedule Management**
  - CRUD operations for schedules
  - RRULE-based recurring schedule support
  - Exception date handling for recurring schedules
  - Virtual instance expansion for date range queries
  - Timezone support (KST, UTC, custom offsets)

- **Timer Sessions**
  - Timer creation linked to Schedule or Todo
  - Pause/Resume/Stop state management
  - Elapsed time tracking
  - WebSocket real-time synchronization
  - Pause history tracking

- **Todo Management**
  - Hierarchical tree structure (unlimited depth)
  - Circular reference prevention
  - Ancestor inclusion in filtered queries
  - Automatic Schedule creation from deadline
  - Statistics API (count by tag)

- **Tag System**
  - TagGroup for logical categorization
  - Custom colors (#RRGGBB format)
  - Tag assignment to Schedule, Timer, Todo
  - Unique tag names within group

- **Holiday Integration**
  - Korea Astronomy and Space Science Institute API integration
  - Background synchronization on startup

#### Social Features
- **Friendship**
  - Request/Accept/Reject workflow
  - Bidirectional unique constraint
  - Block functionality
  - Friend list and request list APIs

- **Visibility Control**
  - 5-level visibility (PRIVATE, FRIENDS, SELECTED_FRIENDS, ALLOWED_EMAILS, PUBLIC)
  - Resource-specific settings (Schedule, Timer, Todo, Meeting)
  - AllowList for selected friends
  - AllowEmail for email/domain-based access

- **Meeting (Schedule Coordination)**
  - Meeting creation with date range and time slots
  - Participant registration via shared link
  - Available time slot selection
  - Common availability query

#### API
- REST API with OpenAPI/Swagger documentation
- GraphQL API with Strawberry (Apollo Sandbox)
- WebSocket API for real-time timer sync

#### Authentication & Security
- OIDC authentication support
- JWT token validation with JWKS caching
- Rate limiting (HTTP and WebSocket)
- Cloudflare and trusted proxy support
- CORS configuration

#### Infrastructure
- SQLite (development) and PostgreSQL (production) support
- Alembic database migrations
- Docker and Docker Compose support
- Multi-platform builds (amd64, arm64)
- GitHub Actions CI/CD
- MkDocs documentation site

### Database Migrations

| Migration | Description |
|-----------|-------------|
| `ee97307fb363` | Initial schema (Schedule, Timer, Todo, Tag) |
| `d8eaba7f881e` | Add tag_group_id to Schedule |
| `341423c03b1a` | Make tag_group_id required for Todos |
| `9b9bdc029ff3` | Add Todo model, update Schedule model |
| `1f4bc4f1de04` | Change Todo parent FK to SET NULL |
| `cf7d6e2ef7a7` | Add owner_id to all models |
| `62a5cb5aae21` | Add todo_id to Timer, make schedule optional |
| `a1b2c3d4e5f6` | Add Friendship and Visibility tables |
| `b2c3d4e5f6a7` | Add Friendship bidirectional unique constraint |
| `c3d4e5f6a7b8` | Add pause history to Timer |
| `d4e5f6a7b8c9` | Change Timer status to UPPERCASE |
| `e5f6a7b8c9d0` | Add VisibilityAllowEmail and Meeting tables |

---

## Version History Format

### Types of Changes

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security vulnerability fixes

---

[Unreleased]: https://github.com/onprem-hipster-timer/backend/compare/v2026.02.23-e582adc...HEAD
[v2026.02.23-e582adc]: https://github.com/onprem-hipster-timer/backend/compare/v2026.01.30...v2026.02.23-e582adc
[v2026.01.30]: https://github.com/onprem-hipster-timer/backend/releases/tag/v2026.01.30
