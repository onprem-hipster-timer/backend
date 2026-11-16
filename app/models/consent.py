"""
Consent 모델

약관 동의 기록. 동의 항목(만 14세 이상, 이용약관, 개인정보처리방침)은 셋 모두 동의해야 기록되므로 따로 두지 않는다.
키 sub는 Kratos identity id(JWT sub)이고 회원과 게스트가 함께 쓴다 (app/domain/consent).
"""
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

from app.models.base import utc_now_naive


class Consent(SQLModel, table=True):
    """약관 동의 ((sub, version)마다 한 행)"""
    __tablename__ = "consent"

    sub: str = Field(primary_key=True)
    version: str = Field(primary_key=True)  # 동의한 약관 시행일 (settings.CONSENT_VERSION)
    consented_at: NaiveDatetime = Field(default_factory=utc_now_naive)  # 그 버전에 처음 동의한 시각(UTC)
