"""
WebSocket Playground

수신 전용 타이머 WebSocket(/v1/ws/timers)에 연결해 이벤트를 확인하는 개발용 페이지.
Swagger UI처럼 개발 환경에서만 활성화됩니다.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

router = APIRouter(tags=["WebSocket Playground"])

# 템플릿 디렉토리 설정
templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get(
    "/ws-playground",
    response_class=HTMLResponse,
    include_in_schema=False,
    summary="WebSocket Playground",
    description="타이머 WebSocket API 테스트 플레이그라운드",
)
async def ws_playground(request: Request):
    """
    WebSocket 테스트 플레이그라운드
    
    DOCS_ENABLED=false 또는 production 환경에서는 404를 반환합니다.
    """
    # DOCS_ENABLED 체크 (Swagger UI와 동일한 조건)
    if not settings.DOCS_ENABLED or settings.ENVIRONMENT == "production":
        return HTMLResponse(
            content="<h1>404 Not Found</h1><p>WebSocket Playground is disabled in production.</p>",
            status_code=404,
        )

    return templates.TemplateResponse(
        "ws_playground.html",
        {
            "request": request,
            "title": "Timer WebSocket Playground",
            "ws_url": "/v1/ws/timers",
        },
    )
