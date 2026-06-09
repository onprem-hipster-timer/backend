# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Hipster Timer Project Contributors

"""
DB Keep-Alive 백그라운드 태스크

유휴 상태일 때 데이터베이스가 자동으로 일시 정지되거나 연결이 끊기는 것을
막기 위해, 주기적으로 가벼운 쿼리(SELECT 1)를 실행한다.

- 일부 무료/서버리스 DB 호스팅은 일정 시간 트래픽이 없으면 인스턴스를
  일시 정지시킨다. 이 태스크는 그런 정지를 방지하는 용도로 사용할 수 있다.
- 주기는 settings.DB_KEEPALIVE_INTERVAL_SECONDS(초)로 설정하며,
  0 이하이면 태스크가 동작하지 않는다(비활성화).

책임:
- 스케줄링 (주기적 ping)
- 상태 관리 (is_running)
"""
import asyncio
import logging

from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_async_db

logger = logging.getLogger(__name__)


class DatabaseKeepAliveTask:
    """
    DB 연결 유지를 위한 주기적 ping 태스크

    스케줄링만 담당하며, 매 주기마다 SELECT 1을 실행한다.
    """

    def __init__(self, interval_seconds: int | None = None):
        """
        Args:
            interval_seconds: ping 주기(초). None이면 설정값을 사용한다.
                              0 이하이면 비활성화된다.
        """
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.DB_KEEPALIVE_INTERVAL_SECONDS
        )
        self.is_running = False

    @property
    def enabled(self) -> bool:
        """주기가 0보다 클 때만 활성화"""
        return self.interval_seconds > 0

    async def _ping(self) -> None:
        """가벼운 쿼리로 DB 연결을 깨운다."""
        async with get_async_db() as session:
            await session.execute(text("SELECT 1"))

    async def run(self) -> None:
        """
        주기적 keep-alive 실행 (lifespan startup 후 실행)

        - enabled가 False면 즉시 종료한다.
        - 시작 시점에는 DB가 막 초기화되므로 먼저 대기 후 ping한다.
        - ping 실패는 경고만 남기고 태스크를 계속 유지한다
          (일시적 DB 장애가 keep-alive를 영구 중단시키지 않도록).
        - asyncio.CancelledError 시 정상 종료한다.
        """
        if not self.enabled:
            logger.info(
                "ℹ️  DB keep-alive disabled (DB_KEEPALIVE_INTERVAL_SECONDS=%d)",
                self.interval_seconds,
            )
            return

        self.is_running = True
        logger.info(
            "✅ DB keep-alive task started (interval=%ds)",
            self.interval_seconds,
        )

        try:
            while self.is_running:
                await asyncio.sleep(self.interval_seconds)

                if not self.is_running:
                    break

                try:
                    await self._ping()
                    logger.debug("DB keep-alive ping OK")
                except Exception as e:
                    # 일시적 장애는 무시하고 다음 주기에 재시도
                    logger.warning(
                        "DB keep-alive ping failed (will retry next interval): %s",
                        str(e),
                    )

        except asyncio.CancelledError:
            logger.info("DB keep-alive task cancelled (shutdown)")
            self.is_running = False
            raise
