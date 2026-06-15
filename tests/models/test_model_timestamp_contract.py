"""
App model timestamp contract tests.

These tests guard against accidentally dropping TimestampMixin from a table
model during model refactors.
"""
import importlib
import inspect
import pkgutil
from collections.abc import Iterator

import pytest

import app.models
from app.models.base import TimestampMixin, utc_now_naive


TIMESTAMP_TABLE_NAMES = {
    "friendship",
    "holiday_hashes",
    "holidays",
    "meeting",
    "meeting_participant",
    "resource_visibility",
    "schedule",
    "scheduleexception",
    "tag",
    "tag_group",
    "timersession",
    "todo",
    "user_profile",
}

TIMESTAMPLESS_TABLE_NAMES = {
    "meeting_time_slot",
    "schedule_exception_tag",
    "schedule_tag",
    "timer_tag",
    "todo_tag",
    "visibility_allow_email",
    "visibility_allow_list",
}


def _iter_app_table_models() -> Iterator[type]:
    for module_info in pkgutil.iter_modules(app.models.__path__):
        module = importlib.import_module(f"{app.models.__name__}.{module_info.name}")

        for _, model in inspect.getmembers(module, inspect.isclass):
            if model.__module__ != module.__name__:
                continue
            if hasattr(model, "__table__"):
                yield model


def _app_table_models_by_name() -> dict[str, type]:
    return {model.__table__.name: model for model in _iter_app_table_models()}


def _assert_timestamp_callable(column_default) -> None:
    assert column_default is not None
    assert callable(column_default.arg)
    assert column_default.arg.__module__ == utc_now_naive.__module__
    assert column_default.arg.__name__ == utc_now_naive.__name__


def test_all_app_tables_are_classified_for_timestamp_contract():
    table_names = set(_app_table_models_by_name())

    assert table_names == TIMESTAMP_TABLE_NAMES | TIMESTAMPLESS_TABLE_NAMES


@pytest.mark.parametrize("table_name", sorted(TIMESTAMP_TABLE_NAMES))
def test_timestamp_tables_use_timestamp_mixin(table_name):
    model = _app_table_models_by_name()[table_name]

    assert issubclass(model, TimestampMixin)


@pytest.mark.parametrize("table_name", sorted(TIMESTAMP_TABLE_NAMES))
def test_timestamp_tables_have_non_nullable_timestamp_columns(table_name):
    table = _app_table_models_by_name()[table_name].__table__

    assert "created_at" in table.c
    assert "updated_at" in table.c
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False


@pytest.mark.parametrize("table_name", sorted(TIMESTAMP_TABLE_NAMES))
def test_timestamp_columns_have_insert_and_update_defaults(table_name):
    table = _app_table_models_by_name()[table_name].__table__

    _assert_timestamp_callable(table.c.created_at.default)
    _assert_timestamp_callable(table.c.updated_at.default)
    _assert_timestamp_callable(table.c.updated_at.onupdate)


@pytest.mark.parametrize("table_name", sorted(TIMESTAMP_TABLE_NAMES))
def test_timestamp_models_create_naive_utc_defaults(table_name):
    model = _app_table_models_by_name()[table_name]

    before = utc_now_naive()
    entity = model()
    after = utc_now_naive()

    assert before <= entity.created_at <= after
    assert before <= entity.updated_at <= after
    assert entity.created_at.tzinfo is None
    assert entity.updated_at.tzinfo is None


@pytest.mark.parametrize("table_name", sorted(TIMESTAMPLESS_TABLE_NAMES))
def test_timestampless_tables_do_not_have_timestamp_columns(table_name):
    model = _app_table_models_by_name()[table_name]

    assert not issubclass(model, TimestampMixin)
    assert "created_at" not in model.__table__.c
    assert "updated_at" not in model.__table__.c
