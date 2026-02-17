"""
재고 기반 생성 트리거 서비스

블로그의 CrawledPost 재고 수준을 확인하고,
BlogGrowthSetting 임계값과 비교하여 생성이 필요한지 판단합니다.

설계 문서: generation_module_workplan.md - Phase 4 - 4.2.3
"""
import json
import logging
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models.blog import Blog
from ...models.title import MainTitle
from ...models.crawled_post import CrawledPost
from ...models.blog_growth_setting import BlogGrowthSetting

logger = logging.getLogger(__name__)

# BlogGrowthSetting이 없을 때 기본 재고 기준값
DEFAULT_INVENTORY_THRESHOLD = 3


@dataclass
class InventoryCheckResult:
    """재고 확인 결과"""
    blog_id: int
    current_inventory: int
    threshold: int
    needs_generation: bool
    growth_stage: str
    available_title_id: Optional[int] = None
    available_title_text: Optional[str] = None


class InventoryTrigger:
    """
    재고 기반 생성 트리거 서비스

    발행 후 또는 플로우 실행 시 호출되어
    재고 부족 여부를 판단하고 생성 대상 제목을 선택합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_inventory(
        self, blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> InventoryCheckResult:
        """
        블로그의 재고 상태를 확인하고 생성 필요 여부를 판단

        Args:
            blog_id: 블로그 ID
            module_settings: 모듈 설정 (Module.settings)

        Returns:
            InventoryCheckResult: 재고 확인 결과
        """
        # 1. 현재 재고 수량 조회
        inventory_count = await self._get_inventory_count(blog_id)

        # 2. 임계값 조회 (모듈 설정 우선, BlogGrowthSetting 폴백)
        threshold, growth_stage = await self._get_threshold(
            blog_id, module_settings
        )

        # 3. 생성 필요 여부 판단
        needs_generation = inventory_count < threshold

        logger.info(
            f"[INVENTORY] blog_id={blog_id} | "
            f"재고={inventory_count} | 기준={threshold} | "
            f"단계={growth_stage} | "
            f"생성필요={'예' if needs_generation else '아니오'}"
        )

        # 4. 생성이 필요하면 사용 가능한 제목 조회
        title_id = None
        title_text = None
        if needs_generation:
            title = await self._find_available_title(blog_id)
            if title:
                title_id = title.id
                title_text = title.title
            else:
                needs_generation = False
                logger.info(
                    f"[INVENTORY] blog_id={blog_id} | "
                    f"재고 부족이지만 사용 가능한 제목 없음"
                )

        return InventoryCheckResult(
            blog_id=blog_id,
            current_inventory=inventory_count,
            threshold=threshold,
            needs_generation=needs_generation,
            growth_stage=growth_stage,
            available_title_id=title_id,
            available_title_text=title_text,
        )

    async def find_available_titles(
        self, blog_id: int, limit: int = 5
    ) -> List[MainTitle]:
        """
        블로그에 매칭된 사용 가능한 제목 목록 조회

        Args:
            blog_id: 블로그 ID
            limit: 최대 조회 수

        Returns:
            사용 가능한 MainTitle 목록
        """
        # 1. matched_blog_ids에 blog_id가 포함된 제목 조회
        blog_id_str = str(blog_id)
        query = (
            select(MainTitle)
            .where(
                MainTitle.status == "available",
                MainTitle.matched_blog_ids.isnot(None),
                MainTitle.matched_blog_ids.contains(blog_id_str),
            )
            .order_by(MainTitle.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        matched_titles = list(result.scalars().all())

        # 2. 매칭된 제목이 부족하면 미매칭 available 제목 보충
        if len(matched_titles) < limit:
            remaining = limit - len(matched_titles)
            matched_ids = [t.id for t in matched_titles]

            fallback_query = (
                select(MainTitle)
                .where(
                    MainTitle.status == "available",
                    MainTitle.id.notin_(matched_ids) if matched_ids else True,
                )
                .order_by(MainTitle.created_at.asc())
                .limit(remaining)
            )
            fallback_result = await self.db.execute(fallback_query)
            matched_titles.extend(fallback_result.scalars().all())

        return matched_titles

    async def _get_inventory_count(self, blog_id: int) -> int:
        """
        블로그의 현재 CrawledPost 재고 수량 조회

        source='generated'이고 아직 발행되지 않은 글의 수를 반환합니다.
        """
        query = (
            select(func.count(CrawledPost.id))
            .where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.source == "generated",
                CrawledPost.published_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _get_threshold(
        self, blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> tuple[int, str]:
        """
        재고 임계값 조회 (모듈 설정 우선, BlogGrowthSetting 폴백)

        Args:
            blog_id: 블로그 ID
            module_settings: 모듈 설정 (Module.settings)

        Returns:
            (임계값, 성장단계) 튜플
        """
        # 모듈 설정에서 재고 설정을 우선 사용
        inv = (module_settings or {}).get("inventory", {})
        if inv:
            # Blog 조회 (현재 발행글 수 확인용)
            query = select(Blog).where(Blog.id == blog_id)
            result = await self.db.execute(query)
            blog = result.scalar_one_or_none()

            if not blog:
                logger.warning(
                    f"[INVENTORY] 블로그를 찾을 수 없음: id={blog_id}"
                )
                return DEFAULT_INVENTORY_THRESHOLD, "unknown"

            current_post_count = blog.total_post_count or 0
            rapid_threshold = inv.get("rapid_growth_threshold", 50)
            growth_threshold = inv.get("growth_threshold", 150)

            if current_post_count <= rapid_threshold:
                threshold_val = inv.get("rapid_growth_inventory", 10)
                logger.debug(
                    f"[INVENTORY] 임계값 결정: 모듈설정 사용 | "
                    f"단계=rapid_growth | 기준={threshold_val} | "
                    f"posts={current_post_count}"
                )
                return threshold_val, "rapid_growth"
            elif current_post_count <= growth_threshold:
                threshold_val = inv.get("growth_inventory", 5)
                logger.debug(
                    f"[INVENTORY] 임계값 결정: 모듈설정 사용 | "
                    f"단계=growth | 기준={threshold_val} | "
                    f"posts={current_post_count}"
                )
                return threshold_val, "growth"
            else:
                threshold_val = inv.get("stable_inventory", 2)
                logger.debug(
                    f"[INVENTORY] 임계값 결정: 모듈설정 사용 | "
                    f"단계=stable | 기준={threshold_val} | "
                    f"posts={current_post_count}"
                )
                return threshold_val, "stable"

        # 기존 BlogGrowthSetting 폴백 로직
        # Blog 조회 (growth_setting 포함)
        query = (
            select(Blog)
            .where(Blog.id == blog_id)
            .options(selectinload(Blog.growth_setting))
        )
        result = await self.db.execute(query)
        blog = result.scalar_one_or_none()

        if not blog:
            logger.warning(
                f"[INVENTORY] 블로그를 찾을 수 없음: id={blog_id}"
            )
            return DEFAULT_INVENTORY_THRESHOLD, "unknown"

        current_post_count = blog.total_post_count or 0

        if blog.growth_setting:
            threshold = blog.growth_setting.get_inventory_threshold(
                current_post_count
            )
            stage = blog.growth_setting.get_growth_stage(
                current_post_count
            )
            logger.debug(
                f"[INVENTORY] 임계값 결정: BlogGrowthSetting 사용 | "
                f"단계={stage} | 기준={threshold} | "
                f"posts={current_post_count}"
            )
            return threshold, stage

        # BlogGrowthSetting이 없으면 기본값 사용
        logger.info(
            f"[INVENTORY] blog_id={blog_id} | "
            f"성장 설정 없음, 기본값 사용: {DEFAULT_INVENTORY_THRESHOLD}"
        )
        return DEFAULT_INVENTORY_THRESHOLD, "default"

    async def _find_available_title(
        self, blog_id: int
    ) -> Optional[MainTitle]:
        """
        블로그에 사용 가능한 제목 1개 조회

        우선순위:
        1. matched_blog_ids에 해당 blog_id가 포함된 제목
        2. 매칭 정보 없는 available 제목 (폴백)
        """
        blog_id_str = str(blog_id)

        # 1차: 매칭된 제목
        query = (
            select(MainTitle)
            .where(
                MainTitle.status == "available",
                MainTitle.matched_blog_ids.isnot(None),
                MainTitle.matched_blog_ids.contains(blog_id_str),
            )
            .order_by(MainTitle.created_at.asc())
            .limit(1)
        )
        result = await self.db.execute(query)
        title = result.scalar_one_or_none()

        if title:
            logger.debug(
                f"[INVENTORY] 제목 선택: 매칭 제목 | "
                f"id={title.id} | '{title.title[:30]}'"
            )
            return title

        # 2차: 미매칭 available 제목 (폴백)
        fallback_query = (
            select(MainTitle)
            .where(MainTitle.status == "available")
            .order_by(MainTitle.created_at.asc())
            .limit(1)
        )
        fallback_result = await self.db.execute(fallback_query)
        fallback_title = fallback_result.scalar_one_or_none()
        if fallback_title:
            logger.debug(
                f"[INVENTORY] 제목 선택: 폴백 제목 | "
                f"id={fallback_title.id} | '{fallback_title.title[:30]}'"
            )
        return fallback_title
