"""
Holiday 도메인 로깅

HolidayService에서 사용하는 로깅 함수들
"""
import logging
from typing import Optional

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


def log_initialization_skipped(skipped_count: int, existing_years: set[int]) -> None:
    """
    초기화 건너뛴 연도 로깅
    
    :param skipped_count: 건너뛴 연도 수
    :param existing_years: 이미 존재하는 연도 집합
    """
    if skipped_count > 0:
        logger.info(
            f"Skipping {skipped_count} years that already exist in hash table: "
            f"{sorted(existing_years)}"
        )


def log_initialization_not_needed(initial_year: int, current_year: int) -> None:
    """
    초기화 불필요 로깅
    
    :param initial_year: 시작 연도
    :param current_year: 현재 연도
    """
    logger.info(
        f"All years from {initial_year} to {current_year} already exist in hash table. "
        f"Skipping initialization."
    )


def log_initialization_start(
        initial_year: int, current_year: int, total_years: int, skipped_count: int
) -> None:
    """
    초기화 시작 로깅
    
    :param initial_year: 시작 연도
    :param current_year: 현재 연도
    :param total_years: 동기화할 총 연도 수
    :param skipped_count: 건너뛴 연도 수
    """
    logger.info(
        f"Initializing historical holiday data from {initial_year} to {current_year} "
        f"({total_years} years to sync, {skipped_count} years skipped)"
    )


def log_initialization_progress(year: int, current: int, total: int) -> None:
    """
    초기화 진행 상황 로깅
    
    :param year: 현재 동기화 중인 연도
    :param current: 현재 진행 번호
    :param total: 전체 연도 수
    """
    logger.debug(f"   [{current}/{total}] {year} year initialized")


def log_initialization_complete(total_years: int) -> None:
    """
    초기화 완료 로깅
    
    :param total_years: 완료된 총 연도 수
    """
    logger.info(
        f"Historical data initialization completed: "
        f"all {total_years} years succeeded"
    )

