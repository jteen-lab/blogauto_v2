"""
오토런 동작 로그 메시지 빌더

수집/대량수집 모듈 실행 결과 dict를 받아 사용자 친화 메시지와
통계 카운트(processed/success/failed)를 생성합니다.

기존 ``_save_autorun_log()`` 는 ``result.get("message")`` 를 그대로
보여주었지만 사용자 보고에 따르면 "수집"이라는 단어만 보이고 통계가
표시되지 않았다. 이 모듈은 두 가지를 해결한다:

1. ``message`` 를 다시 조립하여 통계가 포함된 한국어 문장 반환.
2. ``posts_processed / posts_success / posts_failed`` 컬럼에 넣을
   숫자도 같이 산출 (기존 NULL 채움).

사용 패턴::

    stats = build_collect_log_stats(result, action="collect")
    log_message = stats.message
    db.add(AutorunLog.create_execution_log(
        ..., message=log_message,
        ...
    ))
    # 컬럼 직접 세팅 (create_execution_log 가 받지 않는 필드)
    log.posts_processed = stats.posts_processed
    log.posts_success = stats.posts_success
    log.posts_failed = stats.posts_failed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CollectLogStats:
    """수집/대량수집 로그용 통계 묶음.

    Attributes:
        message: AutorunLog.message 컬럼에 저장할 사람이 읽기 좋은 문장.
        posts_processed: 총 처리 건수 (성공+실패) - posts_processed 컬럼.
        posts_success: 성공 건수 - posts_success 컬럼.
        posts_failed: 실패 건수 - posts_failed 컬럼.
    """

    message: str
    posts_processed: Optional[int] = None
    posts_success: Optional[int] = None
    posts_failed: Optional[int] = None


def _safe_int(value: Any, default: int = 0) -> int:
    """안전한 int 변환 (None/잘못된 타입이면 기본값)."""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _truncate_error(text: str, limit: int = 120) -> str:
    """긴 에러 메시지를 안전하게 자른다."""
    if not text:
        return "알 수 없는 오류"
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _build_collect_success_message(result: Dict[str, Any]) -> CollectLogStats:
    """``action="collect"`` 성공 시 메시지/통계 빌드.

    ``_execute_collect_module()`` 의 성공 응답 구조::

        {
            "success": True,
            "collected_count": int,   # 호환용 (사용 안 함)
            "saved_count": int,       # 호환용 (사용 안 함)
            "results": {
                "naver_news":   {"success": bool, "collected": N, "saved": M},
                "google_trends": {"success": bool, "collected": N, "saved": M},
                ...
            },
            "extraction_result": {"keywords_saved": N} | None,
            ...
        }

    제목 소스(TempTitle 저장)와 키워드 소스(SeedKeyword 저장)를 구분하여
    저장 건수를 합산한다. ``deduplication`` 등 수집 소스가 아닌 메타 키는
    집계에서 제외한다.
    """
    # 키워드 소스 (SeedKeyword 테이블 저장)
    keyword_source_codes = {"google_trends", "naver_datalab", "naver_ads"}
    # 제목 소스 (TempTitle 테이블 저장). keyword_search 는 키워드 기반
    # 제목 수집, bulk_collect 는 레거시 인라인 대량 제목 수집으로 둘 다 제목.
    title_source_codes = {
        "naver_news", "google_news", "naver_webdoc",
        "keyword_search", "bulk_collect",
    }
    results_detail: Dict[str, Any] = result.get("results", {}) or {}

    saved_titles = 0
    saved_keywords = 0
    failed_sources = 0
    success_sources = 0
    source_count = 0

    for src, src_result in results_detail.items():
        if not isinstance(src_result, dict):
            continue
        # 수집 소스가 아닌 메타 키(deduplication 등)는 통계에서 제외
        is_title = src in title_source_codes
        is_keyword = src in keyword_source_codes
        if not is_title and not is_keyword:
            continue
        source_count += 1
        if src_result.get("success"):
            success_sources += 1
            saved = _safe_int(src_result.get("saved"))
            if is_title:
                saved_titles += saved
            else:
                saved_keywords += saved
        else:
            failed_sources += 1

    extraction = result.get("extraction_result") or {}
    extracted = _safe_int(extraction.get("keywords_saved"))

    parts = []
    if saved_titles:
        parts.append(f"제목 {saved_titles}개")
    if saved_keywords:
        parts.append(f"키워드 {saved_keywords}개")
    if extracted:
        parts.append(f"키워드추출 {extracted}개")

    if parts:
        body = ", ".join(parts) + " 수집"
    else:
        body = "수집 완료(저장 0개)"

    if source_count:
        body += f" (소스 {source_count}개"
        if failed_sources:
            body += f", 실패 {failed_sources}개"
        body += ")"

    posts_processed = saved_titles + saved_keywords + extracted
    return CollectLogStats(
        message=body,
        posts_processed=posts_processed,
        posts_success=posts_processed,
        posts_failed=0,
    )


def _build_collect_failed_message(result: Dict[str, Any]) -> CollectLogStats:
    """``action="collect"`` 실패 시 메시지/통계 빌드."""
    err = _truncate_error(str(result.get("message", "")))
    return CollectLogStats(
        message=f"수집 실패: {err}",
        posts_processed=0,
        posts_success=0,
        posts_failed=1,
    )


def _build_bulk_collect_success_message(result: Dict[str, Any]) -> CollectLogStats:
    """``action="bulk_collect"`` 성공 시 메시지/통계 빌드.

    ``cycle_runner._build_cycle_result()`` 의 성공 응답 구조::

        {
            "success": True,
            "processed": int,
            "failed": int,
            "duration_sec": int,
            "chunk_size": int,
            "ingest_summary": {
                "posts_ingested": int,
                "blogs_processed": int,
                "skipped_duplicate": int,
                "failed": int,
            } | None,
        }
    """
    titles = _safe_int(result.get("titles_collected", result.get("processed")))
    failed = _safe_int(result.get("failed"))
    duration = _safe_int(result.get("duration_sec"))
    blogs = _safe_int(result.get("blogs_processed"))
    posts = _safe_int(result.get("posts_ingested"))

    # 3단 통계: 블로그 / 글주소 적재 / 제목 수집
    parts = []
    if blogs:
        parts.append(f"블로그 {blogs}개")
    if posts:
        parts.append(f"글주소 {posts}개 적재")
    parts.append(f"제목 {titles}개 수집")
    body = " / ".join(parts)

    extras = []
    if failed:
        extras.append(f"실패 {failed}개")
    if duration:
        extras.append(f"소요 {duration}초")
    if extras:
        body += " (" + ", ".join(extras) + ")"

    return CollectLogStats(
        message=body,
        posts_processed=titles + failed,
        posts_success=titles,
        posts_failed=failed,
    )


def _build_bulk_collect_failed_message(result: Dict[str, Any]) -> CollectLogStats:
    """``action="bulk_collect"`` 실패 시 메시지/통계 빌드."""
    err = _truncate_error(str(result.get("message", "")))
    return CollectLogStats(
        message=f"대량 수집 실패: {err}",
        posts_processed=0,
        posts_success=0,
        posts_failed=1,
    )


def build_collect_log_stats(
    result: Dict[str, Any],
    action: str,
) -> Optional[CollectLogStats]:
    """수집/대량수집 결과 dict에서 동작 로그용 통계 묶음을 생성.

    Args:
        result: 모듈 실행 결과 dict.
        action: 액션 코드. ``"collect"`` 또는 ``"bulk_collect"`` 만 처리.

    Returns:
        ``CollectLogStats`` 인스턴스. 처리 대상이 아닌 액션이면 ``None``.

    Examples:
        >>> result = {
        ...     "success": True,
        ...     "results": {
        ...         "naver_news": {"success": True, "saved": 152},
        ...         "google_trends": {"success": True, "saved": 20},
        ...     },
        ... }
        >>> stats = build_collect_log_stats(result, "collect")
        >>> stats.message
        '제목 152개, 키워드 20개 수집 (소스 2개)'
        >>> stats.posts_processed
        172
    """
    try:
        if action not in ("collect", "bulk_collect"):
            return None
        # 스킵(콜백 적체 등)은 실패가 아니므로 원본 사유 메시지를 그대로 사용
        if result.get("skipped"):
            return CollectLogStats(
                message=str(result.get("message") or "건너뜀"),
                posts_processed=0,
                posts_success=0,
                posts_failed=0,
            )
        if action == "collect":
            if result.get("success"):
                return _build_collect_success_message(result)
            return _build_collect_failed_message(result)
        # action == "bulk_collect"
        if result.get("success"):
            return _build_bulk_collect_success_message(result)
        return _build_bulk_collect_failed_message(result)
    except Exception as exc:  # noqa: BLE001
        # 로그 빌드 실패가 본 작업 결과까지 망가뜨리면 안 됨.
        logger.warning(
            "[AUTORUN_MSG] 로그 메시지 빌드 실패 | action=%s | error=%s",
            action, exc,
        )
        return None
