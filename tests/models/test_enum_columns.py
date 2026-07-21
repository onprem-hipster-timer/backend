"""
Enum 컬럼 저장 정책 고정 테스트

정책 (docs/development/enums.ko.md):
- 테이블에 저장되는 모든 enum 컬럼은 VARCHAR(`native_enum=False`)로 저장한다.
  네이티브 DB enum 타입(Postgres `CREATE TYPE`)은 금지 — 값 추가마다
  `ALTER TYPE` 마이그레이션이 필요해지고 SQLite와 이식성이 깨진다.
- 저장 값은 멤버 이름이 아니라 `.value`다 (`values_callable`).

이 테스트는 메타데이터 전체를 순회하므로, 새 모델/컬럼이 정책을 이탈하면
즉시 실패한다.
"""
import sqlalchemy as sa
from sqlmodel import SQLModel

import app.models  # noqa: F401 — 전체 모델을 메타데이터에 로드


def _enum_columns():
    for table in SQLModel.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, sa.Enum):
                yield table.name, col


def test_all_enum_columns_are_non_native():
    """모든 저장 enum 컬럼은 native_enum=False (VARCHAR 저장)"""
    violations = [
        f"{table}.{col.name} ({col.type.enum_class.__name__})"
        for table, col in _enum_columns()
        if col.type.native_enum
    ]
    assert not violations, (
        "네이티브 DB enum 컬럼 발견 — models/base.py의 str_enum_column()을 "
        f"사용하세요: {violations}"
    )


def test_all_enum_columns_store_values_not_names():
    """저장 값은 멤버 이름이 아니라 .value (values_callable 적용)"""
    violations = []
    for table, col in _enum_columns():
        expected = [e.value for e in col.type.enum_class]
        if list(col.type.enums) != expected:
            violations.append(f"{table}.{col.name}: {list(col.type.enums)} != {expected}")
    assert not violations, f"values_callable 미적용 컬럼: {violations}"


def test_enum_columns_exist():
    """순회 자체가 비어 있으면 테스트가 무의미 — 최소 개수 방어"""
    assert len(list(_enum_columns())) >= 6
