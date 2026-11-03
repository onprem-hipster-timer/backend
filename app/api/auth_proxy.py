"""
Kratos 공개 API 리버스 프록시

Kratos는 api 컨테이너 옆 사이드카라 밖에서 직접 닿지 않는다.
/auth/* 요청을 /auth 접두사를 뗀 경로로 KRATOS_PUBLIC_URL에 그대로 넘긴다.

- 요청 헤더는 허용 목록만 넘긴다 (Host, X-Origin-Verify 등은 Kratos에 넘기지 않는다)
- 응답의 Set-Cookie는 합치지 않고 하나씩 돌려준다
- 리다이렉트는 따라가지 않고 클라이언트에 그대로 돌려준다
- admin API에는 닿지 않는다. 요청은 KRATOS_PUBLIC_URL 한 곳으로만 간다

OIDC 가입 요청에서 클라이언트가 보낸 traits.email을 버리는 처리는 OIDC provider를 켤 때
추가한다 (infra README "backend가 지켜야 할 것" 2번).
"""
import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core import courier
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cookie는 여러 줄로 올 수 있어 따로 합친다
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
# 그리고 uvicorn이 따로 붙이는 date·server (그대로 두면 두 번 나간다)
DROP_RESPONSE_HEADERS = {
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

router = APIRouter(include_in_schema=False)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.KRATOS_PUBLIC_URL,
        timeout=httpx.Timeout(15.0, connect=3.0),
    )


@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def kratos_proxy(path: str, request: Request) -> Response:
    if not settings.KRATOS_PUBLIC_URL:
        raise HTTPException(status_code=404)

    headers = {name: value for name in FORWARD_REQUEST_HEADERS if (value := request.headers.get(name))}
    if cookies := request.headers.getlist("cookie"):
        headers["cookie"] = "; ".join(cookies)
    url = f"/{path}?{request.url.query}" if request.url.query else f"/{path}"

    try:
        async with _make_client() as client:
            upstream = await client.request(
                request.method, url, headers=headers, content=await request.body()
            )
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
