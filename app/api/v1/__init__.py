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

# ── 인증 라우터 ──────────────────────────────────────────────────────────────
# 토큰 검증 게이트 + 행위자 표시 프로필 JIT 동기화(get_current_user_synced)를 부모
# 라우터에 한 번만 선언 → 하위 모든 경로에 적용. 새 소셜 라우터는 여기에 include만
# 하면 인증/동기화가 자동 적용되어 누락될 수 없다.
# (소셜 미사용 사용자도 프로필·email_hash를 확보해 친구 표시/이메일 친추가 가능)
authed = APIRouter(prefix="/v1", dependencies=[Depends(get_current_user_synced)])
for r in (
        schedules_router,
        timers_router,
        tags_router,
        todos_router,
        meetings_router,
        friends_router,
        users_router,
        visibility_router,
):
    authed.include_router(r)
api_router.include_router(authed)

# ── 공개(무인증) 라우터 ───────────────────────────────────────────────────────
# 인증/동기화 의존성 없음. 타입·prefix가 제각각이라 개별 등록한다.
api_router.include_router(holidays_router, prefix="/v1")
api_router.include_router(timers_ws_router, prefix="/v1")
api_router.include_router(create_graphql_router(), prefix="/v1/graphql", tags=["GraphQL"])
api_router.include_router(ws_playground_router)  # WebSocket Playground (개발 전용)
