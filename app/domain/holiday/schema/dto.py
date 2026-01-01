"""
Holiday Domain DTO (Data Transfer Objects)

아키텍처 원칙:
- Domain이 자신의 DTO를 정의
- REST API와 GraphQL 모두에서 사용
- Pydantic을 사용한 데이터 검증
"""
from typing import Optional, List, Union
from pydantic import ConfigDict, field_validator, model_validator

from app.core.base_model import CustomModel


class HolidayItem(CustomModel):
    """국경일 정보 항목"""
    model_config = ConfigDict(from_attributes=True)
    
    locdate: str  # 날짜 (YYYYMMDD)
    seq: int  # 순번
    dateKind: str  # 날짜 종류 코드 (01: 국경일)
    dateName: str  # 국경일 명칭
    isHoliday: str  # 공공기관 휴일 여부 (Y / N)

    @property
    def is_holiday_bool(self) -> bool:
        """isHoliday를 boolean으로 변환"""
        return self.isHoliday == "Y"

    @property
    def is_national_holiday(self) -> bool:
        """국경일 여부 (dateKind == "01")"""
        return self.dateKind == "01"


class HolidayBodyItems(CustomModel):
    """국경일 API 응답 Body의 items (item이 단일 또는 리스트일 수 있음)"""
    model_config = ConfigDict(from_attributes=True)
    
    item: Optional[Union[HolidayItem, List[HolidayItem]]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_item(cls, data):
        """item이 단일 객체인 경우 리스트로 변환"""
        if isinstance(data, dict) and "item" in data:
            item = data["item"]
            if item is None:
                data["item"] = None
            elif not isinstance(item, list):
                # 단일 객체를 리스트로 변환
                data["item"] = [item]
        return data

    @property
    def items_list(self) -> List[HolidayItem]:
        """item을 리스트로 반환"""
        if self.item is None:
            return []
        if isinstance(self.item, list):
            return self.item
        return [self.item]


class HolidayBody(CustomModel):
    """국경일 API 응답 Body"""
    model_config = ConfigDict(from_attributes=True)
    
    items: Optional[HolidayBodyItems] = None
    numOfRows: Optional[int] = 10
    pageNo: Optional[int] = 1
    totalCount: Optional[int] = 0

    @property
    def items_list(self) -> List[HolidayItem]:
        """items에서 HolidayItem 리스트 반환"""
        if self.items is None:
            return []
        return self.items.items_list


class HolidayHeader(CustomModel):
    """국경일 API 응답 Header"""
    model_config = ConfigDict(from_attributes=True)
    
    resultCode: str
    resultMsg: str


class HolidayResponse(CustomModel):
    """국경일 API 응답"""
    model_config = ConfigDict(from_attributes=True)
    
    header: HolidayHeader
    body: HolidayBody

    @property
    def is_success(self) -> bool:
        """응답이 성공인지 확인"""
        return self.header.resultCode == "00"

    @property
    def items(self) -> List[HolidayItem]:
        """국경일 목록 반환"""
        return self.body.items_list


class HolidayQuery(CustomModel):
    """국경일 조회 요청 DTO"""
    solYear: int  # 조회 연도 (YYYY)
    solMonth: Optional[int] = None  # 조회 월 (MM)
    numOfRows: Optional[int] = None  # 페이지당 결과 수 (기본 10)

    @field_validator("solYear")
    @classmethod
    def validate_year(cls, v: int) -> int:
        """연도 검증"""
        if v < 1900 or v > 2100:
            raise ValueError("Year must be between 1900 and 2100")
        return v

    @field_validator("solMonth")
    @classmethod
    def validate_month(cls, v: Optional[int]) -> Optional[int]:
        """월 검증"""
        if v is not None and (v < 1 or v > 12):
            raise ValueError("Month must be between 1 and 12")
        return v

    @field_validator("numOfRows")
    @classmethod
    def validate_num_of_rows(cls, v: Optional[int]) -> Optional[int]:
        """페이지당 결과 수 검증"""
        if v is not None and v < 1:
            raise ValueError("numOfRows must be greater than 0")
        return v

