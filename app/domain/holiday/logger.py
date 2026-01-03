"""
Holiday 도메인 로깅

HolidayService와 HolidayApiClient에서 사용하는 로깅 함수들
"""
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any, Iterator
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)


def log_sync_result(
        year: int,
        holidays_by_type: dict[str, list],
        deduplicated: list,
        new_hash: str,
        old_hash: Optional[str],
        force_update: bool,
) -> None:
    """
    동기화 결과 로깅
    
    :param year: 동기화한 연도
    :param holidays_by_type: 종류별 공휴일 딕셔너리
    :param deduplicated: 중복 제거된 공휴일 리스트
    :param new_hash: 새 해시값
    :param old_hash: 기존 해시값
    :param force_update: 강제 업데이트 여부
    """
    # 업데이트 결정 로깅
    if force_update:
        logger.debug(f"Force updating holidays for {year} (hash: {new_hash[:8]}...)")
    else:
        old_hash_str = old_hash[:8] if old_hash else "None"
        logger.info(
            f"Holiday changes detected for {year}\n"
            f"   Old: {old_hash_str}..., New: {new_hash[:8]}..."
        )

    # 중복 제거 정보 로깅
    total = sum(len(v) for v in holidays_by_type.values())
    if total != len(deduplicated):
        logger.info(
            f"Removed {total - len(deduplicated)} duplicate holidays "
            f"before saving (total: {total} -> {len(deduplicated)})"
        )

    # 최종 결과 로깅
    logger.info(
        f"Updated {len(deduplicated)} holidays for {year} "
        f"(national: {len(holidays_by_type['national'])}, "
        f"rest: {len(holidays_by_type['rest'])}, "
        f"anniversaries: {len(holidays_by_type['anniversaries'])}, "
        f"24divisions: {len(holidays_by_type['divisions_24'])})"
    )


@contextmanager
def initialization_context(
    initial_year: int,
    current_year: int,
    total_years: int,
    skipped_count: int = 0,
    existing_years: Optional[set[int]] = None,
) -> Iterator[None]:
    """
    초기화 프로세스 컨텍스트 매니저
    
    초기화의 시작/진행/완료를 자동으로 로깅합니다.
    
    사용 예:
        with initialization_context(initial_year, current_year, total_years, skipped_count, existing_years):
            for idx, year in enumerate(years_to_sync, 1):
                # 초기화 로직
                log_initialization_progress(year, idx, total_years)
    
    :param initial_year: 시작 연도
    :param current_year: 현재 연도
    :param total_years: 동기화할 총 연도 수
    :param skipped_count: 건너뛴 연도 수
    :param existing_years: 이미 존재하는 연도 집합 (건너뛴 연도 로깅용)
    """
    # 건너뛴 연도 로깅
    if skipped_count > 0 and existing_years:
        logger.info(
            f"Skipping {skipped_count} years that already exist in hash table: "
            f"{sorted(existing_years)}"
        )
    
    # 초기화 불필요 체크
    if total_years == 0:
        logger.info(
            f"All years from {initial_year} to {current_year} already exist in hash table. "
            f"Skipping initialization."
        )
        yield
        return
    
    # 초기화 시작 로깅
    logger.info(
        f"Initializing historical holiday data from {initial_year} to {current_year} "
        f"({total_years} years to sync, {skipped_count} years skipped)"
    )
    
    try:
        yield
    finally:
        # 초기화 완료 로깅
        logger.info(
            f"Historical data initialization completed: "
            f"all {total_years} years succeeded"
        )


def log_initialization_progress(year: int, current: int, total: int) -> None:
    """
    초기화 진행 상황 로깅
    
    :param year: 현재 동기화 중인 연도
    :param current: 현재 진행 번호
    :param total: 전체 연도 수
    """
    logger.debug(f"   [{current}/{total}] {year} year initialized")


def mask_service_key_in_url(url: str) -> str:
    """
    URL의 쿼리 파라미터에서 ServiceKey를 마스킹
    
    :param url: 원본 URL
    :return: ServiceKey가 마스킹된 URL
    """
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # ServiceKey를 마스킹 (대소문자 구분 없이)
        masked_params = {}
        for key, values in query_params.items():
            if key.lower() in ['servicekey', 'service_key']:
                masked_params[key] = ['***']
            else:
                masked_params[key] = values
        
        # 쿼리 문자열 재구성
        masked_query = urlencode(masked_params, doseq=True)
        masked_parsed = parsed._replace(query=masked_query)
        return urlunparse(masked_parsed)
    except Exception:
        # 파싱 실패 시 원본 URL 반환
        return url


def mask_service_key_in_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    파라미터 딕셔너리에서 ServiceKey를 마스킹
    
    :param params: 원본 파라미터 딕셔너리
    :return: ServiceKey가 마스킹된 파라미터 딕셔너리
    """
    masked = params.copy()
    for key in masked:
        if key.lower() in ['servicekey', 'service_key']:
            masked[key] = '***'
    return masked


def log_api_request(url: str, params: Dict[str, str]) -> None:
    """
    API 요청 로깅 (ServiceKey 마스킹)
    
    :param url: 요청 URL
    :param params: 요청 파라미터
    """
    masked_url = mask_service_key_in_url(url)
    masked_params = mask_service_key_in_params(params)
    logger.info(f"Calling holiday API: {masked_url} with params: {masked_params}")


def log_api_error(error: Exception | str, error_type: str = "API") -> None:
    """
    API 관련 에러 로깅 (범용)
    
    :param error: 에러 예외 또는 에러 메시지
    :param error_type: 에러 타입 (기본값: "API")
    """
    error_msg = str(error) if isinstance(error, Exception) else error
    logger.error(f"Holiday {error_type} error: {error_msg}")


@contextmanager
def paginated_fetch_context(
    item_type: str,
    total_count: int,
    num_of_rows: int,
    total_pages: int
) -> Iterator[None]:
    """
    페이지네이션된 데이터 페칭 컨텍스트 매니저
    
    모든 페이지 조회의 시작/진행/완료를 자동으로 로깅합니다.
    
    사용 예:
        with paginated_fetch_context("holidays", total_count, num_of_rows, total_pages):
            for page_no in range(2, total_pages + 1):
                # 페이지 페칭 로직
                log_page_progress(page_no, total_pages, "holidays")
        
    :param item_type: 항목 타입 (holidays, rest days, anniversaries, 24 divisions)
    :param total_count: 전체 항목 수
    :param num_of_rows: 페이지당 항목 수
    :param total_pages: 전체 페이지 수
    """
    logger.info(
        f"Fetching all pages for {item_type}: "
        f"totalCount={total_count}, numOfRows={num_of_rows}, totalPages={total_pages}"
    )
    try:
        yield
    finally:
        # 완료 로깅은 호출자가 item_count를 전달해야 하므로 여기서는 하지 않음
        pass


def log_page_progress(page_no: int, total_pages: int, item_type: str) -> None:
    """
    페이지 조회 진행 상황 로깅
    
    :param page_no: 현재 페이지 번호
    :param total_pages: 전체 페이지 수
    :param item_type: 항목 타입
    """
    logger.debug(f"Fetched page {page_no}/{total_pages} for {item_type}")


def log_fetch_complete(item_count: int, item_type: str) -> None:
    """
    모든 항목 조회 완료 로깅
    
    :param item_count: 조회된 항목 수
    :param item_type: 항목 타입
    """
    logger.info(f"Fetched total {item_count} {item_type} from all pages")
