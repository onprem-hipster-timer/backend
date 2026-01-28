"""
WebSocket Playground

타이머 WebSocket API를 테스트할 수 있는 인터랙티브 플레이그라운드.
Swagger UI처럼 개발 환경에서만 활성화됩니다.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

router = APIRouter(tags=["WebSocket Playground"])

# 템플릿 디렉토리 설정
templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def get_message_schemas() -> dict:
    """Pydantic 스키마에서 메시지 타입 정보 추출"""
    from app.domain.timer.schema.ws import (
        TimerCreatePayload,
        TimerActionPayload,
        TimerSyncPayload,
    )
    
    return {
        "timer.create": TimerCreatePayload.model_json_schema(),
        "timer.pause": TimerActionPayload.model_json_schema(),
        "timer.resume": TimerActionPayload.model_json_schema(),
        "timer.stop": TimerActionPayload.model_json_schema(),
        "timer.sync": TimerSyncPayload.model_json_schema(),
    }


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
    
    # 메시지 스키마 추출
    message_schemas = get_message_schemas()
    
    return templates.TemplateResponse(
        "ws_playground.html",
        {
            "request": request,
            "title": "Timer WebSocket Playground",
            "ws_url": "/v1/ws/timers",
            "message_schemas": message_schemas,
            "message_schemas_json": json.dumps(message_schemas, indent=2),
        },
    )


@router.get(
    "/ws-playground/schema",
    include_in_schema=False,
    summary="WebSocket Message Schemas",
    description="WebSocket 메시지 스키마 JSON 반환",
)
async def ws_playground_schema():
    """
    WebSocket 메시지 스키마 JSON 반환
    
    프론트엔드에서 스키마 정보를 동적으로 가져올 때 사용합니다.
    """
    if not settings.DOCS_ENABLED or settings.ENVIRONMENT == "production":
        return {"error": "Not available in production"}
    
    return get_message_schemas()
