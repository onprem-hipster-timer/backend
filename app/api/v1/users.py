"""
Users Router

본인 표시 프로필 조회 API.

친구 추가는 검색이 아니라 **친구코드**로 한다(열거 표면 제거). 사용자는 여기서
자기 `friend_code`를 받아 친추 URL 등으로 공유하고, 상대는 그 코드로 친구 요청을
보낸다(POST /v1/friends/requests). 타인 프로필을 검색/조회하는 엔드포인트는 없다.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db_transactional
from app.domain.user.schema.dto import MyProfileRead
from app.domain.user.service import UserProfileService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=MyProfileRead)
async def get_my_profile(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    본인 표시 프로필 조회 (없으면 토큰 클레임으로 생성).

    `friend_code`를 공유하면 상대가 그 코드로 친구 요청을 보낼 수 있다.
    """
    profile = UserProfileService(session, current_user).sync_from_current_user()
    return MyProfileRead(
        id=current_user.sub,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        friend_code=profile.friend_code,
    )
