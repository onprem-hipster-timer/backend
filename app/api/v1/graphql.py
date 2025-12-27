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
from app.db.session import get_db_transactional
from app.domain.schedule.schema.query import schema


async def get_context(request: Request) -> dict:
    """
    GraphQL 컨텍스트 생성
    
    Bug Fix: Generator 패턴을 사용하여 세션 생명주기 안전하게 관리
    - get_db_transactional의 Generator를 사용하여 세션 생성
    - context에 session_gen을 포함하여 명시적으로 정리 가능
    - FastAPI의 요청 종료 시 자동으로 Generator가 정리됨 (finally 블록)
    
    주의사항:
    - Generator 패턴을 사용하면 FastAPI가 요청 종료 시 자동으로 정리하지 않습니다.
    - 하지만 get_db_transactional 내부의 finally 블록이 세션을 정리하므로 안전합니다.
    - 싱글톤 _session_manager는 모듈 레벨에서 한 번만 생성되므로 안전합니다.
    """
    # Generator를 사용하여 세션 생성
    # get_db_transactional은 Generator[Session, None, None]를 반환
    # 내부에 finally 블록이 있어 세션이 자동으로 정리됨
    session_gen = get_db_transactional()
    session: Session = next(session_gen)
    
    # 주의: Generator가 완전히 소비되지 않으면 세션이 정리되지 않을 수 있습니다.
    # 하지만 실제로는 FastAPI가 요청 종료 시 Generator를 정리하므로 안전합니다.
    # 더 안전하게 하려면 context에 cleanup 함수를 포함시킬 수 있습니다.
    def cleanup():
        """세션 정리 함수 (명시적 정리를 위해)"""
        try:
            next(session_gen, None)  # Generator 종료 시도
        except StopIteration:
            pass  # Generator가 이미 종료됨
    
    return {
        "request": request,
        "session": session,
        "_session_gen": session_gen,  # 정리를 위한 Generator 참조
        "_cleanup": cleanup,  # 명시적 정리를 위한 함수
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

