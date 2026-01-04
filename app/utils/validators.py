from datetime import datetime


def validate_time_order(start_time: datetime | None, end_time: datetime | None):
    """
    시간 순서 검증: end_time이 start_time보다 이후여야 함
    
    :param start_time: 시작 날짜
    :param end_time: 종료 날짜
    :raises ValueError: end_time <= start_time인 경우
    """
    if start_time is not None and end_time is not None:
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time")


def validate_color(color: str | None) -> str | None:
    """
    색상 코드 검증 (HEX 형식)
    
    :param color: 색상 코드 (예: "#FFF" 또는 "#FFFFFF")
    :return: 대문자로 변환된 색상 코드
    :raises ValueError: HEX 형식이 아닌 경우
    """
    if color is None:
        return None
    if not color.startswith("#") or len(color) not in (4, 7):
        raise ValueError("색상은 HEX 형식이어야 합니다 (예: #FFF 또는 #FFFFFF)")
    return color.upper()
