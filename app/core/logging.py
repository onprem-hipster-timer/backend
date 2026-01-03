import logging
import sys
import re

from app.core.config import settings


class ServiceKeyMaskingFilter(logging.Filter):
    """httpx 로그에서 ServiceKey를 마스킹하는 필터"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """로그 메시지에서 ServiceKey를 마스킹"""
        # msg 필드 마스킹
        if hasattr(record, 'msg') and record.msg:
            msg_str = str(record.msg)
            # ServiceKey=값 형식 마스킹 (쿼리 파라미터)
            msg_str = re.sub(
                r'(ServiceKey|service_key)=([^&\s"\'\)]+)',
                r'\1=***',
                msg_str,
                flags=re.IGNORECASE
            )
            record.msg = msg_str
        
        # args 필드도 마스킹 (포맷 문자열 인자)
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, tuple):
                masked_args = tuple(
                    re.sub(
                        r'(ServiceKey|service_key)=([^&\s"\'\)]+)',
                        r'\1=***',
                        str(arg),
                        flags=re.IGNORECASE
                    ) if isinstance(arg, str) else arg
                    for arg in record.args
                )
                record.args = masked_args
        
        return True


def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # httpx 로거 설정: DEBUG 레벨 로깅 비활성화 (ServiceKey 노출 방지)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)  # INFO, DEBUG 로그 비활성화
    
    # httpcore 로거 설정 (httpx가 사용하는 하위 라이브러리)
    httpcore_logger = logging.getLogger("httpcore")
    httpcore_logger.setLevel(logging.WARNING)
    
    # 추가 보안: 필터 추가 (만약 로그가 출력될 경우 대비)
    service_key_filter = ServiceKeyMaskingFilter()
    httpx_logger.addFilter(service_key_filter)
    httpcore_logger.addFilter(service_key_filter)
