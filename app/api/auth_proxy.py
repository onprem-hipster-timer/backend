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
  비밀번호·이메일을 바꾸거나 다른 소셜 계정을 연결해 계정을 차지하지 못하게 한다

OIDC 가입 요청에서 클라이언트가 보낸 traits.email을 버리는 처리는 OIDC provider를 켤 때
추가한다 (infra README "backend가 지켜야 할 것" 2번).
"""
import json
import logging
import re
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core import courier
from app.core.config import settings

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

router = APIRouter(include_in_schema=False)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.KRATOS_PUBLIC_URL,
        timeout=httpx.Timeout(15.0, connect=3.0),
    )


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
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


async def _settings_rejection(client: httpx.AsyncClient, request: Request, body: bytes) -> Response | None:
    """메일 코드로 본인 확인한 복구 세션의 비밀번호 변경이 아니면 거절 응답을 돌려준다.

    비밀번호 로그인·재인증 세션은 비밀번호만 알면 만들 수 있으므로 받지 않는다. 복구 세션이라도
    비밀번호로 다시 인증하면 마지막 인증 방법이 password가 되어 받지 않는다. 이메일 변경(profile)과
    소셜 계정 연결(oidc)은 앱이 쓰지 않으므로 복구 세션이어도 막는다.
    """
    if _submitted_method(request.headers.get("content-type", ""), body) != "password":
        return _settings_forbidden()
    token = request.headers.get("x-session-token")
    if not token:
        return _settings_forbidden()
    whoami = await client.get(
        "/sessions/whoami", headers={"x-session-token": token, "accept": "application/json"}
    )
    last_method = None
    if whoami.status_code == 200:
        try:
            session = whoami.json()
        except ValueError:
            session = None
        methods = session.get("authentication_methods") if isinstance(session, dict) else None
        if isinstance(methods, list) and methods and isinstance(methods[-1], dict):
            last_method = methods[-1].get("method")
    if last_method != EMAIL_RECOVERY_METHOD:
        logger.warning("메일 복구 세션이 아닌 설정 제출을 거절함")
        return _settings_forbidden()
    return None


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
            if request.method != "GET" and outgoing.url.path.rstrip("/").lower() == SETTINGS_SUBMIT_PATH:
                if (rejection := await _settings_rejection(client, request, body)) is not None:
                    return rejection
                # 검사한 X-Session-Token 세션으로만 처리되게 다른 세션 헤더는 넘기지 않는다
                outgoing = client.build_request(
                    request.method,
                    url,
                    headers={k: v for k, v in headers.items() if k != "authorization"},
                    content=body,
                )
            upstream = await client.send(outgoing)
    except httpx.HTTPError:
        logger.warning("Kratos 공개 API에 닿지 않음", exc_info=True)
        return JSONResponse({"detail": "Authentication service unavailable"}, status_code=502)

    if request.method == "POST" and upstream.status_code in (200, 303) and MAIL_FLOW_SUBMIT.fullmatch(path):
        courier.trigger()

    response = Response(content=upstream.content, status_code=upstream.status_code)
    for name, value in upstream.headers.multi_items():
        if name.lower() not in DROP_RESPONSE_HEADERS:
            response.headers.append(name, value)
    return response
