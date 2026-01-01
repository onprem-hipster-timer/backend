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


class HolidayApiItem(CustomModel):
    """
    API 응답용 국경일 정보 항목 (원시 데이터)
    
    API에서 정수/문자열이 섞여서 올 수 있으므로 Union 타입 사용
    """
    model_config = ConfigDict(from_attributes=True)
    
    locdate: Union[str, int]  # 날짜 (YYYYMMDD) - 정수 또는 문자열
    seq: int  # 순번
    dateKind: Union[str, int]  # 날짜 종류 코드 (01: 국경일) - 정수 또는 문자열
    dateName: str  # 국경일 명칭
    isHoliday: Union[str, int, bool]  # 공공기관 휴일 여부 (Y / N) - 문자열, 정수, boolean 모두 가능


class HolidayItem(CustomModel):
    """도메인 국경일 정보 항목 (정제된 데이터)"""
    model_config = ConfigDict(from_attributes=True)
    
    locdate: str  # 날짜 (YYYYMMDD)
    seq: int  # 순번
    dateKind: str  # 날짜 종류 코드 (01: 국경일)
    dateName: str  # 국경일 명칭
    isHoliday: str  # 공공기관 휴일 여부 (Y / N)

    @classmethod
    def from_api_item(cls, api_item: HolidayApiItem) -> "HolidayItem":
        """
        API 응답 DTO를 도메인 DTO로 변환
        
        :param api_item: API 응답 DTO
        :return: 도메인 DTO
        """
        # locdate 변환
        locdate_str = str(api_item.locdate)
        
        # dateKind 변환
        if isinstance(api_item.dateKind, int):
            date_kind_str = str(api_item.dateKind).zfill(2)  # "01" 형식 보장
        else:
            date_kind_str = str(api_item.dateKind)
        
        # isHoliday 변환
        if isinstance(api_item.isHoliday, bool):
            is_holiday_str = "Y" if api_item.isHoliday else "N"
        elif isinstance(api_item.isHoliday, int):
            is_holiday_str = "Y" if api_item.isHoliday else "N"
        else:
            is_holiday_str = str(api_item.isHoliday)
        
        return cls(
            locdate=locdate_str,
            seq=api_item.seq,
            dateKind=date_kind_str,
            dateName=api_item.dateName,
            isHoliday=is_holiday_str,
        )

    @property
    def is_holiday_bool(self) -> bool:
        """isHoliday를 boolean으로 변환"""
        return self.isHoliday == "Y"

    @property
    def is_national_holiday(self) -> bool:
        """국경일 여부 (dateKind == "01")"""
        return self.dateKind == "01"


class HolidayApiBodyItems(CustomModel):
    """국경일 API 응답 Body의 items (item이 단일 또는 리스트일 수 있음)"""
    model_config = ConfigDict(from_attributes=True)
    
    item: Optional[Union[HolidayApiItem, List[HolidayApiItem]]] = None

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
    def items_list(self) -> List[HolidayApiItem]:
        """item을 리스트로 반환"""
        if self.item is None:
            return []
        if isinstance(self.item, list):
            return self.item
        return [self.item]


class HolidayApiBody(CustomModel):
    """국경일 API 응답 Body"""
    model_config = ConfigDict(from_attributes=True)
    
    items: Optional[HolidayApiBodyItems] = None
    numOfRows: Optional[int] = 10
    pageNo: Optional[int] = 1
    totalCount: Optional[int] = 0

    @property
    def items_list(self) -> List[HolidayApiItem]:
        """items에서 HolidayApiItem 리스트 반환"""
        if self.items is None:
            return []
        return self.items.items_list


class HolidayHeader(CustomModel):
    """국경일 API 응답 Header"""
    model_config = ConfigDict(from_attributes=True)
    
    resultCode: str
    resultMsg: str


class HolidayApiResponse(CustomModel):
    """국경일 API 응답 (원시 데이터)"""
    model_config = ConfigDict(from_attributes=True)
    
    header: HolidayHeader
    body: HolidayApiBody

    @property
    def is_success(self) -> bool:
        """응답이 성공인지 확인"""
        return self.header.resultCode == "00"

    @property
    def api_items(self) -> List[HolidayApiItem]:
        """API 응답 항목 목록 반환"""
        return self.body.items_list
    
    def to_domain_items(self) -> List[HolidayItem]:
        """API 응답 항목을 도메인 항목으로 변환"""
        return [HolidayItem.from_api_item(api_item) for api_item in self.api_items]


class HolidayQuery(CustomModel):
    """국경일 조회 요청 DTO"""
    solYear: int  # 조회 연도 (YYYY)
    solMonth: Optional[int] = None  # 조회 월 (MM)
    numOfRows: Optional[int] = None  # 페이지당 결과 수 (기본 10)
    pageNo: Optional[int] = None  # 페이지 번호 (기본 1)

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

    @field_validator("pageNo")
    @classmethod
    def validate_page_no(cls, v: Optional[int]) -> Optional[int]:
        """페이지 번호 검증"""
        if v is not None and v < 1:
            raise ValueError("pageNo must be greater than 0")
        return v

