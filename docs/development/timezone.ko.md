# 타임존(Timezone) 처리 가이드

이 서비스는 해외 출장 등 **다양한 타임존의 클라이언트**를 대응하기 위해 datetime을
일관된 규칙으로 처리합니다. 이 문서는 그 규칙과 적용 위치, 새 필드를 추가할 때의
체크리스트를 설명합니다.

---

## 1. 핵심 원칙

> **DB에는 timezone-naive UTC로 저장한다.** (`TIMESTAMP WITHOUT TIME ZONE`)

- **입력(요청 → DB):** 클라이언트가 보낸 datetime은 timezone 정보가 있을 수도(aware),
  없을 수도(naive) 있습니다. 경계에서 **UTC로 변환한 뒤 naive로** 만들어 저장합니다.
    - aware datetime → UTC로 변환 후 tzinfo 제거
    - naive datetime → UTC로 가정하고 그대로 사용
- **저장(DB):** 모든 datetime 컬럼은 naive UTC. SQLite와 PostgreSQL 양쪽에서 동일하게 동작합니다.
- **출력(DB → 응답):** 저장된 naive UTC를 클라이언트가 요청한 타임존(`timezone` 쿼리 파라미터)
  기준의 **aware datetime**으로 변환하여 반환합니다. 지정하지 않으면 UTC로 반환합니다.

```
[Client]  2024-01-01T09:00:00+09:00 (KST, aware)
   │  요청
   ▼
[입력 경계] ensure_utc_naive  →  2024-01-01T00:00:00 (UTC, naive)
   │
   ▼
[DB]  2024-01-01 00:00:00   (TIMESTAMP WITHOUT TIME ZONE)
   │
   ▼
[출력 경계] to_timezone(KST) →  2024-01-01T09:00:00+09:00 (KST, aware)
   │  응답 (?timezone=Asia/Seoul)
   ▼
[Client]
```

### 왜 naive UTC인가?

- **DB 이식성:** SQLite는 timezone 타입을 저장하지 않습니다. naive UTC로 통일하면
  SQLite(개발/테스트)와 PostgreSQL(운영)에서 동작이 같아집니다.
- **장애 예방:** aware datetime을 `TIMESTAMP WITHOUT TIME ZONE` 컬럼에 주입하면
  asyncpg에서 `can't subtract offset-naive and offset-aware datetimes` /
  `DataError`가 발생합니다. (아래 [부록: 장애 사례 #41](#부록-장애-사례-41) 참고)

---

## 2. 변환 헬퍼 (`app/domain/dateutil/service.py`)

| 함수 | 방향 | 용도 |
|------|------|------|
| `ensure_utc_naive(dt)` | 입력 | aware → UTC 변환 후 naive. naive는 UTC로 가정하고 그대로 반환 |
| `to_utc_naive(dt)` | 입력 | `ensure_utc_naive`와 동일 의미 (저장용 정규화) |
| `convert_utc_naive_to_timezone(dt, tz)` | 출력 | naive UTC → 지정 타임존 aware |
| `parse_timezone(tz_str)` | 출력 | `"UTC"`, `"+09:00"`, `"Asia/Seoul"` 등을 `tzinfo`로 파싱 |
| `get_year_range_utc(year)` | 조회 | KST 기준 연도 범위를 UTC naive 범위로 변환 |
| `parse_locdate_to_datetime_range(locdate)` | 입력 | `YYYYMMDD`(KST)를 KST 기준 24시간 UTC naive 범위로 변환 |

---

## 3. 적용 위치

### 입력 경계

- **요청 본문 DTO:** datetime 필드에 `@field_validator`로 `ensure_utc_naive`를 적용합니다.

    ```python
    @field_validator("deadline")
    @classmethod
    def ensure_utc_naive_datetime(cls, v):
        return ensure_utc_naive(v) if v is not None else None
    ```

- **datetime 쿼리 파라미터:** 서비스/CRUD에서 비교·저장 직전에 `ensure_utc_naive`로 변환합니다.
  (예: `start_date`, `end_date`, `instance_start`)

### 출력 경계

- **응답 DTO:** `to_timezone(tz, validate=True)` 메서드를 두고, 라우터에서
  `timezone` 쿼리 파라미터(`parse_timezone`)로 변환합니다.

    ```python
    tz_obj = parse_timezone(tz) if tz else None
    return read_dto.to_timezone(tz_obj)
    ```

### 서버 생성 타임스탬프

- `created_at` / `updated_at`은 `TimestampMixin`(`app/models/base.py`)이
  `utc_now_naive()`(naive UTC)로 채웁니다. **직접 `datetime.now(UTC)`(aware)를 컬럼에
  대입하지 마세요.** 필요하면 `ensure_utc_naive(datetime.now(UTC))`를 사용합니다.

---

## 4. 도메인별 현황

| 도메인 | 입력 변환 | 출력 변환 | 비고 |
|--------|-----------|-----------|------|
| schedule | ✅ `ScheduleCreate/Update` validator, 쿼리 파라미터 변환 | ✅ `ScheduleRead.to_timezone` + `timezone` | |
| timer | ✅ 서버에서 `ensure_utc_naive(datetime.now(UTC))` 설정 | ✅ `TimerRead.to_timezone` + `timezone` | 입력 datetime을 직접 받지 않음 |
| todo | ✅ `TodoCreate/Update` validator | ✅ `TodoRead.to_timezone` + `timezone` | `deadline` |
| holiday | ✅ `parse_locdate_to_datetime_range`, `ensure_utc_naive` | – | 해시 `updated_at`도 naive UTC로 저장 |
| meeting | ✅ `date`/`time` 타입만 사용(datetime 입력 없음) | – | |
| friend / visibility / tag | – | – | `TimestampMixin` 타임스탬프만 사용 |

---

## 5. 새 datetime 필드 추가 체크리스트

1. **모델 컬럼**은 일반 `datetime`으로 둡니다. → PostgreSQL에서 `TIMESTAMP WITHOUT TIME ZONE`(naive).
2. **요청 DTO**에 datetime 필드가 있으면 `ensure_utc_naive` validator를 추가합니다.
    - `Create` DTO: `return ensure_utc_naive(v) if v is not None else None`
    - `Update` DTO(MISSING 센티넬 사용): 동일 패턴. 미지정 시 validator가 동작하지 않아
      MISSING이 유지됩니다.
3. **datetime 쿼리 파라미터**는 비교/저장 직전에 `ensure_utc_naive`로 변환합니다.
4. **응답 DTO**에 `to_timezone`를 구현하고, 라우터에서 `timezone` 쿼리 파라미터로 변환합니다.
5. **서버 타임스탬프**는 `TimestampMixin` 또는 `ensure_utc_naive(datetime.now(UTC))`를 사용합니다.
6. **테스트**(`tests/crud/`)에서 aware 입력 → naive UTC 저장, naive UTC → 요청 타임존 출력
   라운드트립을 검증합니다. PostgreSQL 테스트 DB(`TEST_DATABASE_URL`)에서 실행하면 더 정확합니다.

---

## 부록: 장애 사례 #41

휴일 동기화(Holiday Sync) 배치에서 `holiday_hashes.updated_at`(naive 컬럼)에
`datetime.now(timezone.utc)`(aware)를 대입하여 asyncpg에서 다음 오류가 발생했습니다.

```
TypeError: can't subtract offset-naive and offset-aware datetimes
asyncpg.exceptions.DataError: invalid input for query argument $1: datetime.datetime(2026, 6, 15... tzinfo=datetime.timezone.utc)
```

같은 버그 클래스가 **todo 도메인의 `deadline`**에도 존재했습니다. `TodoCreate/Update`에
변환 validator가 없어, 클라이언트가 보낸 aware deadline이 naive `Todo.deadline` 컬럼에
그대로 저장되는 경로였습니다. 두 경로 모두 입력 경계에서 `ensure_utc_naive`로 변환하도록
수정했습니다.

!!! note "교훈"
    SQLite 테스트는 timezone 타입을 엄격히 검증하지 않아 이 장애를 재현하지 못합니다.
    timezone 관련 회귀 테스트는 PostgreSQL 테스트 DB에서 실행하세요.
