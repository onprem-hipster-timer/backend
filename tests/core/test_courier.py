"""
Kratos courier 잡 온디맨드 실행 테스트

Cloud Run Admin API와 메타데이터 서버는 httpx.MockTransport로 흉내 낸다.
"""
import logging

import httpx
import pytest

from app.core import courier
from app.core.config import Settings

REQUEUE_JOB = "projects/p/locations/r/jobs/courier-requeue"
COURIER_JOB = "projects/p/locations/r/jobs/kratos-courier"
REQUEUE_EXECUTION = f"{REQUEUE_JOB}/executions/courier-requeue-abc"


class FakeCloudRun:
    """메타데이터 토큰, 잡 조회·실행, execution 조회에 답하고 받은 요청을 기록한다"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.courier_latest: dict | None = {"name": "old", "completionTime": "2026-11-04T00:00:00Z"}
        # requeue execution 조회 응답을 차례로 돌려준다 (마지막 값은 반복)
        self.requeue_states = [{}, {"completionTime": "2026-11-04T00:01:00Z", "succeededCount": 1}]

    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3599})
        if request.method == "GET" and path == f"/v2/{COURIER_JOB}":
            return httpx.Response(200, json={"latestCreatedExecution": self.courier_latest} if self.courier_latest else {})
        if request.method == "POST" and path == f"/v2/{REQUEUE_JOB}:run":
            return httpx.Response(200, json={"name": "operations/1", "metadata": {"name": REQUEUE_EXECUTION}})
        if request.method == "GET" and path == f"/v2/{REQUEUE_EXECUTION}":
            state = self.requeue_states.pop(0) if len(self.requeue_states) > 1 else self.requeue_states[0]
            return httpx.Response(200, json={"name": REQUEUE_EXECUTION, **state})
        if request.method == "POST" and path == f"/v2/{COURIER_JOB}:run":
            return httpx.Response(200, json={"name": "operations/2", "metadata": {"name": f"{COURIER_JOB}/executions/x"}})
        return httpx.Response(404)


@pytest.fixture
def cloud_run(monkeypatch):
    fake = FakeCloudRun()
    monkeypatch.setattr(courier, "settings", Settings(COURIER_REQUEUE_JOB=REQUEUE_JOB, KRATOS_COURIER_JOB=COURIER_JOB))
    monkeypatch.setattr(courier, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(courier, "POLL_SECONDS", 0)
    monkeypatch.setattr(courier, "_last_trigger", float("-inf"))
    monkeypatch.setattr(courier, "_task", None)
    return fake


async def _trigger_and_wait() -> None:
    courier.trigger()
    if courier._task is not None:
        await courier._task


@pytest.mark.asyncio
async def test_requeue_succeeds_then_courier_runs(cloud_run):
    await _trigger_and_wait()

    assert cloud_run.calls() == [
        ("GET", "/computeMetadata/v1/instance/service-accounts/default/token"),
        ("GET", f"/v2/{COURIER_JOB}"),
        ("POST", f"/v2/{REQUEUE_JOB}:run"),
        ("GET", f"/v2/{REQUEUE_EXECUTION}"),
        ("GET", f"/v2/{REQUEUE_EXECUTION}"),
        ("POST", f"/v2/{COURIER_JOB}:run"),
    ]
    assert cloud_run.requests[0].headers["metadata-flavor"] == "Google"
    assert all(r.headers["authorization"] == "Bearer tok" for r in cloud_run.requests[1:])


@pytest.mark.asyncio
async def test_first_run_without_previous_execution(cloud_run):
    cloud_run.courier_latest = None

    await _trigger_and_wait()

    assert ("POST", f"/v2/{COURIER_JOB}:run") in cloud_run.calls()


@pytest.mark.asyncio
async def test_skips_both_jobs_while_courier_is_running(cloud_run):
    cloud_run.courier_latest = {"name": "running"}  # completionTime 없음

    await _trigger_and_wait()

    assert [m for m, _ in cloud_run.calls()] == ["GET", "GET"]


@pytest.mark.asyncio
async def test_courier_not_started_when_requeue_fails(cloud_run, caplog):
    cloud_run.requeue_states = [{"completionTime": "2026-11-04T00:01:00Z", "succeededCount": 0, "failedCount": 1}]

    with caplog.at_level(logging.ERROR, logger="app.core.courier"):
        await _trigger_and_wait()

    assert ("POST", f"/v2/{COURIER_JOB}:run") not in cloud_run.calls()
    assert "courier-requeue" in caplog.text


@pytest.mark.asyncio
async def test_courier_runs_directly_without_requeue_job(cloud_run, monkeypatch):
    monkeypatch.setattr(courier, "settings", Settings(KRATOS_COURIER_JOB=COURIER_JOB))

    await _trigger_and_wait()

    assert ("POST", f"/v2/{REQUEUE_JOB}:run") not in cloud_run.calls()
    assert ("POST", f"/v2/{COURIER_JOB}:run") in cloud_run.calls()


@pytest.mark.asyncio
async def test_no_courier_job_configured_does_nothing(cloud_run, monkeypatch):
    monkeypatch.setattr(courier, "settings", Settings())

    await _trigger_and_wait()

    assert courier._task is None
    assert cloud_run.requests == []


@pytest.mark.asyncio
async def test_debounce_skips_repeated_triggers(cloud_run, monkeypatch):
    courier.trigger()
    first = courier._task
    courier.trigger()  # 진행 중
    assert courier._task is first
    await first

    courier.trigger()  # 끝났지만 디바운스 안
    assert courier._task is first

    monkeypatch.setattr(courier, "_last_trigger", courier._last_trigger - courier.DEBOUNCE_SECONDS - 1)
    courier.trigger()
    assert courier._task is not first
    await courier._task
    assert cloud_run.calls().count(("POST", f"/v2/{COURIER_JOB}:run")) == 2


@pytest.mark.asyncio
async def test_errors_are_logged_not_raised(cloud_run, monkeypatch, caplog):
    def refuse(request):
        raise httpx.ConnectError("metadata server unreachable", request=request)

    monkeypatch.setattr(courier, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(refuse)))

    with caplog.at_level(logging.ERROR, logger="app.core.courier"):
        await _trigger_and_wait()

    assert "courier 잡 실행 실패" in caplog.text
