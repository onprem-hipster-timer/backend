"""허용 이메일·도메인을 앞뒤 공백 없는 소문자로 바꾸고 중복을 지우는 데이터 이전

alembic/versions/2026_11_14_1200-aeb221d93ba3_normalize_visibility_allow_email.py
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401  # register every table in SQLModel.metadata
import app.models.holiday  # noqa: F401
from app.core.auth import CurrentUser
from app.domain.visibility.service import VisibilityService
from app.models.visibility import ResourceType, ResourceVisibility, VisibilityAllowEmail, VisibilityLevel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "e7f3a9c5b1d8"


def _alembic_config(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Config:
    # alembic env.py는 실행 시점의 settings.DATABASE_URL을 읽는다
    import app.core.config as app_config
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", (PROJECT_ROOT / "alembic").resolve().as_posix())
    return config


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, sa.Engine]:
    database_url = f"sqlite:///{(tmp_path / 'allow-email.db').resolve().as_posix()}"
    config = _alembic_config(monkeypatch, database_url)
    engine = sa.create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    command.stamp(config, "head")
    command.downgrade(config, PREVIOUS_REVISION)
    return config, engine


def _add_visibility(session: Session, owner_id: str, emails=(), domains=()) -> ResourceVisibility:
    visibility = ResourceVisibility(
        resource_type=ResourceType.SCHEDULE,
        resource_id=uuid4(),
        owner_id=owner_id,
        level=VisibilityLevel.ALLOWED_EMAILS,
    )
    session.add(visibility)
    session.flush()
    for email in emails:
        session.add(VisibilityAllowEmail(visibility_id=visibility.id, email=email))
    for domain in domains:
        session.add(VisibilityAllowEmail(visibility_id=visibility.id, domain=domain))
    session.flush()
    return visibility


def _entries(engine: sa.Engine) -> dict[str, list[tuple[str | None, str | None]]]:
    """owner_id → 정렬한 (email, domain) 목록"""
    with Session(engine) as session:
        rows = session.exec(
            select(ResourceVisibility.owner_id, VisibilityAllowEmail.email, VisibilityAllowEmail.domain)
            .join(ResourceVisibility, ResourceVisibility.id == VisibilityAllowEmail.visibility_id)
        ).all()
    result: dict[str, list[tuple[str | None, str | None]]] = {}
    for owner_id, email, domain in rows:
        result.setdefault(owner_id, []).append((email, domain))
    return {owner: sorted(entries, key=lambda e: (e[0] or "", e[1] or "")) for owner, entries in result.items()}


def test_upgrade_lower_cases_and_deduplicates_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, engine = _prepare(tmp_path, monkeypatch)
    with Session(engine) as session:
        _add_visibility(
            session, "a",
            emails=["Alice@Partner.com", "alice@partner.com", " ALICE@PARTNER.COM ", "bob@partner.com"],
            domains=["Company.com", "company.com"],
        )
        _add_visibility(session, "b", emails=["Alice@Partner.com"], domains=["Partner.ORG"])
        session.commit()

    command.upgrade(config, "head")

    expected = {
        "a": [(None, "company.com"), ("alice@partner.com", None), ("bob@partner.com", None)],
        "b": [(None, "partner.org"), ("alice@partner.com", None)],
    }
    assert _entries(engine) == expected

    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    assert _entries(engine) == expected

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert current == heads[0]


def test_upgrade_on_empty_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, engine = _prepare(tmp_path, monkeypatch)

    command.upgrade(config, "head")

    assert _entries(engine) == {}
    engine.dispose()


@pytest.mark.parametrize(
    ("emails", "domains", "viewer_email", "allowed"),
    [
        (["Alice@Partner.com"], [], "alice@partner.com", True),
        (["Alice@Partner.com"], [], "ALICE@partner.com", True),
        ([], ["Partner.COM"], "bob@partner.com", True),
        ([], ["Partner.COM"], "bob@sub.partner.com", False),
        (["Alice@Partner.com"], [], "bob@partner.com", False),
    ],
)
def test_entries_stored_with_upper_case_match_after_upgrade(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emails, domains, viewer_email, allowed,
) -> None:
    config, engine = _prepare(tmp_path, monkeypatch)
    with Session(engine) as session:
        visibility = _add_visibility(session, "owner", emails=emails, domains=domains)
        resource_id = visibility.resource_id
        session.commit()

    command.upgrade(config, "head")

    viewer = CurrentUser(sub="viewer", email=viewer_email, email_verified=True, name="Viewer")
    with Session(engine) as session:
        service = VisibilityService(session, viewer)
        assert service.can_access(ResourceType.SCHEDULE, resource_id, "owner") is allowed
        visibility = session.exec(
            select(ResourceVisibility).where(ResourceVisibility.resource_id == resource_id)
        ).one()
        accessible = service.filter_accessible_resources(
            ResourceType.SCHEDULE, [visibility], [visibility], lambda v: v.resource_id,
        )
        assert (accessible == [visibility]) is allowed
    engine.dispose()
