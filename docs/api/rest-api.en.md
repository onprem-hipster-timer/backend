# REST API Reference

View the complete API spec in Swagger UI format.

<swagger-ui src="openapi.json"/>

## 주요 엔드포인트

### Schedules

```http
GET    /v1/schedules                    # Get schedules by date range
POST   /v1/schedules                    # Create new schedule
GET    /v1/schedules/{id}               # Get specific schedule
PATCH  /v1/schedules/{id}               # Update schedule
DELETE /v1/schedules/{id}               # Delete schedule
GET    /v1/schedules/{id}/timers        # Get timers for schedule
GET    /v1/schedules/{id}/timers/active # Get active timer
```

### Timers

```http
GET    /v1/timers/{id}           # Get timer
PATCH  /v1/timers/{id}           # Update timer
DELETE /v1/timers/{id}           # Delete timer
```

!!! warning "Warning"
    **Note**: Timer creation and control (create, pause, resume, stop) are handled via WebSocket API.

### Todos

```http
GET    /v1/todos                 # List todos
POST   /v1/todos                 # Create todo
GET    /v1/todos/{id}            # Get specific todo
PATCH  /v1/todos/{id}            # Update todo (including moving it to another todo group)
DELETE /v1/todos/{id}            # Delete todo
GET    /v1/todos/stats           # Get statistics
GET    /v1/todos/groups          # List todo groups (creates the default group if missing)
POST   /v1/todos/groups          # Create todo group
GET    /v1/todos/groups/{id}     # Get specific todo group
PATCH  /v1/todos/groups/{id}     # Update todo group
DELETE /v1/todos/groups/{id}     # Delete todo group (its todos move to the default group)
```

### Tags

```http
GET    /v1/tags/groups           # List tag groups (with tags)
POST   /v1/tags/groups           # Create tag group
GET    /v1/tags/groups/{id}      # Get specific tag group
PATCH  /v1/tags/groups/{id}      # Update tag group
DELETE /v1/tags/groups/{id}      # Delete tag group (and its tags)
GET    /v1/tags                  # List tags
POST   /v1/tags                  # Create tag
DELETE /v1/tags/{id}             # Delete tag
```

### Visibility

```http
PUT    /v1/visibility/{resource_type}/{resource_id}   # Set/update visibility
GET    /v1/visibility/{resource_type}/{resource_id}   # Get visibility settings
DELETE /v1/visibility/{resource_type}/{resource_id}   # Delete visibility (revert to PRIVATE)
```

!!! info "`resource_type`"
    One of `schedule`, `timer`, `todo`, `meeting`.

!!! info "Resources the caller cannot access"
    Schedule, timer, todo and meeting routes answer a resource the caller cannot access with the same `404` as a resource that does not exist. Visibility routes return `404` when the resource does not exist or the caller is not its owner. See the [Visibility guide](../guides/visibility.ko.md#접근-제어-규칙).

### Friends

```http
GET    /v1/friends                       # Friend list (includes display_name, avatar_url)
GET    /v1/friends/ids                    # Friend id list
GET    /v1/friends/check/{user_id}        # Check friendship
POST   /v1/friends/requests               # Friend request (email or friend_code)
GET    /v1/friends/requests/received      # Received requests (includes requester_display_name)
GET    /v1/friends/requests/sent          # Sent requests
POST   /v1/friends/requests/{id}/accept   # Accept request
POST   /v1/friends/requests/{id}/reject   # Reject request
DELETE /v1/friends/requests/{id}          # Cancel sent request
DELETE /v1/friends/{id}                   # Remove friend
POST   /v1/friends/block/{user_id}        # Block user
DELETE /v1/friends/block/{user_id}        # Unblock user
```

!!! info "Friend request (`POST /v1/friends/requests`)"
    The body provides **exactly one** of `{ "email": "..." }` or `{ "friend_code": "..." }` — an **email** (validated; matched against stored verified emails; always returns a uniform `202` to prevent account enumeration) or a **friend code** (random share code; `404` if unknown). Sending both, neither, or `null` returns `422`. No user search/directory is provided. Get your friend code from `GET /v1/users/me`.

### Users

```http
GET    /v1/users/me                       # Own display info + friend code (for sharing)
PUT    /v1/users/me/consent               # Record consent to the terms (usability analytics consent is optional)
POST   /v1/users/me/deletion              # Request account deletion (dormant)
DELETE /v1/users/me/deletion              # Cancel account deletion
```

!!! info "Terms consent and usability analytics consent"
    The body of `PUT /v1/users/me/consent` is `{"version": "<consent_version>", "age_over_14": true, "terms": true, "privacy": true, "analytics": true}`. `version` is the `consent_version` from `GET /v1/users/me` (otherwise `409`), and the three items must all be `true` (otherwise `422`). `analytics` (usability analytics consent) is optional: `true`, `false`, `null` or left out. Leaving it out or `null` means not chosen; a value that is not a boolean returns `422`. The response is the caller's profile (same shape as `GET /v1/users/me`, `200`).
    Sending the same version again keeps the first consent record and changes only `analytics`; leaving it out, `null` or the stored value changes nothing. Consent is recorded per terms version, so after the terms version changes the choice starts from the `analytics` sent with the consent to the new version.
    In profile responses, `analytics_consent` is the value chosen with the consent to the current terms version (`true`, `false`, or `null` when not chosen) and `analytics_consent_updated_at` is when that value was last set. Both are `null` while the member has not consented to the current version (`consent_required: true`). With `CONSENT_ENFORCED`, a member who has not consented can still call this path; dormant accounts get `423`. Purging the account deletes it with the consent records.

!!! info "Account deletion"
    A request makes the account dormant and ends every login session. A dormant account's data is hidden from other users, and any authenticated request other than reading the profile and requesting or cancelling deletion returns `423` (`message: "account_deletion_pending"`). The user can log in again and cancel; once `deletion_scheduled_at` (request + `ACCOUNT_DELETION_GRACE_DAYS` days) has passed, the next purge run deletes all data and the login identity. Tokens of a purged account get `401` (`message: "account_deleted"`).

### Guests

Only answered when `GUEST_ENABLED=true` (404 otherwise).

```http
POST   /v1/guests/lookup                  # Find the login identifier (handle) of the guest with that name in a resource (no authentication). Also returns the current consent version
POST   /v1/guests                         # Create a guest (no authentication, consent required). Returns the handle
DELETE /v1/guests/me                      # The guest deletes itself (guest JWT)
PUT    /v1/guests/me/consent              # Record the guest's consent (guest JWT)
```

Guests sign in with `handle` and their password through `/auth`, like members, and get JWTs the same way. Lookup, creation, self-deletion, a guest's login submission and a settings submission from a guest session need a Turnstile token (`X-Turnstile-Token` header), and each token is accepted once. Recording consent takes no token. The `consent` of creation and the body of recording consent are the same as the member's `PUT /v1/users/me/consent`, so the optional `analytics` item is recorded by the same rules. With `CONSENT_ENFORCED`, a guest that has not consented to the current version gets `428` (`message: "consent_required"`) on guest routes other than recording consent and self-deletion. Guest tokens get `403` on every authenticated route other than the ones above and the guest routes of the resource they belong to. See the [Guest guide](../guides/guest.ko.md).

### Holidays

```http
GET    /v1/holidays              # List holidays
```

## 상세 가이드

각 API에 대한 상세한 사용법은 다음 가이드를 참조하세요:

- [Schedule Guide](../guides/schedule.ko.md)
- [Timer Guide](../guides/timer.ko.md)
- [Todo Guide](../guides/todo.ko.md)
- [Friend Guide](../guides/friend.ko.md)
- [Visibility Guide](../guides/visibility.ko.md)
- [Meeting Guide](../guides/meeting.ko.md)
