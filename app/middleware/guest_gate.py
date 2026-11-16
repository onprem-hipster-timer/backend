"""
게스트 관문 (인터셉터)

게스트 단계의 Cloudflare Turnstile 확인은 여기 한 곳에서 한다 (app/core/turnstile.py). GUEST_ENABLED일 때 아래 요청은
X-Turnstile-Token 헤더의 토큰이 확인을 통과해야 라우트에 닿는다. 꺼져 있으면 확인하지 않는다.

| 게스트 단계 | 요청 |
|---|---|
| 이름 찾기 | POST /v1/guests/lookup |
| 생성 | POST /v1/guests |
| 자기 삭제 | DELETE /v1/guests/me |
| 로그인 | /auth 로그인 제출 중 식별자가 게스트 handle인 것 |
| 설정(이름 변경) | /auth 설정 제출 중 세션이 게스트인 것 |

- 토큰이 없거나 2048자를 넘거나 통과하지 못하거나 이미 받은 토큰이면 403, 확인할 수 없으면 503. /v1은 도메인 에러 JSON
  (GuestVerificationFailedError, GuestServiceUnavailableError), /auth는 프록시 JSON
  (guest_verification_failed, guest_verification_unavailable)으로 답한다
- 순서는 요청 한도 → Turnstile → Kratos를 쓰는 일(Kratos로 넘기기, identity 생성·삭제)이다. Turnstile은 입력 규칙·리소스 상태·
  이름 중복·게스트 수·게스트 JWT 판정보다 먼저다. /v1 경로는 바깥의 RateLimitMiddleware가 먼저 센다
- X-Turnstile-Token은 Kratos에 넘기지 않는다 (프록시의 요청 헤더 허용 목록에 없다)

/auth 제출(프록시 라우트가 받는 메서드 중 GET 밖의 요청과, 검사 경로(auth_proxy._submit_path)가 설정·로그인·가입·인증·복구
제출 경로인 GET)은 프록시(app/api/auth_proxy.py)보다 먼저 여기서 본문을 한 번 읽고 다음을 순서대로 거친다(_AUTH_CHECKS). 그 밖의 GET은 거치지
않는다. 읽은 것(Kratos로 보낼 URL, 본문, 식별자, 세션의 identity, 게스트 여부)은 request.state.auth_submission으로
넘기고, 프록시는 그 URL·본문으로 Kratos에 보낸다.

1. 제출 요청 한도 (app/ratelimit/config.py의 AUTH_* 규칙, 넘으면 429). 설정 밖의 제출과 GET 제출은 IP 단위로 센다
2. 식별자의 ASCII 규칙 (auth_proxy.identifier_refusal: GET 밖의 로그인·가입·인증·복구 제출의 식별자가 ASCII 밖의 문자를
   담으면 400 invalid_identifier)
3. 로그인·가입·인증·복구 제출을 같은 IP에서 같은 식별자(로그인 식별자, 이메일, auth_proxy.normalize_identifier로 맞춘 값)
   단위로도 센다
4. 프록시의 제출 검사 (inspect_submission: 쿼리 문자열, 로그인 식별자, 설정 제출의 세션. GET 제출은 쿼리 문자열만)
5. GET 밖의 설정 제출은 IP로 세지 않고, 검사를 통과한 세션의 identity 단위로 센다
6. 게스트 제출이면 Turnstile

프록시 라우트로 가는 요청(GET 포함)의 Kratos URL을 만들 수 없으면(auth_proxy.kratos_url이 httpx.InvalidURL) 위 단계 없이
400 invalid_request_url로 답한다.

경로와 메서드는 라우터와 같은 기준(라우트 경로 정규식, get_route_path)으로 가린다.
CORS 안쪽에 둔다. 거절 응답에도 CORS 헤더가 붙고, preflight는 CORS가 답한다.

테스트: tests/domain/guest/test_turnstile.py, test_guest_login_turnstile.py, test_rate_limits.py, tests/test_auth_proxy.py
"""
import hashlib
import logging

import httpx
from starlette._utils import get_route_path
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import auth_proxy
from app.core import config as app_config
from app.core import turnstile
from app.core.error_handlers import DomainException, format_error_response
from app.domain.guest.exceptions import GuestServiceUnavailableError, GuestVerificationFailedError
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

TURNSTILE_TOKEN_HEADER = "x-turnstile-token"
TURNSTILE_TOKEN_MAX_LENGTH = 2048

# /v1 게스트 단계: (메서드, 라우트 경로)
V1_STEPS = (
    ("POST", "/v1/guests/lookup"),
    ("POST", "/v1/guests"),
    ("DELETE", "/v1/guests/me"),
)
# /auth 게스트 단계: 게스트 제출(Submission.guest)의 검사 경로
AUTH_STEPS = frozenset({auth_proxy.LOGIN_SUBMIT_PATH, auth_proxy.SETTINGS_SUBMIT_PATH})

_V1_STEP_ROUTES = [(method, compile_path(path)[0]) for method, path in V1_STEPS]
_AUTH_PROXY_PATH, _, _ = compile_path(auth_proxy.PROXY_PATH)


async def _verification_failure(request: Request) -> DomainException | None:
    """X-Turnstile-Token 헤더의 토큰을 확인한다. 통과하면 None"""
    token = request.headers.get(TURNSTILE_TOKEN_HEADER)
    if not token or len(token) > TURNSTILE_TOKEN_MAX_LENGTH:
        return GuestVerificationFailedError()
    try:
        passed = await turnstile.verify(token)
    except turnstile.TurnstileUnavailableError:
        logger.warning(f"Turnstile 확인 실패: {request.method} {request.url.path}", exc_info=True)
        return GuestServiceUnavailableError()
    return None if passed else GuestVerificationFailedError()


async def _v1_step_refusal(request: Request) -> Response | None:
    """/v1 게스트 단계의 Turnstile. 거절은 도메인 예외 핸들러와 같은 본문이다 (미들웨어에서는 예외 핸들러가 돌지 않는다).
    GUEST_ENABLED가 꺼져 있으면 확인하지 않는다 (라우트가 404로 답한다)
    """
    if not app_config.settings.GUEST_ENABLED:
        return None
    failure = await _verification_failure(request)
    if failure is None:
        return None
    error = format_error_response(failure, path=str(request.url.path), method=request.method)
    return JSONResponse(status_code=error.status_code, content=error.dict())


async def _auth_step_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """/auth 게스트 제출의 Turnstile. 게스트 제출이 아니면 확인하지 않는다. 거절은 프록시 JSON이다"""
    if not submission.guest or submission.path not in AUTH_STEPS:
        return None
    failure = await _verification_failure(request)
    if failure is None:
        return None
    if isinstance(failure, GuestServiceUnavailableError):
        error_id, code, status, reason = (
            "guest_verification_unavailable", 503, "Service Unavailable", "확인 서비스에 연결할 수 없습니다."
        )
    else:
        error_id, code, status, reason = (
            "guest_verification_failed", 403, "Forbidden", "확인을 통과하지 못했습니다. 다시 시도하세요."
        )
    return JSONResponse({"error": {"id": error_id, "code": code, "status": status, "reason": reason}}, status_code=code)


def _identifier_key(ip_key: str, submit_path: str, identifier: object) -> str | None:
    """같은 IP·제출 경로·식별자의 한도 키. 식별자가 없으면 None.

    문자열은 auth_proxy.normalize_identifier로 맞춘다(Kratos가 같은 식별자로 찾는 표기는 같은 키). 읽을 수 없거나
    문자열이 아닌 값은 IP·경로마다 한 칸으로 센다. 키에는 식별자 대신 해시를 둔다.
    """
    if identifier is None:
        return None
    normalized = auth_proxy.normalize_identifier(identifier) if isinstance(identifier, str) else ""
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


def _counted_by_identity(submission: auth_proxy.Submission) -> bool:
    """GET 밖의 설정 제출인지. IP가 아니라 검사를 통과한 세션의 identity 단위로 센다"""
    return submission.path == auth_proxy.SETTINGS_SUBMIT_PATH and submission.method != "GET"


async def _submit_rate_limit_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """설정 밖의 제출과 GET 제출을 IP 단위로 센다"""
    if not app_config.settings.RATE_LIMIT_ENABLED or _counted_by_identity(submission):
        return None
    return await _rate_limit_refusal(await client_ip_key(request), request.method, AUTH_SUBMIT_PER_IP)


async def _identifier_rule_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """식별자의 ASCII 규칙 (auth_proxy.identifier_refusal)"""
    return auth_proxy.identifier_refusal(submission)


async def _identifier_rate_limit_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """로그인·가입·인증·복구 제출을 같은 IP의 같은 식별자 단위로 센다 (식별자가 없으면 세지 않는다)"""
    if not app_config.settings.RATE_LIMIT_ENABLED or submission.identifier is None:
        return None
    key = _identifier_key(await client_ip_key(request), submission.path, submission.identifier)
    return await _rate_limit_refusal(key, request.method, AUTH_SUBMIT_PER_IDENTIFIER)


async def _inspection_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """프록시의 제출 검사 (auth_proxy.inspect_submission). submission의 identity_id·guest를 채운다"""
    return await auth_proxy.inspect_submission(submission, request.headers.get("x-session-token"))


async def _settings_rate_limit_refusal(request: Request, submission: auth_proxy.Submission) -> Response | None:
    """검사를 통과한 GET 밖의 설정 제출을 세션의 identity 단위로 센다 (identity id가 없으면 IP 단위)"""
    if not app_config.settings.RATE_LIMIT_ENABLED or not _counted_by_identity(submission):
        return None
    identity_id = submission.identity_id
    key = f"identity:{identity_id}" if identity_id else await client_ip_key(request)
    return await _rate_limit_refusal(key, request.method, AUTH_SETTINGS_PER_IDENTITY)


# /auth 제출의 검사. 위에서부터 돌고 처음 나온 거절로 답한다. 모두 (request, submission)을 받고, 해당하지 않으면 None이다.
# _settings_rate_limit_refusal과 _auth_step_refusal은 _inspection_refusal이 채운 identity_id·guest를 읽는다
_AUTH_CHECKS = (
    _submit_rate_limit_refusal,
    _identifier_rule_refusal,
    _identifier_rate_limit_refusal,
    _inspection_refusal,
    _settings_rate_limit_refusal,
    _auth_step_refusal,
)


async def _auth_submit_refusal(request: Request, path: str, body: bytes) -> Response | None:
    """/auth 제출을 세고 검사한다. 넘길 제출이면 None"""
    try:
        submission = auth_proxy.read_submission(
            request.method, path, request.url.query, request.headers.get("content-type", ""), body
        )
    except httpx.InvalidURL:
        return auth_proxy.invalid_request_url()
    if submission is None:
        return None
    request.state.auth_submission = submission
    for check in _AUTH_CHECKS:
        if refusal := await check(request, submission):
            return refusal
    return None


def _is_v1_step(scope: Scope) -> bool:
    """/v1 게스트 단계인지"""
    route_path = get_route_path(scope)
    return any(scope["method"] == method and path_regex.match(route_path) for method, path_regex in _V1_STEP_ROUTES)


def _auth_submit_path(scope: Scope) -> str | None:
    """프록시 라우트로 갈 제출이면 라우트의 path 값. GET은 검사 경로가 검사하는 제출 경로일 때만 제출이다"""
    method = scope["method"]
    if method != "GET" and method not in AUTH_SUBMIT_METHODS:
        return None
    match = _AUTH_PROXY_PATH.match(get_route_path(scope))
    if match is None:
        return None
    if method == "GET" and not auth_proxy.is_get_submission(match["path"], Request(scope).url.query):
        return None
    return match["path"]


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
        if scope["type"] == "http":
            if _is_v1_step(scope):
                refusal = await _v1_step_refusal(Request(scope, receive))
            else:
                try:
                    path = _auth_submit_path(scope)
                except httpx.InvalidURL:
                    path, refusal = None, auth_proxy.invalid_request_url()
                if path is not None:
                    request = Request(scope, receive)
                    body = await request.body()
                    receive = _replay(body, receive)
                    refusal = await _auth_submit_refusal(request, path, body)
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)
