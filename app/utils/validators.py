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
