"""
Friend Router

친구 관계 관리 API
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db_transactional
from app.domain.friend.schema.dto import (
    FriendRequest,
    FriendshipRead,
    FriendRead,
    PendingRequestRead,
    FriendshipActionResponse,
)
from app.domain.friend.service import FriendService

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


@router.post("/requests", response_model=FriendshipRead, status_code=status.HTTP_201_CREATED)
async def send_friend_request(
        data: FriendRequest,
        session: Session = Depends(get_db_transactional),
        current_user: CurrentUser = Depends(get_current_user),
):
    """
    친구 요청 보내기
    
    대상 사용자에게 친구 요청을 보냅니다.
    이미 친구이거나 대기 중인 요청이 있으면 에러가 발생합니다.
    """
    service = FriendService(session, current_user)
    friendship = service.send_friend_request(data.addressee_id)
    return FriendshipRead.model_validate(friendship)


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
