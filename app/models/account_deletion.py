"""
AccountDeletion 모델

파기한 계정의 sub. Kratos identity 삭제가 끝나지 않았으면 다음 파기 실행이 다시 시도하고,
행이 남아 있는 동안 그 sub의 토큰으로는 프로필을 새로 만들지 않는다.
"""
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel


class AccountDeletion(SQLModel, table=True):
    """파기한 계정 (sub만 남긴다)"""
    __tablename__ = "account_deletion"

    sub: str = Field(primary_key=True)
    purged_at: NaiveDatetime  # DB의 사용자 데이터를 지운 시각(UTC)
    kratos_deleted_at: NaiveDatetime | None = Field(default=None, nullable=True)  # Kratos identity를 지운 시각(UTC)
