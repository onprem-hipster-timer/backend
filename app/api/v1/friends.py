"""
Friend Router

친구 관계 관리 API
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db_transactional
from app.domain.friend.exceptions import FriendCodeNotFoundError
from app.domain.friend.schema.dto import (
    FriendRequest,
    FriendshipRead,
    FriendRead,
    PendingRequestRead,
)
from app.domain.friend.service import FriendService
from app.domain.user.service import UserProfileService

# 행위자 표시 프로필의 JIT 동기화는 app/api/v1/__init__.py에서 전역(모든 인증 라우터)으로 적용됨.
router = APIRouter(prefix="/friends", tags=["Friends"])


# ============================================================
# 친구 목록
# ============================================================

@router.get("", response_model=List[FriendRead])
async def list_friends(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 목록 조회
    
    현재 사용자의 모든 친구 목록을 반환합니다.
    """
    service = FriendService(session, current_user)
    return service.get_friends()


@router.get("/ids", response_model=List[str])
async def list_friend_ids(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 ID 목록만 조회 (효율적인 쿼리)
    
    친구 목록을 빠르게 확인할 때 사용합니다.
    """
    service = FriendService(session, current_user)
    return service.get_friend_ids()


# ============================================================
# 친구 요청 관리
# ============================================================

@router.get("/requests/received", response_model=List[PendingRequestRead])
async def list_received_requests(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    받은 친구 요청 목록 조회
    
    대기 중인 친구 요청만 반환합니다.
    """
    service = FriendService(session, current_user)
    return service.get_pending_requests_received()


@router.get("/requests/sent", response_model=List[PendingRequestRead])
async def list_sent_requests(
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    보낸 친구 요청 목록 조회
    
    대기 중인 친구 요청만 반환합니다.
    """
    service = FriendService(session, current_user)
    return service.get_pending_requests_sent()


@router.post("/requests")
async def send_friend_request(
        data: FriendRequest,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 요청 보내기 (email 또는 friend_code)

    `email` / `friend_code` 중 정확히 하나를 보냅니다(DTO에서 검증):
    - **email**: 검증된 이메일 사용자와 매칭. 계정 열거를 막기 위해 매칭/자기자신/중복/차단/
      미존재 여부와 무관하게 **항상 202** `{"ok": true}`를 반환합니다.
    - **friend_code**: `GET /v1/users/me`로 공유된 코드와 직접 매칭. 코드가 유효하지 않으면
      404, 매칭되면 정상 피드백(201, 또는 자기자신 400 / 중복·이미친구 409 / 차단 403).
    """
    profile_service = UserProfileService(session, current_user)
    friend_service = FriendService(session, current_user)

    if data.is_email_target:
        # 이메일 경로 — 균일 202 (존재 비노출, 도메인 예외는 try_* 가 흡수)
        addressee_id = profile_service.resolve_email(data.email)
        if addressee_id is not None:
            friend_service.try_send_friend_request(addressee_id)
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"ok": True})

    # 친구코드 경로 — 정상 피드백 (도메인 예외는 전역 핸들러가 변환)
    addressee_id = profile_service.resolve_friend_code(data.friend_code)
    if addressee_id is None:
        raise FriendCodeNotFoundError()
    friendship = friend_service.send_friend_request(addressee_id)
    read = FriendshipRead.model_validate(friendship)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=read.model_dump(mode="json"))


@router.post("/requests/{friendship_id}/accept", response_model=FriendshipRead)
async def accept_friend_request(
        friendship_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 요청 수락
    
    받은 친구 요청을 수락합니다.
    요청 수신자만 수락할 수 있습니다.
    """
    service = FriendService(session, current_user)
    friendship = service.accept_friend_request(friendship_id)
    return FriendshipRead.model_validate(friendship)


@router.post("/requests/{friendship_id}/reject", status_code=status.HTTP_200_OK)
async def reject_friend_request(
        friendship_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 요청 거절
    
    받은 친구 요청을 거절합니다.
    거절된 요청은 삭제됩니다.
    """
    service = FriendService(session, current_user)
    service.reject_friend_request(friendship_id)
    return {"ok": True, "message": "Friend request rejected"}


@router.delete("/requests/{friendship_id}", status_code=status.HTTP_200_OK)
async def cancel_friend_request(
        friendship_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    보낸 친구 요청 취소
    
    보낸 친구 요청을 취소합니다.
    요청 발신자만 취소할 수 있습니다.
    """
    service = FriendService(session, current_user)
    service.cancel_friend_request(friendship_id)
    return {"ok": True, "message": "Friend request cancelled"}


# ============================================================
# 친구 관계 관리
# ============================================================

@router.delete("/{friendship_id}", status_code=status.HTTP_200_OK)
async def remove_friend(
        friendship_id: UUID,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 삭제
    
    친구 관계를 끊습니다.
    양쪽 모두 삭제할 수 있습니다.
    """
    service = FriendService(session, current_user)
    service.remove_friend(friendship_id)
    return {"ok": True, "message": "Friend removed"}


@router.get("/check/{user_id}", response_model=bool)
async def check_friendship(
        user_id: str,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 여부 확인
    
    특정 사용자와 친구인지 확인합니다.
    """
    service = FriendService(session, current_user)
    return service.is_friend(user_id)


# ============================================================
# 차단 관리
# ============================================================

@router.post("/block/{user_id}", response_model=FriendshipRead)
async def block_user(
        user_id: str,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    사용자 차단
    
    특정 사용자를 차단합니다.
    차단된 사용자는 친구 요청을 보낼 수 없고, 공유된 콘텐츠에 접근할 수 없습니다.
    """
    service = FriendService(session, current_user)
    friendship = service.block_user(user_id)
    return FriendshipRead.model_validate(friendship)


@router.delete("/block/{user_id}", status_code=status.HTTP_200_OK)
async def unblock_user(
        user_id: str,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    사용자 차단 해제
    
    차단을 해제합니다.
    본인이 차단한 경우에만 해제할 수 있습니다.
    """
    service = FriendService(session, current_user)
    service.unblock_user(user_id)
    return {"ok": True, "message": "User unblocked"}
