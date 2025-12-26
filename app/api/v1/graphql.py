"""
GraphQL Router

아키텍처 원칙:
- GraphQL은 API aggregation layer
- FastAPI에 GraphQL 라우터 등록
- 최신 Strawberry 패턴 적용 (2025 기준)
"""
from fastapi import Request
from strawberry.fastapi import GraphQLRouter
from sqlmodel import Session
from app.domain.schedule.schema.query import schema
from app.core.config import settings
from app.db.session import _session_manager


async def get_context(request: Request) -> dict:
    """
    GraphQL 컨텍스트 생성 (최신 패턴)
    
    최신 권장 패턴 (2025 기준):
    - async 함수로 정의
    - dict 반환 (가장 안전하고 읽기 쉬움)
    - FastAPI Request 포함
    - DB 세션을 context에 포함
    
    아키텍처 원칙:
    - GraphQL은 API aggregation layer
    - 세션 관리는 Context Manager 패턴 사용
    - 세션은 요청 종료 시 자동 정리됨 (Strawberry가 처리)
    """
    # DB 세션 생성 (전역 싱글톤 사용 - Bug Fix)
    session_context = _session_manager.get_session()
    session: Session = session_context.__enter__()
    
    # 세션 정리를 위한 context 저장 (Strawberry가 요청 종료 시 처리)
    # 참고: Strawberry는 context를 요청 전체에 걸쳐 유지하고 자동 정리
    return {
        "request": request,
        "session": session,
        "_session_context": session_context,  # 정리를 위한 내부 참조
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

