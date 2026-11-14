"""저장소의 게스트 Kratos 설정(dev/kratos)이 backend와 맞는지

실제 Kratos 동작은 docs/deployment/kratos-guest.ko.md의 확인 절차로 본다. 여기서는 파일끼리의 약속을 확인한다.
"""
import json
import re
from pathlib import Path

import yaml

from app.domain.guest import service

KRATOS_DIR = Path(__file__).resolve().parents[3] / "dev" / "kratos"


def _overlay() -> dict:
    return yaml.safe_load((KRATOS_DIR / "kratos.guest.yml").read_text())


def test_login_hooks_are_guest_web_hook_then_require_verified_address():
    hooks = _overlay()["selfservice"]["flows"]["login"]["after"]["password"]["hooks"]
    assert [h["hook"] for h in hooks] == ["web_hook", "require_verified_address"]
    assert hooks[0]["config"]["url"].endswith("/internal/kratos/hooks/login")
    assert hooks[0]["config"]["response"]["parse"] is True
    assert hooks[0]["config"]["auth"]["config"]["name"] == "X-Kratos-Hook-Key"


def test_login_hook_body_cancels_every_non_guest():
    body = (KRATOS_DIR / "hook.login.jsonnet").read_text()
    assert "if ctx.identity.schema_id != 'guest' then error 'cancel'" in body


def test_settings_hooks_keep_revoke_active_sessions():
    after = _overlay()["selfservice"]["flows"]["settings"]["after"]
    assert [h["hook"] for h in after["password"]["hooks"]] == ["web_hook", "revoke_active_sessions"]
    for method in ("profile", "password", "oidc"):
        assert after[method]["hooks"][0]["config"]["url"].endswith(f"/internal/kratos/hooks/settings/{method}")


def test_guest_handle_is_verifiable_but_not_recoverable():
    handle = json.loads((KRATOS_DIR / "guest.schema.json").read_text())["properties"]["traits"]["properties"]["handle"]
    assert handle["format"] == "email"
    kratos = handle["ory.sh/kratos"]
    assert kratos["credentials"]["password"]["identifier"] is True
    assert kratos["verification"] == {"via": "email"}
    assert "recovery" not in kratos


def test_handle_domain_is_reserved_invalid_tld():
    assert service.GUEST_HANDLE_DOMAIN.endswith(".invalid")


def test_claims_mapper_takes_email_only_from_email_trait():
    """게스트의 handle(인증된 주소)이 email 클레임이 되지 않는다"""
    mapper = (KRATOS_DIR / "api-jwt.claims.jsonnet").read_text()
    code = "\n".join(line for line in mapper.splitlines() if not line.lstrip().startswith("//"))
    assert "local email = if 'email' in traits then traits.email else null;" in code
    assert "handle" not in code
    assert re.search(r"\[if email != null then 'email' else null\]: email", code)
    assert "schema_id: identity.schema_id" in code
