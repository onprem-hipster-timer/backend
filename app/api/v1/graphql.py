"""
GraphQL Router

아키텍처 원칙:
- GraphQL은 API aggregation layer
- FastAPI에 GraphQL 라우터 등록
- 최신 Strawberry 패턴 적용 (2025 기준)
"""
from fastapi import Request, Depends
from sqlmodel import Session
from strawberry.fastapi import GraphQLRouter

from app.api.dependencies import get_db_transactional
from app.core.config import settings
from app.domain.schedule.schema.query import schema


async def get_context(
        request: Request,
        session: Session = Depends(get_db_transactional),
) -> dict:
    """
    GraphQL 컨텍스트 생성 (최신 패턴)
    
    최신 권장 패턴 (2025 기준):
    - async 함수로 정의
    - dict 반환 (가장 안전하고 읽기 쉬움)
    - FastAPI Request 포함
    - DB 세션을 context에 포함
    
    Bug Fix: FastAPI 의존성 + yield 패턴 사용
    - Strawberry는 자동으로 cleanup하지 않으므로 FastAPI 의존성 시스템 활용
    - get_db_transactional이 yield 패턴으로 세션 생명주기 관리
    - FastAPI가 요청 종료 시 자동으로 세션 정리 보장
    """
    return {
        "request": request,
        "session": session,
        # 향후 auth, user 등 추가 가능
    }


def create_graphql_router() -> GraphQLRouter:
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
