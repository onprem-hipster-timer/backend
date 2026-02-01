# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

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

[Unreleased]: https://github.com/onprem-hipster-timer/backend/compare/v2026.01.30...HEAD
[v2026.01.30]: https://github.com/onprem-hipster-timer/backend/releases/tag/v2026.01.30
