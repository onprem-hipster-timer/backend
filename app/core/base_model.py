"""
Custom Pydantic Base Model

FastAPI Best Practices:
- Custom Base Model로 모든 모델의 공통 설정 관리
- datetime 직렬화 표준화
- serializable_dict 메서드 제공
"""
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict


def datetime_to_gmt_str(dt: datetime) -> str:
    """
    datetime을 GMT 문자열로 변환
    
    Bug Fix: ZoneInfo 대신 timezone.utc 사용
    - Windows에서 tzdata 패키지 없이도 작동
    - 표준 라이브러리만 사용하여 호환성 향상
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


class CustomModel(BaseModel):
    """
    Custom Base Model
    
    FastAPI Best Practices:
    - 모든 Pydantic 모델의 공통 설정
    - datetime 직렬화 표준화
    - serializable_dict 메서드 제공
    """
    model_config = ConfigDict(
        json_encoders={datetime: datetime_to_gmt_str},
        populate_by_name=True,
    )

    def serializable_dict(self, **kwargs):
        """Return a dict which contains only serializable fields."""
        default_dict = self.model_dump()
        return jsonable_encoder(default_dict)
