# Validator 추가 가이드

DTO에 Pydantic validator를 추가할 때의 패턴과 주의사항을 설명합니다.

---

## 1. 프로젝트의 validator 패턴

### 공용 validator 함수 (`app/utils/validators.py`)

여러 DTO에서 재사용되는 검증 로직은 공용 함수로 분리합니다.

| 함수 | 용도 | 사용처 |
|------|------|--------|
| `validate_time_order` | `end_time > start_time` 검증 | `ScheduleCreate`, `ScheduleUpdate` |
| `validate_color` | HEX 색상 코드 (`#FFF`, `#FFFFFF`) 검증 | `TagCreate`, `TagUpdate`, `TagGroupCreate`, `TagGroupUpdate` |

### UTC 변환 (`app/domain/dateutil/service.py`)

| 함수 | 용도 | 사용처 |
|------|------|--------|
| `ensure_utc_naive` | timezone-aware datetime → UTC naive 변환 | `ScheduleCreate/Update`, `TimerRead` |

---

## 2. `@field_validator` 추가

### Create DTO

값이 항상 존재하므로 단순하게 검증합니다.

```python
class TimerCreate(CustomModel):
    allocated_duration: int

    @field_validator("allocated_duration")
    @classmethod
    def validate_allocated_duration(cls, v):
        if v <= 0:
            raise ValueError("allocated_duration must be positive")
        return v
```

### Update DTO (MISSING sentinel)

Update DTO는 필드가 `MISSING`일 수 있으므로 **반드시 `isinstance`로 타입 체크** 후 검증해야 합니다.

```python
# ❌ MISSING이 들어오면 TypeError 발생
@field_validator("end_time")
def validate_time(cls, end_time, info):
    start_time = info.data.get("start_time")
    if start_time and end_time <= start_time:  # MISSING <= datetime → TypeError
        raise ValueError("...")

# ✅ isinstance로 실제 값인지 확인
@field_validator("end_time")
def validate_time(cls, end_time, info):
    start_time = info.data.get("start_time")
    if isinstance(start_time, datetime) and isinstance(end_time, datetime):
        if end_time <= start_time:
            raise ValueError("...")
    return end_time
```

!!! danger "Update DTO에서 `is not None` 사용 금지"
    `MISSING is not None`은 `True`입니다. MISSING을 걸러내려면 `isinstance`를 사용하세요.

### nullable 필드

validator에서 `None` 가능성을 먼저 처리합니다.

```python
@field_validator("color")
@classmethod
def validate_color_field(cls, v: str | None) -> str | None:
    return validate_color(v)  # validate_color 내부에서 None 처리
```

---

## 3. 공용 validator 함수 작성

여러 DTO에서 같은 검증이 필요하면 `app/utils/validators.py`에 함수를 추가합니다.

```python
# app/utils/validators.py
def validate_positive(value: int | None, field_name: str) -> int | None:
    if value is not None and value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value
```

```python
# DTO에서 사용
@field_validator("allocated_duration")
@classmethod
def validate_allocated_duration(cls, v):
    return validate_positive(v, "allocated_duration")
```

---

## 4. `@model_validator`

여러 필드 간 관계를 검증할 때 사용합니다.

```python
@model_validator(mode="before")
@classmethod
def normalize_data(cls, data):
    """입력 데이터 전처리 (파싱 전)"""
    if isinstance(data, dict) and "items" in data:
        if data["items"] == "":
            data["items"] = None
    return data
```

- `mode="before"`: Pydantic 파싱 전 raw 데이터를 전처리
- `mode="after"`: 파싱 완료 후 인스턴스 레벨에서 검증

---

## 관련 코드

| 파일 | 역할 |
|------|------|
| `app/utils/validators.py` | 공용 validator 함수 |
| `app/domain/dateutil/service.py` | `ensure_utc_naive` |
| `app/domain/*/schema/dto.py` | 각 도메인의 DTO validator |
