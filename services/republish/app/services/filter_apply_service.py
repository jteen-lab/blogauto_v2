"""
필터 적용 서비스

기존 데이터(임시제목, 시드키워드)에 활성 필터를 적용하여 매칭 항목을 삭제합니다.
"""
import re
from dataclasses import dataclass

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.content_filter import ContentFilter
from ..models.title import TempTitle
from ..models.keyword import SeedKeyword

logger = get_logger("filter_apply", "app.log")


@dataclass
class FilterApplyResult:
    """필터 적용 결과."""

    deleted_titles: int = 0
    deleted_keywords: int = 0

    @property
    def total(self) -> int:
        """총 삭제 건수."""
        return self.deleted_titles + self.deleted_keywords


async def apply_filters_to_existing_data(
    db: AsyncSession,
) -> FilterApplyResult:
    """활성 필터를 기존 임시제목·시드키워드에 적용하여 매칭 항목 삭제.

    Args:
        db: DB 세션.

    Returns:
        삭제 건수 결과.
    """
    filters_result = await db.execute(
        select(ContentFilter).where(ContentFilter.is_active == True)
    )
    active_filters = filters_result.scalars().all()
    result = FilterApplyResult()

    for f in active_filters:
        val = f.filter_value
        match_title = f.target_type in ("title", "both")
        match_keyword = f.target_type in ("keyword", "both")

        if f.filter_type == "keyword":
            result.deleted_titles += await _delete_by_keyword(
                db, val, TempTitle, match_title
            )
            result.deleted_keywords += await _delete_by_keyword_kw(
                db, val, match_keyword
            )
        elif f.filter_type == "pattern":
            try:
                pattern = re.compile(val, re.IGNORECASE)
            except re.error:
                logger.warning(f"[FILTER_APPLY] 잘못된 정규식: {val}")
                continue
            result.deleted_titles += await _delete_by_pattern(
                db, pattern, TempTitle, match_title
            )
            result.deleted_keywords += await _delete_by_pattern_kw(
                db, pattern, match_keyword
            )

    await db.commit()

    logger.info(
        f"[FILTER_APPLY] 기존 데이터 필터 적용: "
        f"임시제목 {result.deleted_titles}건, "
        f"시드키워드 {result.deleted_keywords}건 삭제"
    )
    return result


async def _delete_by_keyword(
    db: AsyncSession, val: str, model: type, enabled: bool,
) -> int:
    """키워드 타입 필터로 임시제목 삭제."""
    if not enabled:
        return 0
    rows = await db.execute(
        select(model.id).where(model.title.ilike(f"%{val}%"))
    )
    ids = [r[0] for r in rows.all()]
    if ids:
        await db.execute(delete(model).where(model.id.in_(ids)))
    return len(ids)


async def _delete_by_keyword_kw(
    db: AsyncSession, val: str, enabled: bool,
) -> int:
    """키워드 타입 필터로 시드키워드 삭제."""
    if not enabled:
        return 0
    rows = await db.execute(
        select(SeedKeyword.id).where(SeedKeyword.keyword.ilike(f"%{val}%"))
    )
    ids = [r[0] for r in rows.all()]
    if ids:
        await db.execute(delete(SeedKeyword).where(SeedKeyword.id.in_(ids)))
    return len(ids)


async def _delete_by_pattern(
    db: AsyncSession, pattern: re.Pattern, model: type, enabled: bool,
) -> int:
    """정규식 패턴 필터로 임시제목 삭제."""
    if not enabled:
        return 0
    rows = await db.execute(select(model.id, model.title))
    to_delete = [tid for tid, title in rows.all() if pattern.search(title)]
    for tid in to_delete:
        await db.execute(delete(model).where(model.id == tid))
    return len(to_delete)


async def _delete_by_pattern_kw(
    db: AsyncSession, pattern: re.Pattern, enabled: bool,
) -> int:
    """정규식 패턴 필터로 시드키워드 삭제."""
    if not enabled:
        return 0
    rows = await db.execute(
        select(SeedKeyword.id, SeedKeyword.keyword)
    )
    to_delete = [kid for kid, kw in rows.all() if pattern.search(kw)]
    for kid in to_delete:
        await db.execute(delete(SeedKeyword).where(SeedKeyword.id == kid))
    return len(to_delete)
