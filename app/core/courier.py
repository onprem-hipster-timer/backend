"""
Kratos courier 잡 온디맨드 실행

Kratos 메일은 상시 프로세스가 아니라 Cloud Run 잡 kratos-courier가 보낸다 (infra docs/scale-to-zero.md).
메일을 큐에 넣는 /auth 요청이 성공하면 백그라운드에서 다음을 한다.

1. kratos-courier가 이미 실행 중이면 아무것도 하지 않는다. 실행 중에 requeue하면 메일이 두 번 나갈 수 있다.
2. courier-requeue 잡을 실행하고 성공할 때까지 기다린다. 죽은 courier가 processing에 남긴 메시지를 되돌린다.
3. kratos-courier 잡을 실행한다. 끝날 때까지 기다리지 않는다.

요청 응답을 막지 않고, 실패해도 요청을 실패시키지 않는다. 인스턴스가 최대 1개라 디바운스는 메모리 값으로 충분하다.
KRATOS_COURIER_JOB이 비어 있으면 아무것도 하지 않는다.
"""
import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RUN_API = "https://run.googleapis.com/v2"
TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
DEBOUNCE_SECONDS = 30
POLL_SECONDS = 5
# requeue 잡의 태스크 타임아웃 300초 x 2회(재시도 1회)에 콜드 스타트 여유
REQUEUE_TIMEOUT_SECONDS = 900

_last_trigger = float("-inf")
_task: asyncio.Task | None = None


def trigger() -> None:
    """courier 실행을 백그라운드로 시작한다. 이전 실행이 진행 중이거나 디바운스 안이면 건너뛴다."""
    global _last_trigger, _task
    if not settings.KRATOS_COURIER_JOB:
        return
    now = time.monotonic()
    if (_task is not None and not _task.done()) or now - _last_trigger < DEBOUNCE_SECONDS:
        return
    _last_trigger = now
    _task = asyncio.create_task(_run())


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


async def _run() -> None:
    try:
        async with _make_client() as client:
            token = (await _get_json(client, TOKEN_URL, {"Metadata-Flavor": "Google"}))["access_token"]
            auth = {"Authorization": f"Bearer {token}"}

            job = await _get_json(client, f"{RUN_API}/{settings.KRATOS_COURIER_JOB}", auth)
            latest = job.get("latestCreatedExecution")
            if latest and "completionTime" not in latest:
                logger.info("kratos-courier가 실행 중이라 건너뜀")
                return

            if settings.COURIER_REQUEUE_JOB:
                operation = await _post_json(client, f"{RUN_API}/{settings.COURIER_REQUEUE_JOB}:run", auth)
                if not await _wait_succeeded(client, operation["metadata"]["name"], auth):
                    logger.error("courier-requeue가 성공하지 않아 kratos-courier를 실행하지 않음")
                    return

            await _post_json(client, f"{RUN_API}/{settings.KRATOS_COURIER_JOB}:run", auth)
            logger.info("kratos-courier 실행")
    except Exception:
        logger.exception("courier 잡 실행 실패")


async def _wait_succeeded(client: httpx.AsyncClient, execution_name: str, auth: dict) -> bool:
    """execution이 끝날 때까지 기다리고 성공 여부를 돌려준다 (태스크 1개짜리 잡 기준)."""
    deadline = time.monotonic() + REQUEUE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        execution = await _get_json(client, f"{RUN_API}/{execution_name}", auth)
        if "completionTime" in execution:
            return execution.get("succeededCount", 0) > 0
        await asyncio.sleep(POLL_SECONDS)
    return False


async def _get_json(client: httpx.AsyncClient, url: str, headers: dict) -> dict:
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


async def _post_json(client: httpx.AsyncClient, url: str, headers: dict) -> dict:
    response = await client.post(url, headers=headers, json={})
    response.raise_for_status()
    return response.json()
