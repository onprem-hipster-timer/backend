"""
Kratos courier 잡 온디맨드 실행

Kratos 메일은 상시 프로세스가 아니라 Cloud Run 잡 kratos-courier가 보낸다 (infra docs/scale-to-zero.md).
메일을 큐에 넣는 /auth 요청이 성공하면 응답하기 전에 그 잡의 실행을 요청하고, 접수까지만 기다린다.
실행 중인 courier와의 중복, 멈춘 메시지 복구는 잡이 스스로 처리한다.

응답 뒤에는 CPU가 보장되지 않아(cpu_idle) 백그라운드로 미루지 않는다. 실패해도 요청을 실패시키지 않는다.
KRATOS_COURIER_JOB이 비어 있으면 아무것도 하지 않는다.
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RUN_API = "https://run.googleapis.com/v2"
TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


async def start() -> None:
    """kratos-courier 잡 실행을 요청한다. 실패는 로그로만 남긴다."""
    if not settings.KRATOS_COURIER_JOB:
        return
    try:
        async with _make_client() as client:
            token = await client.get(TOKEN_URL, headers={"Metadata-Flavor": "Google"})
            token.raise_for_status()
            response = await client.post(
                f"{RUN_API}/{settings.KRATOS_COURIER_JOB}:run",
                headers={"Authorization": f"Bearer {token.json()['access_token']}"},
                json={},
            )
            response.raise_for_status()
    except Exception:
        logger.exception("courier 잡 실행 요청 실패")
