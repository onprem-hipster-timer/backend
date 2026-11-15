"""
Kratos가 비밀번호 해시를 계산하는 요청의 동시 실행 상한

Kratos(bcrypt cost 12)는 api 인스턴스 안의 사이드카라 쓸 수 있는 vCPU가 정해져 있다. 해시를 계산하는 요청이 몰리면
Kratos의 다른 응답(세션 확인, JWT 발급)까지 느려지므로, backend가 그런 요청을 Kratos로 넘기기 전에 자리를 잡는다.

- 회원과 게스트의 자리는 따로다. 한쪽이 몰려도 다른 쪽은 막히지 않는다
- 자리는 WAIT_SECONDS까지 기다리고, 그 안에 나지 않으면 KratosBusyError
- 자리는 프로세스 메모리에 있어 api가 한 프로세스일 때만 상한이 맞다
"""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# 동시에 Kratos로 넘기는 해시 요청 수. bcrypt cost 12 한 번이 vCPU 하나를 수백 ms 쓴다
MEMBER_SLOTS = 2
GUEST_SLOTS = 1
# 자리를 기다리는 최대 시간(초)과, 자리가 없을 때 클라이언트에 알려 줄 재시도 대기(초)
WAIT_SECONDS = 2.0
RETRY_AFTER_SECONDS = 1


class KratosBusyError(Exception):
    """기다리는 동안 자리가 나지 않았다"""


class Slots:
    def __init__(self, size: int):
        self._semaphore = asyncio.Semaphore(size)

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        """자리를 잡고 블록이 끝나면 돌려준다. WAIT_SECONDS 안에 못 잡으면 KratosBusyError"""
        try:
            await asyncio.wait_for(self._semaphore.acquire(), WAIT_SECONDS)
        except TimeoutError:
            raise KratosBusyError() from None
        try:
            yield
        finally:
            self._semaphore.release()


member_slots = Slots(MEMBER_SLOTS)
guest_slots = Slots(GUEST_SLOTS)
