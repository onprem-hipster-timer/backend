# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Timer expiry**: a RUNNING timer expires at `started_at + (allocated_duration - elapsed_time)`. Reads (`GET /v1/timers`, `/v1/timers/active`, `/v1/timers/{id}` and timers embedded in schedule and Todo responses) show an expired timer as `PAUSED` with `elapsed_time = allocated_duration`, `paused_at` at the expiry instant and an `expire` entry in `pause_history`, without writing the row. The next command on the timer (`pause`, `stop`, `cancel`, a successful `PATCH`) and changes that reach the timer from its Todo or schedule (applying a Todo status, deleting the Todo or schedule with `linked_timer_policy=unlink`) store that state first and send `timer.updated` with `action: expire` before their own event; no event is sent at the expiry instant. A `resume` that returns 400 and a `PATCH` that returns 422 store nothing and send no event. `pause` on an expired timer returns 200, `resume` returns 400 until `allocated_duration` is extended, and `stop`/`cancel` finish with `elapsed_time = allocated_duration`. Status filters still match the stored status, so an expired timer not yet stored is matched by `status=RUNNING`.
- **Extending a timer**: `PATCH /v1/timers/{timer_id}` accepts `allocated_duration`. It must be greater than the time used so far (the stored `elapsed_time` plus the running segment while the timer runs), otherwise 422 (`AllocatedDurationTooShortError`). An expired timer can be resumed after it is extended.
- **Maximum `allocated_duration`**: `POST /v1/timers` and `PATCH /v1/timers/{timer_id}` reject an `allocated_duration` above 2147483647 with a 422 validation error.

### Changed

- **`elapsed_time` is capped at `allocated_duration`**: `pause`, `stop` and completing a timer through its Todo no longer add running time beyond the allocated duration.
- **Client rule for timer state**: the realtime and timer guides now tell clients to apply a timer value only when its `updated_at` is newer than the held one; on an equal `updated_at` the value with the longer `pause_history` wins and equal lengths keep the held value, except that the response to the client's own command is applied (a `PATCH` such as extending `allocated_duration` may add no `pause_history` entry). A timer seen as COMPLETED or CANCELLED is never made active again by a later value.
- **Active timers over their allocation**: a migration raises `allocated_duration` to `elapsed_time` for RUNNING and PAUSED timers whose `elapsed_time` exceeds it. COMPLETED and CANCELLED timers keep their values, so finished timers can still have `elapsed_time` greater than `allocated_duration`. The migration's downgrade does not restore the previous values.

---

## [v2026.11.08-099ab9f] - 2026-11-08

### Fixed

- **Datetime columns created as `timestamptz`**: databases bootstrapped with `create_all` while model datetime fields were plain `datetime` got `TIMESTAMP WITH TIME ZONE` columns, so PostgreSQL returned timezone-aware values and arithmetic with naive UTC datetimes failed with 500 (`can't subtract offset-naive and offset-aware datetimes`) on timer pause, stop and cancel and in schedule duration calculations. A migration converts these columns to `TIMESTAMP WITHOUT TIME ZONE`, keeping the same UTC instant; columns that are already naive are left as they are.
- **Alembic accepts `%` in `DATABASE_URL`**: percent-encoded characters in the URL (for example `options=-c%20timezone=...` or an encoded password) no longer break `alembic` with a configparser interpolation error.
- **Migration-only changes are deployed**: a `main` push that changes only `alembic/`, `alembic.ini` or `scripts/docker-entrypoint.sh` now builds the image and starts a deploy. Previously the image build ran only for `app/`, `requirements.txt` and `Dockerfile` changes, so such migrations were not deployed until another change was merged.

### Changed

- **Database migrations need approval**: the Cloud Run deploy compares the commit of the running `api` image with the new image's commit. When `alembic/` or `alembic.ini` changed between them (or either commit is unknown), the `migrate` job waits for approval through the `database-migration` environment before running `app-migrate`, and `api` is updated only after it succeeds. Without changes the deploy skips the migration and updates `api` directly. The deploy stops if that environment has no required reviewers. Previously every deploy ran `app-migrate` automatically.

---

## [v2026.11.07-f65a7fe] - 2026-11-07

### Added

- **Timer cancel command**: `POST /v1/timers/{timer_id}/cancel` (RUNNING or PAUSED → CANCELLED) takes the same query parameters as `stop` and sends `timer.updated` with `action: cancel`. Cancelling a timer that is not running or paused returns 400. The running segment is not added to `elapsed_time`.

### Changed

- **Timer completion and Todo status (breaking)**: completing a timer (`stop`) sets its linked Todo to `DONE` and cancelling sets it to `CANCELLED`; a Todo that is already `DONE` or `CANCELLED` is left as is. When a Todo's status changes (`PATCH /v1/todos/{id}`, including the automatic `UNSCHEDULED`↔`SCHEDULED` change when a deadline is set or removed, and removing a projected schedule from the schedule side), its running and paused timers follow: `DONE` completes them (the running segment is added, `timer.updated` with `action: stop`), `CANCELLED` cancels them (`action: cancel`), and `UNSCHEDULED`/`SCHEDULED` leaves them running and only bumps `updated_at` (`action: update`). When completing or cancelling a timer finishes its Todo, the Todo's other running and paused timers are completed or cancelled too. `stop` and `cancel` responses with `include_todo=true` show the new Todo status. Previously timer and Todo status were independent.
- **One `update` event per timer per transaction**: when one request produces several `timer.updated` events with `action: update` for the same timer, only the last one (the latest state) is sent.

---

## [v2026.11.07-c7b2408] - 2026-11-07

### Fixed

- **CORS exposes `Date`**: responses to allowed origins send `Access-Control-Expose-Headers: Date`, so browser clients can read the server time from the `Date` header of REST responses.
- **`/v1/ws/timers` authentication failures close with `1008`**: when the token is missing or invalid, the server completes the handshake (echoing the `authorization.bearer.*` subprotocol) and then closes with `1008` and a reason. Previously it rejected the handshake with HTTP 403, which browsers report as `1006`, so clients did not know to refresh the token.
- **`/v1/ws/timers` rate-limit rejections close with `4029`**: the server completes the handshake before closing, so browsers see `4029` instead of `1006`.

---

## [v2026.11.07-acb5673] - 2026-11-07

### Added

- **`linked_timer_policy` (breaking)**: Deleting a Todo (`DELETE /v1/todos/{id}`) or a Schedule (`DELETE /v1/schedules/{id}`) that has linked timers now requires `linked_timer_policy` — `delete` (remove the timers and their visibility settings, sending `timer.deleted`) or `unlink` (clear `todo_id`/`schedule_id`; the timer stays as an independent timer, keeps running if it was running, and `timer.updated` with `action: update` is sent). There is no server default; omitting it while linked timers exist returns `422`. When deleting the last instance of a recurring series removes the series, an omitted policy means `unlink`. Projected schedules removed from the Todo side (clearing a deadline, or deleting a Todo with `linked_schedule_policy=delete`) unlink their timers' `schedule_id` without asking and send `timer.updated`; timers also linked to the deleted Todo follow its `linked_timer_policy`, with one event per timer. Deleting a tag group unlinks the timers of the Todos it deletes. Previously all of these links were set to `null` with no realtime event.

---

## [v2026.11.06-039b759] - 2026-11-06

### Added

- **Realtime timer delivery**: committed timer changes are delivered to the owner's other devices and to the friends the timer's visibility allows (`FRIENDS`/`PUBLIC`: all friends, `SELECTED_FRIENDS`: allow-listed friends; nobody else for `PRIVATE`, `ALLOWED_EMAILS` or timers without a visibility row). `REALTIME_BACKEND=inprocess` (default) delivers over this process's `/v1/ws/timers` sockets; `REALTIME_BACKEND=cloudflare` pushes to the realtime Worker (`POST REALTIME_PUSH_URL` with `Authorization: Bearer REALTIME_PUSH_SECRET`, users split into batches of 40, one retry on connection errors and 5xx, about 2 seconds per event, failures logged as `realtime_push_failed`). In production, the `cloudflare` mode fails startup without the URL or secret. See `docs/development/realtime-adapter.ko.md`.
- **Realtime message envelope**: `{id, type, from_user, timestamp, payload: {action, actor_name, timer}}` with `timer.created` (`start`), `timer.updated` (`pause`, `resume`, `stop`, `cancel`, `update`) and `timer.deleted` (`delete`, `timer: null` plus `timer_id`). Times are UTC in the same format as REST responses (`2026-11-06T10:30:00+0000`), so the same timer state has the same `updated_at` in an event and in a REST response; `elapsed_time` is the stored value.
- **OIDC discovery and JWKS**: `GET /auth/.well-known/jwks.json` serves `OIDC_JWKS` and `GET /auth/.well-known/openid-configuration` a minimal discovery document, so services outside the backend can verify Kratos JWTs. Both send `Cache-Control: public, max-age=3600`, return 404 when `OIDC_JWKS` is empty, and also answer under `/auth//.well-known/...`. Startup now fails if `OIDC_JWKS` contains private (`d`) or symmetric keys.
- **Timer REST commands**: `POST /v1/timers` (201), `PATCH /v1/timers/{timer_id}/pause`, `PATCH /v1/timers/{timer_id}/resume` and `POST /v1/timers/{timer_id}/stop`, taking the same `include_schedule`, `include_todo`, `tag_include_mode` and `timezone` query parameters as the read endpoints. Invalid transitions return 400.

### Changed

- **Timer writes commit before the response**: timer create, pause, resume, stop, update and delete commit and hand off their realtime events before the response is sent, so a read made right after the response sees the change.
- **`/v1/ws/timers` is receive-only**: on connect the server sends `{"id", "type": "connected", "from_user": null, "timestamp", "payload": {}}` and afterwards only timer events. The only client message is the text `ping`, answered with `pong`; anything else is ignored. Clients reload timers over REST after every connect and reconnect. The `timezone` query parameter is no longer read (events are always UTC), and every server message now carries an `id` and a UTC-aware `timestamp`.
- **WebSocket Playground** (development only) shows incoming messages and sends `ping`.

### Removed

- **WebSocket timer commands**: the `timer.create`, `timer.pause`, `timer.resume`, `timer.stop` and `timer.sync` messages, the `timer.sync_result` sent on connect, `error` messages, and `timer.friend_activity`, which went to every online friend regardless of the timer's visibility. Use the REST commands; friends now receive the timer events their visibility allows. `GET /ws-playground/schema` is gone as well.
- **WebSocket message rate limit** and its `WS_MESSAGE_WINDOW`/`WS_MESSAGE_MAX` settings (the connection limit stays). Remove these keys from `.env` files, where unknown keys fail settings validation; environment variables are ignored.

### Fixed

- **Timer `pause_history` timezone in REST**: the `timezone` query parameter now also converts `pause_history[].at` in REST timer responses, like the other timer timestamps.
- **Timer reads no longer write**: timer read endpoints (`GET /v1/timers`, `/v1/timers/active`, `/v1/timers/{timer_id}`, and the schedule and todo timer lists and active timer) added the running segment to `elapsed_time` on the session's object, and the request's transaction committed it. Each read inflated the stored `elapsed_time` and bumped `updated_at`, even when a friend read a shared timer, and clients that add `now - started_at` themselves counted the segment twice. Reads now return the stored `elapsed_time`; pause and stop still add the running segment.

---

## [v2026.11.04-71e4266] - 2026-11-04

### Fixed

- **Naive UTC datetime columns**: sqlmodel 0.0.48 maps plain `datetime` fields to a timezone-aware column type that rejects naive values, so every insert with `created_at` failed with 500. Table model datetime fields (`TimestampMixin` and 14 model fields) are now annotated with Pydantic `NaiveDatetime`, which keeps `TIMESTAMP WITHOUT TIME ZONE` and the existing UTC naive storage. A model test fails if any table column becomes timezone-aware again.

---

## [v2026.11.04-42359ab] - 2026-11-04

### Security

- **Social sign-up email**: the `/auth` proxy drops `traits.email` from social (OIDC) login and registration submissions, so social accounts only use the email the provider verified. Submissions whose `method` can't be read unambiguously (duplicate keys, also keys that differ only in case) are rejected with 400.

---

## [v2026.11.04-5b27507] - 2026-11-04

### Added

- **Cloud Run auto deploy**: `.github/workflows/deploy.yml` deploys every successful `main` image build to Cloud Run through Workload Identity Federation (no keys). The image is pinned by digest, the `app-migrate` job runs first, then the `api` service is updated. A manual run takes a version tag for redeploys and rollbacks. The workflow is skipped until the repository variables `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_DEPLOY_WIF_PROVIDER` and `GCP_DEPLOYER_SA` are set. Images are now also tagged `sha-<commit sha>`.

---

## [v2026.07.21-c825e27] - 2026-07-21

### Added

- **In-process Domain Event + Message Bus**: Cross-domain write propagation now flows through a session-scoped event queue (`app/shared/uow.py`) and a central handler registry with a queue-based drain loop (`app/shared/messagebus.py`) — same session/transaction, no external broker. Handlers run before response assembly so auto-created resources appear immediately; a handler failure rolls back the whole transaction. Cascade loops are stopped by per-chain `event_key` dedupe plus a `MAX_DISPATCH_DEPTH` bound. `get_db_transactional` now commits via `commit_with_events` (safety-net drain) and clears the event queue at rollback boundaries. Known limitation: the WebSocket per-message commit path does **not** yet drain events — WS-reachable code must not emit domain events until the WS transaction boundary is aligned ([#49](https://github.com/onprem-hipster-timer/backend/issues/49)). ([#54](https://github.com/onprem-hipster-timer/backend/issues/54))
- **`linked_schedule_policy` (breaking)**: Clearing a Todo's deadline (`PATCH` with `"deadline": null`) and deleting a Todo (`DELETE /v1/todos/{id}`) now require an explicit `linked_schedule_policy` **when linked schedules exist** — `delete` (remove the projected Schedule + its visibility settings) or `unlink` (detach `source_todo_id`; the Schedule survives as a regular schedule with its notes/tags/sharing intact). There is deliberately **no server default**; omitting it while a link exists returns `422`. Todos without a linked schedule may omit the parameter. ([#61](https://github.com/onprem-hipster-timer/backend/issues/61))
- **`source_todo_policy` (breaking)**: The symmetric policy for the Schedule side. Deleting a source-linked Schedule (`DELETE /v1/schedules/{id}`) and converting one to a recurring series (`PATCH` setting `recurrence_rule`) now require `source_todo_policy` — `clear_deadline` (also remove the Todo's deadline) or `keep_deadline` (keep it; only the linkage flag resets). A deadline projection cannot become a recurring series, so conversion **auto-detaches the link** before applying; the internal auto-delete path (recurring series exhausted) uses `keep_deadline` since no client can be asked. No server default; omitting it on a linked schedule returns `422`.
- **`status` is a linkage flag (breaking)**: `UNSCHEDULED`/`SCHEDULED` are derived from whether a linked schedule exists — auto-computed when omitted, and an explicit value that contradicts the actual linkage state returns `422` (no lying flags; reopen a `DONE` todo by sending the value matching its linkage). Only `DONE`/`CANCELLED` are user-owned states. A frontend migration guide was added to `docs/guides/todo.ko.md`.

### Changed

- **`source_todo_id` rejected on public Schedule writes (breaking)**: `POST /v1/schedules` and `PATCH /v1/schedules/{id}` return `422` if the payload carries `source_todo_id` (it remains present in read responses). The link lifecycle is managed exclusively by the dedicated flows (deadline projection, `create_todo_options`, `POST /v1/schedules/{id}/todo`, `linked_schedule_policy`/`source_todo_policy`). This closes two invariant holes: a client could previously attach a second Schedule to a Todo (only the first projection was moved on deadline changes, leaving stale duplicates) or detach a projection via generic PATCH (leaving the Todo `SCHEDULED` with zero linked schedules). "Exactly one projection per Todo" is now also enforced at the database level via a partial unique index on `schedule.source_todo_id` (migration `c4d7e8f1a2b3`). ([#55](https://github.com/onprem-hipster-timer/backend/issues/55))
- **Schedule→Todo back-propagation (reverse direction)**: Moving a projected Schedule (one with `source_todo_id`) now back-propagates its `start_time` to the source Todo's `deadline`, resolving the one-way-sync gap of [#44](https://github.com/onprem-hipster-timer/backend/issues/44). Guards: changes originating from the Todo side are not re-propagated (origin guard). Deleting a projected Schedule keeps the Todo and handles its deadline per the client's `source_todo_policy`, resetting the linkage flag unless the Todo is in a terminal state. `create_todo_options` / `POST /v1/schedules/{id}/todo` now flow through `ScheduleCreatedWithTodoOption` handled on the Todo side (low-level creation, so the new Todo's deadline cannot re-trigger a second Schedule). The recurring-series auto-delete path (all instances exhausted) now also emits the deletion event and cleans up visibility rows, which it previously skipped. ([#55](https://github.com/onprem-hipster-timer/backend/issues/55), [#44](https://github.com/onprem-hipster-timer/backend/issues/44))
- **Todo→Schedule sync moved to domain events, and corrected**: The inline `TodoService`→`ScheduleService` calls were replaced by `TodoDeadlineSet/Changed/Removed`, `TodoContentChanged`, `TodoTagsChanged`, and `TodoDeleted` events handled in `app/domain/schedule/event_handlers.py` (owner-invariant checked, low-level ops, no visibility copying). Field-ownership rules (`docs/development/domain-events.ko.md` §5.1) fixed several long-standing sync gaps:
  - Renaming a Todo (title/description) now updates the projected Schedule — previously never propagated.
  - Changing a deadline moves only the projection's start; a user-adjusted duration is preserved (previously forced back to 1 hour).
  - Changing a deadline when the projection is missing recreates it (previously a silent no-op).
  - `status` now reflects projection existence as a linkage flag (`SCHEDULED` ⇔ linked schedule exists; `DONE`/`CANCELLED` are never overridden) — consistent across both creation paths.
  - Exactly one linked projection per Todo is maintained. ([#55](https://github.com/onprem-hipster-timer/backend/issues/55), [#61](https://github.com/onprem-hipster-timer/backend/issues/61))

---

## [v2026.06.15-552ec57] - 2026-06-15

### Added

- **Per-request timezone for Todo responses**: The Todo endpoints (`POST`/`GET`/`PATCH /v1/todos`, `GET /v1/todos/{id}`) gained an optional `timezone` query parameter (e.g. `Asia/Seoul`, `+09:00`, `UTC`), matching the existing Schedule/Timer behavior. `TodoRead.to_timezone` converts the UTC-naive `deadline`/`created_at` (and nested schedules) to the requested timezone; when omitted, values are returned in UTC.

### Fixed

- **Holiday sync timezone crash**: The holiday sync batch failed when updating `holiday_hashes.updated_at`, because a timezone-*aware* `datetime.now(timezone.utc)` was assigned to a `TIMESTAMP WITHOUT TIME ZONE` (naive) column, raising `TypeError: can't subtract offset-naive and offset-aware datetimes` / `asyncpg.exceptions.DataError` during autoflush. `save_holidays` now stores the hash timestamp as UTC-naive. Holiday dates ingested from the KASI (천문연구원) API — whose `locdate` values carry no timezone — are now explicitly assigned KST (`Asia/Seoul`) at the receiving DTO (`HolidayItem.to_utc_naive_range`) before being normalized to UTC-naive. ([#41](https://github.com/onprem-hipster-timer/backend/issues/41))
- **Holiday insert `NotNullViolationError` on `created_at`/`updated_at`**: `HolidayModel` lost its `TimestampMixin` during an earlier model-relocation refactor, so inserts into `holidays` omitted `created_at`/`updated_at`. Because the `holidays` table is created via `create_all` (not Alembic) and existing deployments already had those columns as `NOT NULL` from when the mixin was present, new rows were rejected with `asyncpg.exceptions.NotNullViolationError` — surfaced once the #41 fix let the sync proceed to the holiday insert. `TimestampMixin` was restored on `HolidayModel`, so timestamps are populated as UTC-naive. ([#41](https://github.com/onprem-hipster-timer/backend/issues/41))
- **Todo deadline timezone (same bug class as #41)**: `TodoCreate`/`TodoUpdate.deadline` lacked the UTC-normalization validator that the Schedule/Timer DTOs already had, so a client-supplied timezone-aware `deadline` was written directly to the naive `todo.deadline` column — the same `asyncpg.DataError` class as #41 on PostgreSQL. Both DTOs now run `ensure_utc_naive` on `deadline`, converting aware datetimes to UTC-naive before storage. A timezone-handling guide was added at `docs/development/timezone.ko.md`. ([#41](https://github.com/onprem-hipster-timer/backend/issues/41))

---

## [v2026.06.15-53559c3] - 2026-06-15

### Added

- **Friend display info**: Friend list and pending-request responses now carry the counterparty's display info so a UI can show *who* a request/friend is. `FriendRead` gained `display_name`/`avatar_url`, and `PendingRequestRead` gained `requester_display_name`/`requester_avatar_url`. A new `GET /v1/users/me` returns the caller's profile and a shareable `friend_code`. Display info is sourced **only** from standard OIDC claims (`name`→`display_name`, `picture`→`avatar_url`) of each user's own validated access token via just-in-time provisioning into a new `user_profile` table — no UserInfo/Admin-API calls, so the backend stays provider-agnostic. JIT sync runs on every authenticated endpoint, so any active user is addressable even if they never open the social UI. The WebSocket `timer.friend_activity` payload also gained `display_name`. ([#20](https://github.com/onprem-hipster-timer/backend/issues/20))
- **Friend requests by code or email**: `POST /v1/friends/requests` takes **exactly one** of `{ "friend_code": "<value>" }` or `{ "email": "<value>" }` (sending both fields, neither field, `null`, or a malformed email returns `422`):
  - **friend code**: resolved against a stored CSPRNG-generated URL-safe token (`secrets.token_urlsafe(32)`) that is not derived from the OIDC `sub`. An unknown code returns `404`.
  - **email** (format-validated): matched against the stored normalized `verified_email`, populated only when the token's `email_verified` is true. To prevent account enumeration the endpoint **always returns `202 {"ok": true}`** regardless of whether the email matched, was your own, was a duplicate, or was blocked. Rate-limited tighter than other writes (20/min).
  Verified email is stored only for friend-request matching and is not returned through search, lists, or API responses. There is deliberately **no user-search/directory endpoint**. ([#20](https://github.com/onprem-hipster-timer/backend/issues/20))

### Changed

- **Friend request body**: `POST /v1/friends/requests` now accepts an explicit `{ "email" }` or `{ "friend_code" }` (exactly one, validated) instead of `{ "addressee_id": "<sub>" }` — an OIDC `sub` could never be obtained by a client. ([#20](https://github.com/onprem-hipster-timer/backend/issues/20))

### Security

- **Holiday API over HTTPS**: The default `HOLIDAY_API_BASE_URL` was changed from `http://apis.data.go.kr/...` to `https://apis.data.go.kr/...`, so Korea Astronomy and Space Science Institute (Public Data Portal) holiday lookups — which carry the `HOLIDAY_API_SERVICE_KEY` — are no longer transmitted in cleartext. **All released versions up to and including `v2026.06.12-cfa3200` ship the `http://` default.** Operators running those tags should inject the HTTPS address directly through the `HOLIDAY_API_BASE_URL` environment variable until they upgrade to a build containing this change:

  ```bash
  HOLIDAY_API_BASE_URL=https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService
  ```

---

## [v2026.06.12-cfa3200] - 2026-06-12

### Changed

- **`authlib.jose` → `joserfc` migration**: OIDC JWT verification in `app/core/auth.py` was migrated off the deprecated `authlib.jose` module (deprecated since Authlib 1.7.0, slated for removal in Authlib 2.0.0) to the standalone `joserfc` package, which Authlib already pulls in transitively. JWKS loading (`KeySet.import_key_set`), decoding + claim validation (`jwt.decode` + `JWTClaimsRegistry`), and error handling (`joserfc.errors.JoseError`) were ported with no behavioral change to token verification. Signature verification is now restricted to asymmetric algorithms (`RS256/384/512`, `ES256/384/512`), preventing the `alg` confusion / `none` attacks that Authlib's unrestricted default allowed. `authlib` was dropped from `requirements.in` (and the lockfiles) in favor of a direct `joserfc` dependency. ([#34](https://github.com/onprem-hipster-timer/backend/issues/34), [#37](https://github.com/onprem-hipster-timer/backend/pull/37))

---

## [v2026.06.09-30c31db] - 2026-06-09

### Fixed

- **Cross-platform lockfile (Windows installability)**: `uvloop` (a `uvicorn[standard]` transitive dependency with no Windows wheel) was pinned without an environment marker, so `pip install -r requirements.txt` failed on Windows with `uvloop does not support Windows`. `uvloop` is now declared directly in `requirements.in` with a `; sys_platform != 'win32'` marker, which pip-compile preserves in the lockfile and Dependabot retains across regenerations (it reads but never rewrites `requirements.in`). Linux/production installs are unchanged. Verified: fresh Windows venv install succeeds (uvloop skipped); Linux test suite still passes (824 tests).

---

## [v2026.06.09-91639bf] - 2026-06-09

### Changed

- **Strict `Content-Type` checking for JSON requests**: As part of the FastAPI dependency upgrade (0.132+, via [#29](https://github.com/onprem-hipster-timer/backend/pull/29)), requests carrying a JSON body must include a `Content-Type: application/json` header. A missing header now returns `422 Unprocessable Entity`, and an incorrect media type returns `415 Unsupported Media Type`; bodyless requests (`GET`, `DELETE`) are unaffected. The previous lenient behavior can be restored with `FastAPI(strict_content_type=False)`. Documented in the API Overview (Korean and English).

---

## [v2026.03.31-41a4f1d] - 2026-03-31

### Added

- **WebSocket close code specification**: Documented close codes (`1000`, `1008`, `1011`, `4029`) in both Korean and English WebSocket API docs with reconnection guidance per code. Updated reconnection example to block retry on `1008` (auth failure). ([#15](https://github.com/onprem-hipster-timer/backend/issues/15), [#18](https://github.com/onprem-hipster-timer/backend/pull/18))

---

## [v2026.03.09-2c3b92f] - 2026-03-09

### Added

- **`UpdateMixin.apply_update` for ORM models**: Added a generic partial-update method to `UpdateMixin` (inherited by all models via `UUIDBase`). Accepts a dict (from `model_dump()`) and applies values to model columns with built-in safeguards.
  - **Protected fields**: Primary keys (auto-detected via SQLAlchemy mapper), `TimestampMixin` fields (`created_at`, `updated_at` — derived from `TimestampMixin.__annotations__`), and `owner_id` are always excluded from updates.
  - **Nullable safety**: Setting `None` on a non-nullable column is silently skipped; nullable columns accept `None` normally. Nullable status is correctly resolved via `ColumnProperty.columns[0].nullable`.
  - **Custom exclusion**: Callers can pass `exclude=["field"]` to protect additional fields per use case.

### Changed

- **Centralized Visibility API controller**: Extracted visibility management from each domain (Schedule, Timer, Todo, Meeting) into a dedicated `/v1/visibility/{resource_type}/{resource_id}` endpoint with `PUT`/`GET`/`DELETE` operations.
  - **Breaking change**: `visibility` field removed from all Create/Update DTOs. Clients must set visibility via a separate `PUT /v1/visibility/{type}/{id}` call after resource creation.
- **MISSING sentinel for Update DTOs**: Replaced `Optional[T] = None` + `model_dump(exclude_unset=True)` pattern with `pydantic.experimental.missing_sentinel.MISSING` across all Update DTOs (`TodoUpdate`, `ScheduleUpdate`, `TagGroupUpdate`, `TagUpdate`, `TimerUpdate`, `MeetingUpdate`).
  - Fields now use `T | None = MISSING` for explicit 3-way semantics: MISSING (not sent, keep current), `None` (clear value), value (set value).
  - Removed all `model_dump(exclude_unset=True)` calls from CRUD and Service layers; `model_dump()` now automatically excludes MISSING fields.
  - Fixed `validate_time_order` to use `isinstance` checks, preventing `TypeError` when cross-field validators receive MISSING sentinel values.

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

[Unreleased]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.08-099ab9f...HEAD
[v2026.11.08-099ab9f]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.07-f65a7fe...v2026.11.08-099ab9f
[v2026.11.07-f65a7fe]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.07-c7b2408...v2026.11.07-f65a7fe
[v2026.11.07-c7b2408]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.07-acb5673...v2026.11.07-c7b2408
[v2026.11.07-acb5673]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.06-039b759...v2026.11.07-acb5673
[v2026.11.06-039b759]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.04-71e4266...v2026.11.06-039b759
[v2026.11.04-71e4266]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.04-42359ab...v2026.11.04-71e4266
[v2026.11.04-42359ab]: https://github.com/onprem-hipster-timer/backend/compare/v2026.11.04-5b27507...v2026.11.04-42359ab
[v2026.11.04-5b27507]: https://github.com/onprem-hipster-timer/backend/compare/v2026.07.21-c825e27...v2026.11.04-5b27507
[v2026.07.21-c825e27]: https://github.com/onprem-hipster-timer/backend/compare/v2026.06.15-552ec57...v2026.07.21-c825e27
[v2026.06.15-552ec57]: https://github.com/onprem-hipster-timer/backend/compare/v2026.06.15-53559c3...v2026.06.15-552ec57
[v2026.06.15-53559c3]: https://github.com/onprem-hipster-timer/backend/compare/v2026.06.12-cfa3200...v2026.06.15-53559c3
[v2026.06.12-cfa3200]: https://github.com/onprem-hipster-timer/backend/compare/v2026.06.09-30c31db...v2026.06.12-cfa3200
[v2026.06.09-30c31db]: https://github.com/onprem-hipster-timer/backend/compare/v2026.06.09-91639bf...v2026.06.09-30c31db
[v2026.06.09-91639bf]: https://github.com/onprem-hipster-timer/backend/compare/v2026.03.31-41a4f1d...v2026.06.09-91639bf
[v2026.03.31-41a4f1d]: https://github.com/onprem-hipster-timer/backend/compare/v2026.03.09-2c3b92f...v2026.03.31-41a4f1d
[v2026.03.09-2c3b92f]: https://github.com/onprem-hipster-timer/backend/compare/v2026.03.05-6194559...v2026.03.09-2c3b92f
[v2026.03.05-6194559]: https://github.com/onprem-hipster-timer/backend/compare/v2026.03.04-d027c48...v2026.03.05-6194559
[v2026.03.04-d027c48]: https://github.com/onprem-hipster-timer/backend/compare/v2026.03.03-5609ccd...v2026.03.04-d027c48
[v2026.03.03-5609ccd]: https://github.com/onprem-hipster-timer/backend/compare/v2026.02.23-e582adc...v2026.03.03-5609ccd
[v2026.02.23-e582adc]: https://github.com/onprem-hipster-timer/backend/compare/v2026.01.30...v2026.02.23-e582adc
[v2026.01.30]: https://github.com/onprem-hipster-timer/backend/releases/tag/v2026.01.30
