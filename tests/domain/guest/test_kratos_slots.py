"""Kratos가 비밀번호 해시를 계산하는 요청의 동시 실행 상한 (app/core/kratos_slots.py)

가짜 Kratos가 해시 요청을 붙잡아 두는 동안 같은 자리를 쓰는 요청이 어떻게 되는지 본다.
"""
import asyncio
import json
import uuid

import httpx
import pytest

from app.core import kratos_slots
from app.domain.guest.host import GuestHostStatus
from tests.domain.guest.helpers import guest_rows, make_guest

LOGIN = "/auth/self-service/login"


@pytest.fixture
def resource(host):
    resource_id = uuid.uuid4()
    host.statuses[resource_id] = GuestHostStatus.OPEN
    return resource_id


@pytest.fixture
def slots(monkeypatch):
    """회원·게스트 자리 하나씩, 짧은 대기"""
    monkeypatch.setattr(kratos_slots, "member_slots", kratos_slots.Slots(1))
    monkeypatch.setattr(kratos_slots, "guest_slots", kratos_slots.Slots(1))
    monkeypatch.setattr(kratos_slots, "WAIT_SECONDS", 0.05)


class Gate:
    """identifier가 held인 로그인 제출을 release 전까지 붙잡는 가짜 Kratos"""

    def __init__(self, kratos, held: str):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        public = kratos.public

        async def gated_public(request):
            if request.url.path == "/self-service/login" and json.loads(request.content).get("identifier") == held:
                self.entered.set()
                await self.release.wait()
            return await public(request)

        kratos.public = gated_public


def _client():
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _login(client, identifier, password="1234"):
    return await client.post(
        f"{LOGIN}?flow={uuid.uuid4()}",
        json={"method": "password", "identifier": identifier, "password": password},
        headers={"X-Turnstile-Token": "t"},
    )


def _handle(kratos, guest) -> str:
    return kratos.identities[guest.identity_id]["traits"]["handle"]


@pytest.mark.asyncio
async def test_member_submit_waits_then_gets_429_while_slot_is_held(guest_client, kratos, slots):
    gate = Gate(kratos, held="first@example.com")
    async with _client() as client:
        first = asyncio.create_task(_login(client, "first@example.com"))
        await gate.entered.wait()

        second = await _login(client, "second@example.com")

        assert second.status_code == 429
        assert second.headers["Retry-After"] == "1"
        gate.release.set()
        assert (await first).status_code != 429
        assert (await _login(client, "second@example.com")).status_code != 429


@pytest.mark.asyncio
async def test_held_guest_slot_does_not_block_member_submits(guest_client, kratos, slots, resource):
    guest = make_guest(kratos, resource, name="민수")
    gate = Gate(kratos, held=_handle(kratos, guest))
    async with _client() as client:
        first = asyncio.create_task(_login(client, _handle(kratos, guest)))
        await gate.entered.wait()

        assert (await _login(client, "member@example.com")).status_code != 429
        other_guest = make_guest(kratos, resource, name="철수")
        assert (await _login(client, _handle(kratos, other_guest))).status_code == 429
        gate.release.set()
        assert (await first).status_code == 200


@pytest.mark.asyncio
async def test_held_guest_slot_refuses_guest_creation(guest_client, kratos, slots, resource):
    guest = make_guest(kratos, resource, name="민수")
    gate = Gate(kratos, held=_handle(kratos, guest))
    body = {"resource_type": "meeting", "resource_id": str(resource), "name": "영희", "password": "1", "turnstile_token": "t"}
    async with _client() as client:
        first = asyncio.create_task(_login(client, _handle(kratos, guest)))
        await gate.entered.wait()

        r = await client.post("/v1/guests", json=body)

        assert r.status_code == 429
        assert r.json()["error_type"] == "GuestServiceBusyError"
        assert [g.name for g in guest_rows()] == ["민수"]
        gate.release.set()
        await first
        assert (await client.post("/v1/guests", json=body)).status_code == 201


@pytest.mark.asyncio
async def test_submits_that_do_not_hash_are_not_held_back(guest_client, kratos, slots):
    gate = Gate(kratos, held="first@example.com")
    async with _client() as client:
        first = asyncio.create_task(_login(client, "first@example.com"))
        await gate.entered.wait()

        recovery = await client.post(
            f"/auth/self-service/recovery?flow={uuid.uuid4()}", json={"method": "code", "email": "a@example.com"}
        )
        whoami = await client.get("/auth/sessions/whoami")

        assert recovery.status_code != 429
        assert whoami.status_code != 429
        gate.release.set()
        await first


@pytest.mark.asyncio
async def test_slot_is_returned_when_kratos_is_unreachable(guest_client, kratos, slots):
    async with _client() as client:
        kratos.down.add("public")
        assert (await _login(client, "member@example.com")).status_code == 502
        kratos.down.discard("public")

        assert (await _login(client, "member@example.com")).status_code != 429
