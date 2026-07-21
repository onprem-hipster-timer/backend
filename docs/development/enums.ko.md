# Enum 컨벤션

> **상태**: 확정·구현됨. 정책 고정 테스트: `tests/models/test_enum_columns.py`

도메인별로 제각각이던 enum의 **정의 위치**와 **저장 방식**을 통일한 규칙입니다.
자료형으로서의 enum(Python 타입)과 테이블의 enum(저장 컬럼)은 계층이 다릅니다.

---

## 1. 자료형 ENUM — 소유 도메인의 `enums.py`

도메인 어휘인 enum은 소유 도메인이 정의합니다. `(str, Enum)`을 상속합니다.

| Enum | 정식 정의 위치 |
|------|----------------|
| `TodoStatus`, `LinkedSchedulePolicy` | `app/domain/todo/enums.py` |
| `ScheduleState`, `SourceTodoPolicy` | `app/domain/schedule/enums.py` |
| `TimerStatus` | `app/domain/timer/enums.py` |
| `FriendshipStatus` | `app/domain/friend/enums.py` |
| `VisibilityLevel`, `ResourceType` | `app/domain/visibility/enums.py` |

- **models는 저장 매핑만 담당**합니다 — 자료형 정의를 models 파일에 두지 않습니다.
- 저장되지 않는 API·인프라 enum은 쓰이는 계층에 둡니다:
  `ResourceScope`·`TagIncludeMode`(공용 쿼리 파라미터 → `app/core/constants.py`),
  WS 메시지 타입(`schema/ws.py`), `EventOrigin`(`app/shared/events.py`),
  DTO 전용(`TodoIncludeReason` 등 → 해당 `schema/dto.py`).

!!! note "하위호환 재수출"
    이동 전 위치(`app/core/constants.py`의 `TimerStatus`, `app/models/friendship.py`의
    `FriendshipStatus`, `app/models/visibility.py`의 `VisibilityLevel`/`ResourceType`)는
    재수출로 유지됩니다. 새 코드는 정식 경로에서 import하세요.

---

## 2. 테이블 ENUM — `str_enum_column()`으로 VARCHAR 저장

테이블에 저장되는 enum 컬럼은 반드시 `app/models/base.py`의 `str_enum_column()`을
사용합니다.

```python
from app.models.base import str_enum_column

class Todo(UUIDBase, TimestampMixin, table=True):
    status: TodoStatus = Field(
        default=TodoStatus.UNSCHEDULED,
        sa_column=str_enum_column(TodoStatus, default=TodoStatus.UNSCHEDULED),
    )
```

헬퍼가 보장하는 것:

- **`native_enum=False`** — 네이티브 DB enum(Postgres `CREATE TYPE`) 금지.
  네이티브 타입은 멤버를 추가할 때마다 `ALTER TYPE` 마이그레이션이 필요하고,
  SQLite와의 이식성이 깨집니다. VARCHAR 저장 + 앱 계층 검증으로 충분합니다.
- **`values_callable`** — 멤버 **이름이 아니라 `.value`**를 저장합니다.

!!! danger "정책 이탈은 테스트가 적발"
    `tests/models/test_enum_columns.py`가 메타데이터 전체를 순회하며 모든 enum
    컬럼의 `native_enum=False`·`values_callable` 적용을 단언합니다. `sa_column`을
    생략하면 SQLModel이 네이티브 enum을 자동 생성하므로(과거 `timersession.status`가
    그렇게 이탈 — 마이그레이션 `d5e8f2a3b4c1`로 정리) 저장 enum 필드에는 반드시
    헬퍼를 명시하세요.

---

## 3. `.value`는 직렬화 경계에서만

도메인 로직(비교·대입·질의 필터)에서는 enum 인스턴스를 사용합니다.

```python
# ✅ 도메인 로직
timer.status = TimerStatus.COMPLETED
if timer.status == TimerStatus.RUNNING: ...
query.where(TimerSession.status.in_([TimerStatus.RUNNING, TimerStatus.PAUSED]))

# ❌ 문자열 취급 (과거 timer 도메인 관행 — 제거됨)
timer.status = TimerStatus.COMPLETED.value

# ✅ 직렬화 경계 (JSON/WS payload 조립)에서는 .value가 적절
payload = {"status": timer.status.value}
```

`(str, Enum)`이라 문자열 비교도 동작하지만, 타입 일관성과 IDE·mypy 지원을 위해
도메인 로직에서는 enum 인스턴스로 통일합니다.
