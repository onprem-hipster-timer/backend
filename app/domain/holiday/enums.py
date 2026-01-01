"""
Holiday Domain Enums

날짜 종류( dateKind) Enum 정의
"""
from enum import Enum


class DateKind(str, Enum):
    """
    날짜 종류 (dateKind)
    
    한국천문연구원 특일 정보제공 서비스에서 사용하는 날짜 종류 코드
    """
    NATIONAL_HOLIDAY = "01"  # 국경일 (어린이 날, 광복절, 개천절 등)
    MEMORIAL_DAY = "02"  # 기념일 (의병의 날, 정보보호의 날, 4·19 혁명 기념일 등)
    SOLAR_TERM = "03"  # 24절기 (청명, 경칩, 하지 등)
    FOLK_HOLIDAY = "04"  # 잡절 (단오, 한식 등)

    @property
    def label(self) -> str:
        """항목명 반환"""
        labels = {
            "01": "국경일",
            "02": "기념일",
            "03": "24절기",
            "04": "잡절",
        }
        return labels.get(self.value, "알 수 없음")

    def __str__(self) -> str:
        """문자열 표현"""
        return self.value
