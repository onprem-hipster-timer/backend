"""
실시간 publisher 테스트 (app/realtime/publisher.py)

- InProcessPublisher: 같은 루프·다른 스레드에서 불려도 ConnectionManager 연결로 보낸다
- CloudflarePublisher: httpx.MockTransport가 Worker 역할을 하고 받은 요청을 기록한다
"""
import asyncio
import json
import time

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.realtime import publisher as publisher_module
from app.realtime.publisher import CloudflarePublisher, InProcessPublisher, create_publisher
from app.websocket.manager import connection_manager

PUSH_URL = "https://api.example.com/realtime/push"
SECRET = "push-secret"
MESSAGE = {"id": "event-1", "type": "timer.updated", "from_user": "owner", "payload": {}}


# ============================================================
# InProcessPublisher
# ============================================================

class FakeWebSocket:
    def __init__(self):
        self.received: list[str] = []
        self.got_message = asyncio.Event()

    async def send_text(self, text: str) -> None:
        self.received.append(text)
        self.got_message.set()


@pytest_asyncio.fixture
async def sockets():
    """user-a, user-b의 가짜 연결을 connection_manager에 등록"""
    created = {"user-a": FakeWebSocket(), "user-b": FakeWebSocket()}
    for user, ws in created.items():
        await connection_manager.connect(ws, user)
    yield created
    for ws in created.values():
        await connection_manager.disconnect(ws)


@pytest.mark.asyncio
async def test_inprocess_sends_from_loop_thread(sockets):
    publisher = InProcessPublisher(asyncio.get_running_loop())

    publisher.publish({"user-a"}, MESSAGE)
    await asyncio.wait_for(sockets["user-a"].got_message.wait(), timeout=1)

    assert [json.loads(t) for t in sockets["user-a"].received] == [MESSAGE]
    assert sockets["user-b"].received == []


@pytest.mark.asyncio
async def test_inprocess_sends_from_worker_thread(sockets):
    publisher = InProcessPublisher(asyncio.get_running_loop())

    await asyncio.to_thread(publisher.publish, {"user-a", "user-b"}, MESSAGE)
    for ws in sockets.values():
        await asyncio.wait_for(ws.got_message.wait(), timeout=1)

    assert [json.loads(t) for t in sockets["user-b"].received] == [MESSAGE]


def test_inprocess_closed_loop_does_not_raise():
    loop = asyncio.new_event_loop()
    loop.close()

    InProcessPublisher(loop).publish({"user-a"}, MESSAGE)


# ============================================================
# CloudflarePublisher
# ============================================================

class Worker:
    """받은 요청을 기록하고 responses 순서대로 응답하는 가짜 Worker (비면 202)"""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: list = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self.responses.pop(0) if self.responses else 202
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result(request)
        return httpx.Response(result, json={})

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture
def worker(monkeypatch):
    worker = Worker()
    monkeypatch.setattr(
        publisher_module, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(worker))
    )
    return worker


@pytest.fixture
def cloudflare(worker):
    publisher = CloudflarePublisher(PUSH_URL, SECRET)
    yield publisher
    publisher.close()


def test_cloudflare_posts_bearer_and_body(cloudflare, worker):
    cloudflare.publish({"user-b", "user-a"}, MESSAGE)

    assert len(worker.requests) == 1
    request = worker.requests[0]
    assert request.method == "POST"
    assert str(request.url) == PUSH_URL
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert worker.bodies() == [{"users": ["user-a", "user-b"], "message": MESSAGE}]


def test_cloudflare_splits_users_by_40(cloudflare, worker):
    users = {f"user-{i:03d}" for i in range(85)}

    cloudflare.publish(users, MESSAGE)

    sent = [body["users"] for body in worker.bodies()]
    assert [len(chunk) for chunk in sent] == [40, 40, 5]
    assert sorted(sum(sent, [])) == sorted(users)
    assert all(body["message"] == MESSAGE for body in worker.bodies())


def test_cloudflare_retries_5xx_once(cloudflare, worker):
    worker.responses = [503, 202]

    cloudflare.publish({"user-a"}, MESSAGE)

    assert len(worker.requests) == 2


def test_cloudflare_retries_connection_error_once(cloudflare, worker):
    worker.responses = [httpx.ConnectError("down"), 202]

    cloudflare.publish({"user-a"}, MESSAGE)

    assert len(worker.requests) == 2


def test_cloudflare_gives_up_after_second_failure(cloudflare, worker, monkeypatch):
    logged = []
    monkeypatch.setattr(publisher_module.logger, "warning", lambda msg, *args: logged.append(msg % args))
    worker.responses = [503, 503, 202]

    cloudflare.publish({"user-a"}, MESSAGE)

    assert len(worker.requests) == 2
    assert logged == ["realtime_push_failed id=event-1 users=1 status=503 error=None"]


@pytest.mark.parametrize("status", [400, 401, 413])
def test_cloudflare_does_not_retry_4xx(cloudflare, worker, status):
    worker.responses = [status]

    cloudflare.publish({"user-a"}, MESSAGE)

    assert len(worker.requests) == 1


def test_cloudflare_stops_at_deadline(cloudflare, worker, monkeypatch):
    monkeypatch.setattr(publisher_module, "PUSH_DEADLINE_SECONDS", 0.05)

    def slow_failure(request):
        time.sleep(0.06)
        return httpx.Response(503)

    worker.responses = [slow_failure, 202]

    cloudflare.publish({f"user-{i:03d}" for i in range(45)}, MESSAGE)

    # 첫 묶음의 첫 시도에서 기한을 넘겼으므로 재시도도, 다음 묶음도 보내지 않는다
    assert len(worker.requests) == 1


def test_cloudflare_without_url_does_not_call(worker):
    CloudflarePublisher("", SECRET).publish({"user-a"}, MESSAGE)

    assert worker.requests == []


def test_cloudflare_never_raises(cloudflare, worker):
    worker.responses = [RuntimeError("bug"), RuntimeError("bug")]

    cloudflare.publish({"user-a"}, MESSAGE)


def test_cloudflare_close_and_reuse(cloudflare, worker):
    cloudflare.publish({"user-a"}, MESSAGE)
    cloudflare.close()
    cloudflare.publish({"user-a"}, MESSAGE)

    assert len(worker.requests) == 2


# ============================================================
# 선택과 설정
# ============================================================

@pytest.mark.parametrize("backend, expected", [
    ("inprocess", InProcessPublisher),
    ("cloudflare", CloudflarePublisher),
])
def test_create_publisher_follows_setting(monkeypatch, backend, expected):
    import app.core.config as config_module

    monkeypatch.setattr(
        config_module,
        "settings",
        Settings(REALTIME_BACKEND=backend, REALTIME_PUSH_URL=PUSH_URL, REALTIME_PUSH_SECRET=SECRET),
    )
    loop = asyncio.new_event_loop()
    try:
        assert isinstance(create_publisher(loop), expected)
    finally:
        loop.close()


@pytest.mark.parametrize("url, secret", [("", SECRET), (PUSH_URL, ""), ("", "")])
def test_production_cloudflare_requires_url_and_secret(url, secret):
    with pytest.raises(ValueError, match="REALTIME_PUSH"):
        Settings(
            ENVIRONMENT="production",
            REALTIME_BACKEND="cloudflare",
            REALTIME_PUSH_URL=url,
            REALTIME_PUSH_SECRET=secret,
        )


def test_development_cloudflare_allows_empty_url():
    assert Settings(REALTIME_BACKEND="cloudflare").REALTIME_PUSH_URL == ""
