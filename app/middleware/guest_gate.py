"""
게스트 관문 (인터셉터)

/auth 제출(프록시 라우트가 받는 메서드 중 GET 밖)은 프록시(app/api/auth_proxy.py)보다 먼저 여기서 본문을 한 번 읽고
다음을 거친다. 읽은 것은 request.state.auth_submission으로 넘기고, 프록시는 그 URL·본문으로 Kratos에 보낸다.

1. 제출 요청 한도 (app/ratelimit/config.py의 AUTH_* 규칙, 넘으면 429). 설정 밖의 제출은 IP 단위로,
   로그인·가입·인증·복구 제출은 같은 IP에서 같은 식별자(로그인 식별자, 이메일) 단위로도 센다
2. 프록시의 제출 검사 (inspect_submission: 쿼리 문자열, 설정 제출의 세션)
3. 설정 제출은 IP로 세지 않고, 검사를 통과한 세션의 identity 단위로 센다

경로는 라우터와 같은 기준(라우트 경로 정규식, get_route_path)으로 가린다.
CORS 안쪽에 둔다. 거절 응답에도 CORS 헤더가 붙고, preflight는 CORS가 답한다.

테스트: tests/domain/guest/test_rate_limits.py, tests/test_auth_proxy.py
"""
import hashlib
import logging
import unicodedata

from starlette._utils import get_route_path
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import auth_proxy
from app.core import config as app_config
from app.ratelimit.config import (
    AUTH_SETTINGS_PER_IDENTITY,
    AUTH_SUBMIT_METHODS,
    AUTH_SUBMIT_PER_IDENTIFIER,
    AUTH_SUBMIT_PER_IP,
    RateLimitRule,
)
from app.ratelimit.limiter import get_limiter
from app.ratelimit.middleware import client_ip_key, rate_limited_response

logger = logging.getLogger(__name__)

_AUTH_PROXY_PATH, _, _ = compile_path(auth_proxy.PROXY_PATH)


def _identifier_key(ip_key: str, submit_path: str, identifier: object) -> str | None:
    """같은 IP·제출 경로·식별자의 한도 키. 식별자가 없으면 None.

    문자열은 NFKC·앞뒤 공백 제거·casefold로 맞춘다. 읽을 수 없거나 문자열이 아닌 값은 IP·경로마다 한 칸으로 센다.
    키에는 식별자 대신 해시를 둔다.
    """
    if identifier is None:
        return None
    normalized = unicodedata.normalize("NFKC", identifier).strip().casefold() if isinstance(identifier, str) else ""
    digest = hashlib.sha256(f"{submit_path}\n{normalized}".encode()).hexdigest()
    return f"{ip_key}:identifier:{digest}"


async def _rate_limit_refusal(key: str, method: str, rule: RateLimitRule) -> Response | None:
    """key로 한 번 센다. 한도 안이면 None, 넘으면 429 응답"""
    result = await get_limiter().check_and_record(key, method, rule)
    if result.allowed:
        return None
    logger.warning(
        f"Rate limit exceeded: path={rule.path_pattern}, count={result.current_count}/{result.max_requests}"
    )
    return rate_limited_response(result)


async def _submit_rate_limit_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """설정 밖의 제출을 IP 단위로 세고, 로그인·가입·인증·복구 제출은 같은 IP의 같은 식별자 단위로도 센다"""
    if not app_config.settings.RATE_LIMIT_ENABLED or submission.path == auth_proxy.SETTINGS_SUBMIT_PATH:
        return None
    ip_key = await client_ip_key(request)
    refusal = await _rate_limit_refusal(ip_key, request.method, AUTH_SUBMIT_PER_IP)
    if refusal is not None:
        return refusal
    key = _identifier_key(ip_key, submission.path, submission.identifier)
    if key is None:
        return None
    return await _rate_limit_refusal(key, request.method, AUTH_SUBMIT_PER_IDENTIFIER)


async def _settings_rate_limit_refusal(request: Request, identity_id: str | None) -> Response | None:
    """검사를 통과한 설정 제출을 세션의 identity 단위로 센다 (identity id가 없으면 IP 단위)"""
    if not app_config.settings.RATE_LIMIT_ENABLED:
        return None
    key = f"identity:{identity_id}" if identity_id else await client_ip_key(request)
    return await _rate_limit_refusal(key, request.method, AUTH_SETTINGS_PER_IDENTITY)


async def _auth_submit_refusal(request: Request, path: str, body: bytes) -> Response | None:
    """/auth 제출을 세고 검사한다. 넘길 제출이면 None"""
    submission = auth_proxy.read_submission(path, request.url.query, request.headers.get("content-type", ""), body)
    if submission is None:
        return None
    request.state.auth_submission = submission
    refusal = await _submit_rate_limit_refusal(request, submission)
    if refusal is None:
        refusal = await auth_proxy.inspect_submission(submission, request.headers.get("x-session-token"))
    if refusal is None and submission.path == auth_proxy.SETTINGS_SUBMIT_PATH:
        refusal = await _settings_rate_limit_refusal(request, submission.identity_id)
    return refusal


def _auth_submit_path(scope: Scope) -> str | None:
    """프록시 라우트로 갈 제출이면 라우트의 path 값"""
    if scope["method"] not in AUTH_SUBMIT_METHODS:
        return None
    match = _AUTH_PROXY_PATH.match(get_route_path(scope))
    return match["path"] if match else None


def _replay(body: bytes, receive: Receive) -> Receive:
    """이미 읽은 본문을 한 번 다시 내주는 receive"""
    replayed = False

    async def replay() -> Message:
        nonlocal replayed
        if replayed:
            return await receive()
        replayed = True
        return {"type": "http.request", "body": body, "more_body": False}

    return replay


class GuestGateMiddleware:
    """게스트 관문 (순수 ASGI)"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        refusal = None
        if scope["type"] == "http" and (path := _auth_submit_path(scope)) is not None:
            request = Request(scope, receive)
            body = await request.body()
            receive = _replay(body, receive)
            refusal = await _auth_submit_refusal(request, path, body)
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)
