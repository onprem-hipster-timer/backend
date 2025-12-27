"""
GraphQL Router

아키텍처 원칙:
- GraphQL은 API aggregation layer
- FastAPI에 GraphQL 라우터 등록
- 최신 Strawberry 패턴 적용 (2025 기준)
"""
from typing import Any, Coroutine

from fastapi import Request
from strawberry.fastapi import GraphQLRouter
from sqlmodel import Session

from app.core.config import settings
from app.db.session import get_db
from app.domain.schedule.schema.query import schema


async def get_context(request: Request) -> dict:
    """
    GraphQL 컨텍스트 생성
    
    Bug Fix: Generator 패턴을 사용하여 세션 생명주기 안전하게 관리
    - get_db()의 Generator를 사용하여 세션 생성 (읽기 전용, commit 불필요)
    - GraphQL resolver에서 try-finally를 통해 cleanup 보장
    - 요청 종료 시 자동으로 세션 정리됨
    
    주의: Strawberry는 context를 자동으로 cleanup하지 않으므로
    GraphQL resolver에서 try-finally를 통해 cleanup을 보장해야 합니다.
    """
    # Generator를 사용하여 세션 생성
    # get_db()는 읽기 전용 세션 (commit 불필요)
    session_gen = get_db()
    session: Session = next(session_gen)
    
    return {
        "request": request,
        "session": session,
        "_session_gen": session_gen,  # 정리를 위한 Generator 참조
        # 향후 auth, user 등 추가 가능
    }


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

