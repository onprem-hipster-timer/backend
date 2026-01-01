"""
Custom Pydantic Base Model

FastAPI Best Practices:
- Custom Base Model로 모든 모델의 공통 설정 관리
- datetime 직렬화 표준화
- serializable_dict 메서드 제공
"""
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, field_serializer


class CustomModel(BaseModel):
    """
    Custom Base Model
    
    FastAPI Best Practices:
    - 모든 Pydantic 모델의 공통 설정
    - datetime 직렬화 표준화
    - serializable_dict 메서드 제공
    """
    model_config = ConfigDict(
        populate_by_name=True,
    )
    
    @field_serializer('*', when_used='json-unless-none')
    def serialize_datetime(self, value, info):
        """datetime 필드를 직렬화"""
        if isinstance(value, datetime):
            if not value.tzinfo:
                value = value.replace(tzinfo=timezone.utc)
            return value.strftime("%Y-%m-%dT%H:%M:%S%z")
        return value

    def serializable_dict(self, **kwargs):
        """Return a dict which contains only serializable fields."""
        default_dict = self.model_dump()
        return jsonable_encoder(default_dict)
