"""
Consent Domain DTO
"""
from typing import Literal

from pydantic import StrictBool

from app.core.base_model import CustomModel


class ConsentCreate(CustomModel):
    """약관 동의 — 세 항목 모두 true여야 한다. 사용성 분석(analytics)은 선택이다

    PUT /v1/users/me/consent·PUT /v1/guests/me/consent의 본문이고 POST /v1/guests의 consent다.
    """
    version: str  # 동의한 약관 시행일. 현재 CONSENT_VERSION과 같아야 한다
    age_over_14: Literal[True]
    terms: Literal[True]
    privacy: Literal[True]
    analytics: StrictBool | None = None  # 사용성 분석 동의. 빠졌거나 null이면 고르지 않음(저장된 값을 두고 바꾸지 않는다)
