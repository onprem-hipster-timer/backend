"""
Cloudflare Turnstile 서버 확인 (siteverify)

게스트 단계 요청에서 클라이언트가 위젯에서 받은 토큰을 TURNSTILE_SECRET_KEY로 확인한다.
부르는 곳은 인터셉터 한 곳이다 (app/middleware/guest_gate.py). 클라이언트 IP는 보내지 않는다.

- 토큰은 한 번만 받는다. siteverify를 부르기 전에 토큰 해시를 기록하고, 이미 기록한 토큰이면 부르지 않고 거절한다.
  확인에 실패하거나 확인할 수 없어도 기록은 지우지 않는다. 기록은 프로세스 메모리라 api가 한 프로세스일 때만 맞다
- Cloudflare 테스트용 비밀 키(TESTING_SECRET_KEYS)로는 기록하지 않는다. 테스트 키의 위젯은 늘 같은 더미 토큰을 준다

테스트: tests/domain/guest/test_turnstile.py
"""
import hashlib
import logging
import time
from collections import OrderedDict

import httpx

import app.core.config as app_config

logger = logging.getLogger(__name__)

# Cloudflare 테스트용 비밀 키: 항상 통과, 항상 실패, 이미 쓴 토큰
TESTING_SECRET_KEYS = frozenset({
    "1x0000000000000000000000000000000AA",
    "2x0000000000000000000000000000000AA",
    "3x0000000000000000000000000000000AA",
})
# 토큰 유효 시간(300초)에 시계 차이 여유를 더한 기록 유지 시간
SPENT_TOKEN_TTL_SECONDS = 330
# 기록 수 상한. 넘치면 가장 오래된 기록부터 지운다. 오래된 토큰의 재사용은 Cloudflare siteverify가 거절한다
SPENT_TOKEN_MAX = 50_000


class TurnstileUnavailableError(Exception):
    """확인 엔드포인트에 닿지 않거나 200이 아니거나 응답을 읽을 수 없음"""


class _SpentTokens:
    """한 번 받은 토큰의 해시와 만료 시각 (기록 순서 = 만료 순서)"""

    def __init__(self):
        self._expiry: OrderedDict[bytes, float] = OrderedDict()

    def claim(self, token: str) -> bool:
        """처음 보는 토큰이면 기록하고 True, 이미 기록한 토큰이면 False.

        await가 없어 같은 토큰으로 동시에 온 요청 중 하나만 True를 받는다.
        """
        now = time.monotonic()
        while self._expiry and next(iter(self._expiry.values())) <= now:
            self._expiry.popitem(last=False)
        digest = hashlib.sha256(token.encode()).digest()
        if digest in self._expiry:
            return False
        if len(self._expiry) >= SPENT_TOKEN_MAX:
            self._expiry.popitem(last=False)
        self._expiry[digest] = now + SPENT_TOKEN_TTL_SECONDS
        return True


_spent_tokens = _SpentTokens()


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0))


async def verify(token: str) -> bool:
    """토큰이 통과하면 True. 통과하지 못했거나 이미 받은 토큰이면 False. 확인할 수 없으면 TurnstileUnavailableError"""
    settings = app_config.settings
    if settings.TURNSTILE_SECRET_KEY not in TESTING_SECRET_KEYS and not _spent_tokens.claim(token):
        logger.warning("이미 받은 Turnstile 토큰을 거절함")
        return False
    try:
        async with _make_client() as client:
            response = await client.post(
                settings.TURNSTILE_VERIFY_URL,
                data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token},
            )
    except httpx.HTTPError as exc:
        raise TurnstileUnavailableError("siteverify request failed") from exc
    if response.status_code != 200:
        raise TurnstileUnavailableError(f"siteverify status={response.status_code}")
    try:
        success = response.json()["success"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TurnstileUnavailableError("siteverify response unreadable") from exc
    if not isinstance(success, bool):
        raise TurnstileUnavailableError("siteverify response unreadable")
    return success
