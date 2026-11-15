"""
GraphQL Router

아키텍처 원칙:
- GraphQL은 API aggregation layer
- FastAPI에 GraphQL 라우터 등록
- 최신 Strawberry 패턴 적용 (2025 기준)
- OIDC 인증 통합
"""
from typing import Any, Coroutine

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session
from strawberry.fastapi import GraphQLRouter

from app.core.auth import CurrentUser, oidc_client
import app.core.config as app_config
from app.core.config import settings
from app.db.session import get_db
from app.domain.schedule.schema.query import schema


async def get_context(request: Request, session: Session = Depends(get_db)) -> dict:
    """
    GraphQL 컨텍스트 생성 (인증 포함)
    
    세션:
    - context_getter는 FastAPI 의존성으로 해석되므로 get_db 세션(읽기 전용)을 Depends로 받는다
    - 세션은 어떤 resolver가 실행되든(또는 실행되지 않든) 요청이 끝나면 FastAPI가 닫는다
    
    인증:
    - Authorization 헤더에서 Bearer 토큰 추출
    - OIDC Provider를 통해 JWT 검증
    - CurrentUser 객체를 컨텍스트에 추가

    테스트: tests/test_graphql.py (요청 종료 시 세션 close)
    """
    # 인증 처리
    current_user: CurrentUser | None = None

    if not settings.OIDC_ENABLED:
        # 인증 비활성화 시 테스트용 사용자 반환
        current_user = CurrentUser.mock()
    else:
        # Authorization 헤더에서 토큰 추출
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # "Bearer " 제거
            try:
                claims = await oidc_client.verify_token(token)
                sub = claims.get("sub")
                if sub:
                    current_user = CurrentUser.from_claims(claims)
            except HTTPException:
                # 토큰 검증 실패 시 current_user는 None
                pass

    if current_user is not None:
        _require_active_account(session, current_user.sub)
    if current_user is not None and app_config.settings.CONSENT_ENFORCED:
        # 지연 import: domain.user.service가 app.core.auth를 import하므로 순환 회피
        from app.domain.user.exceptions import ConsentRequiredError
        from app.domain.user.service import consent_pending

        if consent_pending(session, current_user.sub):
            raise ConsentRequiredError()

    return {
        "request": request,
        "session": session,
        "current_user": current_user,
    }


def _require_active_account(session: Session, sub: str) -> None:
    """휴면·파기 계정은 REST와 같은 오류로 거부한다"""
    from app.domain.user.exceptions import AccountDeletedError, AccountDeletionPendingError
    from app.domain.user.service import AccountState, account_state

    state = account_state(session, sub)
    if state == AccountState.ACTIVE:
        return
    if state == AccountState.DELETED:
        raise AccountDeletedError()
    raise AccountDeletionPendingError()


def create_graphql_router() -> GraphQLRouter[Coroutine[Any, Any, dict], None]:
    """
    GraphQL 라우터 생성
    
    최신 권장 설정 (2025 기준):
    - graphql_ide: "apollo-sandbox" (현대적 UI)
    - context_getter: async 함수, dict 반환
    - GET/POST 모두 지원
    
    - Apollo Sandbox: 개발 환경에서 활성화
    - Introspection: 개발 환경에서 활성화
    
    :return: GraphQLRouter 인스턴스
    """
    return GraphQLRouter(
        schema,
        context_getter=get_context,
        graphql_ide="apollo-sandbox" if settings.GRAPHQL_ENABLE_PLAYGROUND else None,
        allow_queries_via_get=True,
    )
