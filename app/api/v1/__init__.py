# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Hipster Timer Project Contributors

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user_synced
from app.api.v1.friends import router as friends_router
from app.api.v1.graphql import create_graphql_router
from app.api.v1.holidays import router as holidays_router
from app.api.v1.meetings import router as meetings_router
from app.api.v1.schedules import router as schedules_router
from app.api.v1.tags import router as tags_router
from app.api.v1.timers import router as timers_router
from app.api.v1.timers_ws import router as timers_ws_router
from app.api.v1.todos import router as todos_router
from app.api.v1.users import router as users_router
from app.api.v1.visibility import router as visibility_router
from app.api.v1.ws_playground import router as ws_playground_router

api_router = APIRouter()

# 인증 라우터 공통 의존성: 모든 인증된 요청에서 행위자의 표시 프로필을 JIT 동기화.
# (소셜 미사용 사용자도 프로필·email_hash를 확보해 친구 표시/이메일 친추가 가능)
# 무인증/공개 라우터(holidays, ws_playground, graphql, health)에는 적용하지 않는다.
_synced = [Depends(get_current_user_synced)]

# REST API 등록
api_router.include_router(schedules_router, prefix="/v1", dependencies=_synced)
api_router.include_router(timers_router, prefix="/v1", dependencies=_synced)
api_router.include_router(holidays_router, prefix="/v1")  # 공개(무인증) — 동기화 제외
api_router.include_router(tags_router, prefix="/v1", dependencies=_synced)
api_router.include_router(todos_router, prefix="/v1", dependencies=_synced)
api_router.include_router(meetings_router, prefix="/v1", dependencies=_synced)
api_router.include_router(friends_router, prefix="/v1", dependencies=_synced)
api_router.include_router(users_router, prefix="/v1", dependencies=_synced)
api_router.include_router(visibility_router, prefix="/v1", dependencies=_synced)

# WebSocket API 등록
api_router.include_router(timers_ws_router, prefix="/v1")

# GraphQL API 등록 (v1에 통합)
graphql_router = create_graphql_router()
api_router.include_router(graphql_router, prefix="/v1/graphql", tags=["GraphQL"])

# WebSocket Playground (개발 환경 전용)
api_router.include_router(ws_playground_router)
