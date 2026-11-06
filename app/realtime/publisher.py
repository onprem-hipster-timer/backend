"""
실시간 publisher 어댑터

커밋 후 큐(app/shared/uow.py)의 항목 `{"users": set[str], "message": dict}`를
받는 사람의 소켓으로 보낸다. REALTIME_BACKEND로 고른다.

- inprocess (기본): 이 프로세스의 `/v1/ws/timers` 연결(ConnectionManager)로 보낸다
- cloudflare: realtime Worker의 `POST /realtime/push`로 보낸다

publish는 커밋 직후 동기적으로 불린다(대개 스레드풀 워커). 어떤 경우에도 예외를 던지지 않는다.
놓친 메시지는 클라이언트가 (재)연결 직후 REST로 다시 맞춘다.

계약과 설정: docs/development/realtime-adapter.ko.md
테스트: tests/realtime/test_publisher.py
"""
import asyncio
import logging
import threading
import time
from typing import Protocol

import httpx

from app.core import config as app_config
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

# Worker가 한 요청에 받는 최대 사용자 수 (넘으면 413)
PUSH_MAX_USERS = 40
# 이벤트 하나를 push하는 데 쓰는 시간 상한 (재시도 포함). 커밋 뒤 응답 전에 실행되므로 짧게 둔다
PUSH_DEADLINE_SECONDS = 2.0


class Publisher(Protocol):
    def publish(self, users: set[str], message: dict) -> None: ...

    def close(self) -> None: ...


class InProcessPublisher:
    """같은 프로세스의 WebSocket 연결로 보낸다. loop는 연결을 처리하는 이벤트 루프"""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._tasks: set[asyncio.Task] = set()

    def publish(self, users: set[str], message: dict) -> None:
        coro = self._send(set(users), message)
        try:
            if _running_loop() is self._loop:
                task = self._loop.create_task(coro)
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            else:
                asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError:
            # 루프가 닫힌 뒤(종료 중)
            coro.close()
            logger.warning("realtime_publish_dropped id=%s users=%d", message.get("id"), len(users))

    async def _send(self, users: set[str], message: dict) -> None:
        try:
            for user in users:
                await connection_manager.send_to_user(user, message)
        except Exception:
            logger.exception("realtime_publish_failed id=%s", message.get("id"))

    def close(self) -> None:
        pass


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _make_client() -> httpx.Client:
    return httpx.Client()


class CloudflarePublisher:
    """
    realtime Worker로 push한다.

    - `Authorization: Bearer <secret>`, 본문 `{"users": [...], "message": {...}}`, 성공은 2xx(202)
    - users는 PUSH_MAX_USERS명씩 나눠 보낸다
    - 연결 오류·5xx는 한 번 재시도하고 4xx는 재시도하지 않는다
    - 이벤트당 PUSH_DEADLINE_SECONDS 안에서만 시도한다 (각 시도의 timeout = 남은 시간)
    - 실패는 `realtime_push_failed` 로그만 남긴다
    """

    def __init__(self, url: str, secret: str):
        self._url = url
        self._secret = secret
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    def _http(self) -> httpx.Client:
        with self._lock:
            if self._client is None:
                self._client = _make_client()
            return self._client

    def publish(self, users: set[str], message: dict) -> None:
        if not self._url or not users:
            return
        try:
            deadline = time.monotonic() + PUSH_DEADLINE_SECONDS
            ordered = sorted(users)
            for start in range(0, len(ordered), PUSH_MAX_USERS):
                self._push(ordered[start:start + PUSH_MAX_USERS], message, deadline)
        except Exception:
            logger.exception("realtime_push_failed id=%s users=%d", message.get("id"), len(users))

    def _push(self, users: list[str], message: dict, deadline: float) -> None:
        status: int | None = None
        error: str | None = None
        for _ in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = "deadline"
                break
            try:
                response = self._http().post(
                    self._url,
                    json={"users": users, "message": message},
                    headers={"Authorization": f"Bearer {self._secret}"},
                    timeout=remaining,
                )
            except httpx.TransportError as exc:
                status, error = None, type(exc).__name__
                continue
            status, error = response.status_code, None
            if response.is_success:
                return
            if status < 500:
                break
        logger.warning(
            "realtime_push_failed id=%s users=%d status=%s error=%s",
            message.get("id"), len(users), status, error,
        )

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None


def create_publisher(loop: asyncio.AbstractEventLoop) -> Publisher:
    """REALTIME_BACKEND에 맞는 publisher (loop: inprocess가 쓸 이벤트 루프)"""
    settings = app_config.settings
    if settings.REALTIME_BACKEND == "cloudflare":
        return CloudflarePublisher(settings.REALTIME_PUSH_URL, settings.REALTIME_PUSH_SECRET)
    return InProcessPublisher(loop)


def as_after_commit_sink(publisher: Publisher):
    """커밋 후 큐 항목을 publisher로 넘기는 sink (app/shared/uow.py set_after_commit_sink)"""

    def sink(item: dict) -> None:
        publisher.publish(item["users"], item["message"])

    return sink
