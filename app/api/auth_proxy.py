"""
Kratos 공개 API 리버스 프록시

Kratos는 api 컨테이너 옆 사이드카라 밖에서 직접 닿지 않는다.
/auth/* 요청을 /auth 접두사를 뗀 경로로 KRATOS_PUBLIC_URL에 그대로 넘긴다.

- 요청 헤더는 허용 목록만 넘긴다 (Host, X-Origin-Verify 등은 Kratos에 넘기지 않는다)
- 쿠키는 오가지 않는다. 인증은 세션 토큰과 JWT로만 하므로 요청의 Cookie는 넘기지 않고
  응답의 Set-Cookie는 버린다 (Kratos API 플로우는 Cookie가 붙은 요청을 400으로 거부한다)
- 리다이렉트는 따라가지 않고 클라이언트에 그대로 돌려준다
- admin API에는 닿지 않는다. 요청은 KRATOS_PUBLIC_URL 한 곳으로만 간다
- 설정 제출은 메일 코드로 본인 확인한 복구 세션의 비밀번호 변경만 넘긴다. 새어 나간 비밀번호만으로
  비밀번호·이메일을 바꾸거나 다른 소셜 계정을 연결해 계정을 차지하지 못하게 한다.
  GUEST_ENABLED면 게스트 세션의 profile 제출(이름 변경)도 넘긴다. 무엇을 바꿀 수 있는지는 Kratos 설정 훅이
  정한다 (app/api/kratos_hooks.py). 같은 리소스의 다른 게스트가 쓰는 이름(정규형으로 비교)이면 넘기지 않고
  409 guest_name_taken으로 답한다 (app/domain/guest/service.py name_taken_by_other)
- 내용을 검사하는 제출(설정, 가입·로그인, 인증·복구)의 쿼리 문자열에는 flow 하나만 받는다(키는 대소문자 구분 없이).
  Kratos는 쿼리 문자열의 제출 값도 읽으므로 다른 키가 있으면 400 invalid_request_body로 거절하고 넘기지 않는다
- GUEST_ENABLED면 로그인 제출의 식별자(identifier, password_identifier)가 게스트 handle 주소일 때 X-Turnstile-Token
  헤더의 Turnstile 토큰을 확인한 뒤 넘긴다. 토큰이 없거나 통과하지 못하면 403 guest_verification_failed, 확인할 수
  없으면 503 guest_verification_unavailable. 식별자가 둘 이상이거나 본문을 읽을 수 없으면 400 invalid_request_body.
  X-Turnstile-Token은 Kratos에 넘기지 않는다
- 인증·복구 제출의 email이 게스트 handle 도메인(@guest.invalid)이면 400 address_not_accepted로 거절하고
  넘기지 않는다. 본문을 읽을 수 없으면 400 invalid_request_body
- 소셜(OIDC) 가입·로그인 제출에서 클라이언트가 보낸 traits.email은 버린다. 이메일은 제공자가
  검증해 준 값만 쓴다 (infra README "backend가 지켜야 할 것" 2번)
- 로그인·가입 제출이 200이면 identity id와 클라이언트 IP를 접근 기록으로 남긴다 (app/core/audit.py).
  응답은 바꾸지 않는다
- GET 밖의 제출은 요청 한도로 센다 (app/ratelimit/config.py의 AUTH_* 규칙, 넘으면 429). 설정 밖의 제출은 IP 단위로,
  로그인·가입·인증·복구 제출은 같은 IP에서 같은 식별자(로그인 식별자, 이메일) 단위로도 센다.
  설정 제출은 IP로 세지 않고, 검사를 통과한 세션의 identity 단위로 센다
"""
import hashlib
import json
import logging
import re
import unicodedata
from urllib.parse import parse_qs, parse_qsl, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core import config as app_config
from app.core import courier, turnstile
from app.core.audit import log_account_access
from app.core.config import settings
from app.domain.guest import service as guest_service
from app.ratelimit.config import (
    AUTH_SETTINGS_PER_IDENTITY,
    AUTH_SUBMIT_PER_IDENTIFIER,
    AUTH_SUBMIT_PER_IP,
    RateLimitRule,
)
from app.ratelimit.limiter import get_limiter
from app.ratelimit.middleware import client_ip_key, rate_limited_response

logger = logging.getLogger(__name__)

FORWARD_REQUEST_HEADERS = (
    "x-session-token",
    "authorization",
    "accept",
    "content-type",
    "x-forwarded-host",
    "x-forwarded-proto",
    "cf-connecting-ip",
)
# hop-by-hop 헤더, httpx가 본문을 풀면서 맞지 않게 된 길이·인코딩 헤더,
# uvicorn이 따로 붙이는 date·server (그대로 두면 두 번 나간다), 그리고 쓰지 않는 쿠키
DROP_RESPONSE_HEADERS = {
    "set-cookie",
    "date",
    "server",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "content-length",
    "content-encoding",
}
# 성공하면 메일을 큐에 넣을 수 있는 제출 (가입, 인증·복구 코드 요청, 설정 변경)
MAIL_FLOW_SUBMIT = re.compile(r"self-service/(registration|verification|recovery|settings)")

# 설정(비밀번호·이메일·소셜 계정 연결) 제출 경로. Kratos로 나갈 경로를 소문자·끝 슬래시 없이 비교한다
SETTINGS_SUBMIT_PATH = "/self-service/settings"
# 메일로 받은 복구 코드로 만든 세션의 인증 방법 (whoami의 authentication_methods)
EMAIL_RECOVERY_METHOD = "code_recovery"
# 소셜 로그인 제출 경로. 처음 쓰는 소셜 계정이면 로그인 제출도 가입으로 이어진다
OIDC_SUBMIT_PATHS = ("/self-service/registration", "/self-service/login")
# 메일 주소를 받는 인증·복구 제출 경로. 게스트 handle 도메인 주소는 받지 않는다
ADDRESS_SUBMIT_PATHS = ("/self-service/verification", "/self-service/recovery")
# 로그인 제출 경로와 로그인 식별자 키 (password_identifier는 이전 이름)
LOGIN_SUBMIT_PATH = "/self-service/login"
IDENTIFIER_KEYS = ("identifier", "password_identifier")
# 같은 IP의 같은 식별자 단위로도 세는 제출 경로 (식별자: 로그인은 identifier, 가입은 traits.email, 인증·복구는 email)
REGISTRATION_SUBMIT_PATH = "/self-service/registration"
IDENTIFIER_SUBMIT_PATHS = frozenset({LOGIN_SUBMIT_PATH, REGISTRATION_SUBMIT_PATH, *ADDRESS_SUBMIT_PATHS})
# 게스트 handle로 로그인할 때 Turnstile 토큰을 담는 요청 헤더와 토큰 길이 상한
TURNSTILE_TOKEN_HEADER = "x-turnstile-token"
TURNSTILE_TOKEN_MAX_LENGTH = 2048
# 본문을 검사하는 제출 경로. 쿼리 문자열에는 flow만 받는다
INSPECTED_SUBMIT_PATHS = frozenset({SETTINGS_SUBMIT_PATH, *OIDC_SUBMIT_PATHS, *ADDRESS_SUBMIT_PATHS})
# 성공하면 접근 기록을 남기는 제출 경로와 그 이벤트
ACCESS_LOG_EVENTS = {"/self-service/login": "login", "/self-service/registration": "registration"}

router = APIRouter(include_in_schema=False)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.KRATOS_PUBLIC_URL,
        timeout=httpx.Timeout(15.0, connect=3.0),
    )


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    # Kratos(Go)는 JSON 키를 대소문자 구분 없이 읽으므로 대소문자만 다른 키도 겹친 것으로 본다
    keys = [key.lower() for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key")
    return dict(pairs)


def _submitted_method(content_type: str, body: bytes) -> str | None:
    """제출 본문의 method. 읽을 수 없거나 키가 겹치면 None.

    키가 겹치면 여기와 Kratos가 서로 다른 값을 읽을 수 있으므로 받지 않는다.
    """
    try:
        if content_type.split(";")[0].strip().lower() == "application/x-www-form-urlencoded":
            values = parse_qs(body.decode(), keep_blank_values=True).get("method", [])
            return values[0] if len(values) == 1 else None
        data = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeDecodeError):
        return None
    method = data.get("method") if isinstance(data, dict) else None
    return method if isinstance(method, str) else None


def _only_flow_query(query: str) -> bool:
    """쿼리 문자열이 비었거나 flow 하나뿐이면 True (키는 대소문자 구분 없이 비교)"""
    keys = [key.lower() for key, _ in parse_qsl(query, keep_blank_values=True)]
    return keys in ([], ["flow"])


_UNREADABLE = object()


def _submitted_identifier(content_type: str, body: bytes) -> object:
    """로그인 제출의 식별자 값(없으면 None). 읽을 수 없거나 식별자가 둘 이상이면 _UNREADABLE"""
    if content_type.split(";")[0].strip().lower() == "application/x-www-form-urlencoded":
        try:
            pairs = parse_qsl(body.decode(), keep_blank_values=True)
        except UnicodeDecodeError:
            return _UNREADABLE
        values = [value for key, value in pairs if key.lower() in IDENTIFIER_KEYS]
    else:
        try:
            data = json.loads(body, object_pairs_hook=_no_duplicate_keys)
        except (ValueError, UnicodeDecodeError):
            return _UNREADABLE
        if not isinstance(data, dict):
            return None
        values = [value for key, value in data.items() if key.lower() in IDENTIFIER_KEYS]
    if len(values) > 1:
        return _UNREADABLE
    return values[0] if values else None


def _is_guest_handle(identifier: object) -> bool:
    """NFKC·앞뒤 공백 제거·casefold 뒤 게스트 handle 도메인 주소인지"""
    if not isinstance(identifier, str):
        return False
    normalized = unicodedata.normalize("NFKC", identifier).strip().casefold()
    return normalized.endswith(f"@{guest_service.GUEST_HANDLE_DOMAIN}")


async def _guest_login_refusal(token: str | None) -> Response | None:
    """게스트 handle 로그인의 Turnstile 토큰을 확인한다. 통과하면 None, 아니면 거절 응답"""
    if not token or len(token) > TURNSTILE_TOKEN_MAX_LENGTH:
        return _guest_verification_failed()
    try:
        passed = await turnstile.verify(token)
    except turnstile.TurnstileUnavailableError:
        logger.warning("게스트 로그인 Turnstile 확인 실패", exc_info=True)
        return _proxy_error("guest_verification_unavailable", 503, "Service Unavailable", "확인 서비스에 연결할 수 없습니다.")
    return None if passed else _guest_verification_failed()


def _submitted_name(content_type: str, body: bytes) -> object:
    """설정 제출 본문의 traits.name. 없거나 읽을 수 없으면 None (키는 Kratos처럼 대소문자 구분 없이 찾는다)"""
    try:
        if content_type.split(";")[0].strip().lower() == "application/x-www-form-urlencoded":
            values = parse_qs(body.decode(), keep_blank_values=True).get("traits.name", [])
            return values[0] if len(values) == 1 else None
        data = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeDecodeError):
        return None
    traits = _get_ignoring_case(data, "traits")
    return _get_ignoring_case(traits, "name")


def _get_ignoring_case(data: object, key: str) -> object:
    if not isinstance(data, dict):
        return None
    return next((value for k, value in data.items() if k.lower() == key), None)


def _submitted_value(content_type: str, body: bytes, path: tuple[str, ...]) -> object:
    """제출 본문에서 path(예: ("traits", "email"))의 값. 없으면 None, 본문을 읽을 수 없거나 값이 겹치면 _UNREADABLE.

    키는 Kratos처럼 대소문자 구분 없이 찾는다. 폼 본문의 키는 path를 점으로 이은 것이다.
    """
    if content_type.split(";")[0].strip().lower() == "application/x-www-form-urlencoded":
        try:
            pairs = parse_qsl(body.decode(), keep_blank_values=True)
        except UnicodeDecodeError:
            return _UNREADABLE
        form_key = ".".join(path)
        values = [value for key, value in pairs if key.lower() == form_key]
        if len(values) > 1:
            return _UNREADABLE
        return values[0] if values else None
    try:
        data = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeDecodeError):
        return _UNREADABLE
    for key in path:
        data = _get_ignoring_case(data, key)
    return data


def _is_guest_address(content_type: str, body: bytes) -> bool | None:
    """제출한 email이 게스트 handle 도메인 주소면 True. 본문을 읽을 수 없거나 email이 겹치면 None.

    값은 앞뒤 공백을 떼고 대소문자 구분 없이 비교한다.
    """
    email = _submitted_value(content_type, body, ("email",))
    if email is _UNREADABLE:
        return None
    return isinstance(email, str) and email.strip().lower().endswith(f"@{guest_service.GUEST_HANDLE_DOMAIN}")


def _submitted_rate_limit_identifier(submit_path: str, content_type: str, body: bytes) -> object:
    """같은 식별자 단위로 셀 제출의 식별자 (로그인은 identifier, 가입은 traits.email, 인증·복구는 email)"""
    if submit_path == LOGIN_SUBMIT_PATH:
        return _submitted_identifier(content_type, body)
    if submit_path == REGISTRATION_SUBMIT_PATH:
        return _submitted_value(content_type, body, ("traits", "email"))
    return _submitted_value(content_type, body, ("email",))


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


async def _submit_rate_limit_refusal(request: Request, submit_path: str, body: bytes) -> Response | None:
    """설정 밖의 제출을 IP 단위로 세고, 로그인·가입·인증·복구 제출은 같은 IP의 같은 식별자 단위로도 센다"""
    if not app_config.settings.RATE_LIMIT_ENABLED or submit_path == SETTINGS_SUBMIT_PATH:
        return None
    ip_key = await client_ip_key(request)
    refusal = await _rate_limit_refusal(ip_key, request.method, AUTH_SUBMIT_PER_IP)
    if refusal is not None or submit_path not in IDENTIFIER_SUBMIT_PATHS:
        return refusal
    identifier = _submitted_rate_limit_identifier(submit_path, request.headers.get("content-type", ""), body)
    key = _identifier_key(ip_key, submit_path, identifier)
    if key is None:
        return None
    return await _rate_limit_refusal(key, request.method, AUTH_SUBMIT_PER_IDENTIFIER)


async def _settings_rate_limit_refusal(request: Request, identity_id: str | None) -> Response | None:
    """검사를 통과한 설정 제출을 세션의 identity 단위로 센다 (identity id가 없으면 IP 단위)"""
    if not app_config.settings.RATE_LIMIT_ENABLED:
        return None
    key = f"identity:{identity_id}" if identity_id else await client_ip_key(request)
    return await _rate_limit_refusal(key, request.method, AUTH_SETTINGS_PER_IDENTITY)


def _without_oidc_email(content_type: str, body: bytes) -> bytes | None:
    """소셜 로그인 제출이면 traits.email을 뺀 본문, 아니면 본문 그대로. 읽을 수 없으면 None.

    소셜 계정의 이메일은 제공자 매퍼가 준 값(제공자가 검증한 이메일)만 쓴다.
    """
    if content_type.split(";")[0].strip().lower() == "application/x-www-form-urlencoded":
        try:
            pairs = parse_qsl(body.decode(), keep_blank_values=True)
        except UnicodeDecodeError:
            return None
        methods = [value for key, value in pairs if key == "method"]
        if len(methods) > 1:
            return None
        if methods != ["oidc"]:
            return body
        return urlencode([(key, value) for key, value in pairs if key != "traits.email"]).encode()

    try:
        data = json.loads(body, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return body
    if next((value for key, value in data.items() if key.lower() == "method"), None) != "oidc":
        return body
    for key in [key for key in data if key.lower() == "traits"]:
        if isinstance(data[key], dict):
            data[key] = {k: v for k, v in data[key].items() if k.lower() != "email"}
        else:
            del data[key]
    return json.dumps(data).encode()


def _identity_id(content: bytes) -> str | None:
    """Kratos 로그인·가입 응답의 identity id (session.identity.id, 없으면 identity.id)"""
    try:
        data = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for holder in (data.get("session"), data):
        identity = holder.get("identity") if isinstance(holder, dict) else None
        identity_id = identity.get("id") if isinstance(identity, dict) else None
        if isinstance(identity_id, str) and identity_id:
            return identity_id
    return None


def _unreadable_body() -> JSONResponse:
    return JSONResponse(
        {"error": {"id": "invalid_request_body", "code": 400, "status": "Bad Request", "reason": "요청 본문을 읽을 수 없습니다."}},
        status_code=400,
    )


def _settings_forbidden() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "id": "settings_require_email_recovery",
                "code": 403,
                "status": "Forbidden",
                "reason": "비밀번호는 메일로 받은 코드로 본인 확인을 마친 뒤에만 바꿀 수 있습니다.",
            }
        },
        status_code=403,
    )


def _proxy_error(error_id: str, code: int, status: str, reason: str) -> JSONResponse:
    return JSONResponse({"error": {"id": error_id, "code": code, "status": status, "reason": reason}}, status_code=code)


def _guest_verification_failed() -> JSONResponse:
    return _proxy_error("guest_verification_failed", 403, "Forbidden", "확인을 통과하지 못했습니다. 다시 시도하세요.")


def _address_not_accepted() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "id": "address_not_accepted",
                "code": 400,
                "status": "Bad Request",
                "reason": "이 주소로는 인증·복구를 요청할 수 없습니다.",
            }
        },
        status_code=400,
    )


def _guest_name_taken() -> JSONResponse:
    return JSONResponse(
        {"error": {"id": "guest_name_taken", "code": 409, "status": "Conflict", "reason": "같은 이름의 게스트가 이미 있습니다."}},
        status_code=409,
    )


def _unavailable() -> JSONResponse:
    return JSONResponse({"detail": "Authentication service unavailable"}, status_code=502)


def _session_identity_id(session: object) -> str | None:
    """whoami 세션의 identity id"""
    identity = session.get("identity") if isinstance(session, dict) else None
    identity_id = identity.get("id") if isinstance(identity, dict) else None
    return identity_id if isinstance(identity_id, str) and identity_id else None


def _guest_identity_id(session: object) -> str | None:
    """whoami 세션이 게스트 schema identity면 그 id"""
    return _session_identity_id(session) if _is_guest_session(session) else None


def _is_guest_session(session: object) -> bool:
    """whoami 세션의 identity가 게스트 schema인지"""
    identity = session.get("identity") if isinstance(session, dict) else None
    schema_id = identity.get("schema_id") if isinstance(identity, dict) else None
    return isinstance(schema_id, str) and schema_id == settings.KRATOS_GUEST_SCHEMA_ID


async def _settings_rejection(
        client: httpx.AsyncClient, request: Request, body: bytes
) -> tuple[Response | None, str | None, bool]:
    """메일 코드로 본인 확인한 복구 세션의 비밀번호 변경이 아니면 거절 응답을 돌려준다.
    넘길 제출이면 두 번째 값은 그 세션의 identity id, 세 번째 값은 게스트의 이름 변경인지다.

    비밀번호 로그인·재인증 세션은 비밀번호만 알면 만들 수 있으므로 받지 않는다. 복구 세션이라도
    비밀번호로 다시 인증하면 마지막 인증 방법이 password가 되어 받지 않는다. 이메일 변경(profile)과
    소셜 계정 연결(oidc)은 앱이 쓰지 않으므로 복구 세션이어도 막는다.
    GUEST_ENABLED면 게스트 세션의 profile 제출은 넘긴다 (로그인 식별자 변경은 Kratos 설정 훅이 거절한다).
    """
    method = _submitted_method(request.headers.get("content-type", ""), body)
    if method != "password" and not (method == "profile" and settings.GUEST_ENABLED):
        return _settings_forbidden(), None, False
    token = request.headers.get("x-session-token")
    if not token:
        return _settings_forbidden(), None, False
    whoami = await client.get(
        "/sessions/whoami", headers={"x-session-token": token, "accept": "application/json"}
    )
    last_method = None
    session = None
    if whoami.status_code == 200:
        try:
            session = whoami.json()
        except ValueError:
            session = None
    if method == "profile":
        guest_identity_id = _guest_identity_id(session)
        return (None, guest_identity_id, True) if guest_identity_id else (_settings_forbidden(), None, False)
    if session is not None:
        methods = session.get("authentication_methods") if isinstance(session, dict) else None
        if isinstance(methods, list) and methods and isinstance(methods[-1], dict):
            last_method = methods[-1].get("method")
    if last_method != EMAIL_RECOVERY_METHOD:
        logger.warning("메일 복구 세션이 아닌 설정 제출을 거절함")
        return _settings_forbidden(), None, False
    return None, _session_identity_id(session), False


@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def kratos_proxy(path: str, request: Request) -> Response:
    if not settings.KRATOS_PUBLIC_URL:
        raise HTTPException(status_code=404)

    headers = {name: value for name in FORWARD_REQUEST_HEADERS if (value := request.headers.get(name))}
    url = f"/{path}?{request.url.query}" if request.url.query else f"/{path}"

    body = await request.body()
    try:
        async with _make_client() as client:
            outgoing = client.build_request(request.method, url, headers=headers, content=body)
            # 검사는 실제로 나갈 경로로 한다 (httpx가 ..·인코딩을 정리한 뒤의 경로)
            submit_path = outgoing.url.path.rstrip("/").lower()
            if request.method != "GET":
                refusal = await _submit_rate_limit_refusal(request, submit_path, body)
                if refusal is not None:
                    return refusal
            if request.method != "GET" and submit_path in INSPECTED_SUBMIT_PATHS:
                if not _only_flow_query(request.url.query):
                    return _unreadable_body()
            if request.method != "GET" and submit_path in ADDRESS_SUBMIT_PATHS:
                guest_address = _is_guest_address(request.headers.get("content-type", ""), body)
                if guest_address is None:
                    return _unreadable_body()
                if guest_address:
                    return _address_not_accepted()
            if request.method != "GET" and submit_path == LOGIN_SUBMIT_PATH and settings.GUEST_ENABLED:
                identifier = _submitted_identifier(request.headers.get("content-type", ""), body)
                if identifier is _UNREADABLE:
                    return _unreadable_body()
                if _is_guest_handle(identifier):
                    refusal = await _guest_login_refusal(request.headers.get(TURNSTILE_TOKEN_HEADER))
                    if refusal is not None:
                        return refusal
            if request.method != "GET" and submit_path in OIDC_SUBMIT_PATHS:
                cleaned = _without_oidc_email(request.headers.get("content-type", ""), body)
                if cleaned is None:
                    return _unreadable_body()
                if cleaned != body:
                    outgoing = client.build_request(request.method, url, headers=headers, content=cleaned)
            if request.method != "GET" and submit_path == SETTINGS_SUBMIT_PATH:
                rejection, identity_id, guest_rename = await _settings_rejection(client, request, body)
                if rejection is not None:
                    return rejection
                refusal = await _settings_rate_limit_refusal(request, identity_id)
                if refusal is not None:
                    return refusal
                # 검사한 X-Session-Token 세션으로만 처리되게 다른 세션 헤더는 넘기지 않는다
                outgoing = client.build_request(
                    request.method,
                    url,
                    headers={k: v for k, v in headers.items() if k != "authorization"},
                    content=body,
                )
                if guest_rename and await guest_service.name_taken_by_other(
                        identity_id, _submitted_name(request.headers.get("content-type", ""), body)
                ):
                    return _guest_name_taken()
            upstream = await client.send(outgoing)
    except httpx.HTTPError:
        logger.warning("Kratos 공개 API에 닿지 않음", exc_info=True)
        return _unavailable()

    if request.method == "POST" and upstream.status_code in (200, 303) and MAIL_FLOW_SUBMIT.fullmatch(path):
        await courier.start()

    event = ACCESS_LOG_EVENTS.get(submit_path)
    if request.method == "POST" and upstream.status_code == 200 and event:
        if identity_id := _identity_id(upstream.content):
            log_account_access(event, identity_id, request.client.host if request.client else None)

    response = Response(content=upstream.content, status_code=upstream.status_code)
    for name, value in upstream.headers.multi_items():
        if name.lower() not in DROP_RESPONSE_HEADERS:
            response.headers.append(name, value)
    return response
