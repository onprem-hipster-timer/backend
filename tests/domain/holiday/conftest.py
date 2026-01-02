"""
Holiday 도메인 테스트용 fixture

필요 시 holiday 전용 fixture 추가
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_holiday_api_client():
    """
    HolidayApiClient를 자동으로 Mock으로 패치
    
    모든 holiday 도메인 테스트에서 자동으로 적용되어
    실제 API 호출 없이 테스트가 실행됩니다.
    """
    with patch('app.domain.holiday.service.HolidayApiClient') as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance
