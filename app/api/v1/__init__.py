from fastapi import APIRouter

from app.api.v1.friends import router as friends_router
from app.api.v1.graphql import create_graphql_router
from app.api.v1.holidays import router as holidays_router
from app.api.v1.schedules import router as schedules_router
from app.api.v1.tags import router as tags_router
from app.api.v1.timers import router as timers_router
from app.api.v1.timers_ws import router as timers_ws_router
from app.api.v1.todos import router as todos_router

api_router = APIRouter()

# REST API 등록
api_router.include_router(schedules_router, prefix="/v1")
api_router.include_router(timers_router, prefix="/v1")
api_router.include_router(holidays_router, prefix="/v1")
api_router.include_router(tags_router, prefix="/v1")
api_router.include_router(todos_router, prefix="/v1")
api_router.include_router(friends_router, prefix="/v1")

# WebSocket API 등록
api_router.include_router(timers_ws_router, prefix="/v1")

# GraphQL API 등록 (v1에 통합)
graphql_router = create_graphql_router()
api_router.include_router(graphql_router, prefix="/v1/graphql", tags=["GraphQL"])
