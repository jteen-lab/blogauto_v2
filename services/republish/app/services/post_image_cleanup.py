"""발행글 이미지 파일 정리 공용 유틸.

CrawledPost에 연결된 이미지 파일(대표/GenerationHistory 대표/섹션)을 디스크에서
삭제한다. 정식제목 삭제(titles 라우터)와 저장 정리(재발행 리뉴얼 P4)에서 공용 사용.
DB 메타는 건드리지 않고 파일만 삭제한다(메타 보존은 호출측 책임).
"""
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.logger import get_logger
from ..models.crawled_post import CrawledPost
from ..models.generation_history import GenerationHistory

logger = get_logger("post_image_cleanup", "app.log")


def _remove_file(image_url: Optional[str]) -> int:
    """image_url의 파일명을 추출해 저장 디렉토리에서 삭제. 삭제 수(0/1) 반환."""
    if not image_url:
        return 0
    try:
        filename = image_url.split("/")[-1]
        path = Path(settings.image_storage_dir) / filename
        if path.exists():
            path.unlink()
            return 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IMG_CLEANUP] 이미지 삭제 실패: %s", exc)
    return 0


async def delete_post_images(post: CrawledPost, db: AsyncSession) -> int:
    """CrawledPost에 연결된 이미지 파일(대표/섹션)을 삭제.

    Args:
        post: 삭제 대상 CrawledPost.
        db: 비동기 DB 세션(GenerationHistory 조회용).

    Returns:
        삭제된 이미지 파일 수.
    """
    deleted = 0

    # 대표 이미지
    deleted += _remove_file(post.image_url)

    # GenerationHistory 연결 이미지(대표 + 섹션)
    if post.generation_history_id:
        gh = (await db.execute(
            select(GenerationHistory)
            .where(GenerationHistory.id == post.generation_history_id)
        )).scalar_one_or_none()
        if gh:
            deleted += _remove_file(gh.image_url)
            if gh.section_images:
                try:
                    items = json.loads(gh.section_images)
                    if isinstance(items, list):
                        for item in items:
                            url = (
                                item.get("image_url")
                                if isinstance(item, dict) else None
                            )
                            deleted += _remove_file(url)
                except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
                    logger.warning("[IMG_CLEANUP] 섹션 이미지 삭제 실패: %s", exc)

    return deleted
