"""
Kratos courier 잡 온디맨드 실행 테스트

Cloud Run Admin API와 메타데이터 서버는 httpx.MockTransport로 흉내 낸다.
"""
import logging

import httpx
import pytest

from app.core import courier
from app.core.config import Settings

COURIER_JOB = "projects/p/locations/r/jobs/kratos-courier"


class FakeCloudRun:
    """메타데이터 토큰과 잡 실행에 답하고 받은 요청을 기록한다"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.run_status = 200

    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3599})
        if request.method == "POST" and request.url.path == f"/v2/{COURIER_JOB}:run":
            return httpx.Response(self.run_status, json={"name": "operations/1"})
        return httpx.Response(404)


@pytest.fixture
def cloud_run(monkeypatch):
    fake = FakeCloudRun()
    monkeypatch.setattr(courier, "settings", Settings(KRATOS_COURIER_JOB=COURIER_JOB))
    monkeypatch.setattr(courier, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return fake


@pytest.mark.asyncio
async def test_start_runs_courier_job_with_metadata_token(cloud_run):
    await courier.start()

    assert cloud_run.calls() == [
        ("GET", "/computeMetadata/v1/instance/service-accounts/default/token"),
        ("POST", f"/v2/{COURIER_JOB}:run"),
    ]
    assert cloud_run.requests[0].headers["metadata-flavor"] == "Google"
    assert cloud_run.requests[1].headers["authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_every_start_requests_a_run(cloud_run):
    await courier.start()
    await courier.start()

    assert cloud_run.calls().count(("POST", f"/v2/{COURIER_JOB}:run")) == 2


@pytest.mark.asyncio
async def test_no_courier_job_configured_does_nothing(cloud_run, monkeypatch):
    monkeypatch.setattr(courier, "settings", Settings())

    await courier.start()

    assert cloud_run.requests == []


@pytest.mark.asyncio
async def test_rejected_run_is_logged_not_raised(cloud_run, caplog):
    cloud_run.run_status = 403

    with caplog.at_level(logging.ERROR, logger="app.core.courier"):
        await courier.start()

    assert "courier 잡 실행 요청 실패" in caplog.text


@pytest.mark.asyncio
async def test_unreachable_metadata_server_is_logged_not_raised(cloud_run, monkeypatch, caplog):
    def refuse(request):
        raise httpx.ConnectError("metadata server unreachable", request=request)

    monkeypatch.setattr(courier, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(refuse)))

    with caplog.at_level(logging.ERROR, logger="app.core.courier"):
        await courier.start()

    assert "courier 잡 실행 요청 실패" in caplog.text
