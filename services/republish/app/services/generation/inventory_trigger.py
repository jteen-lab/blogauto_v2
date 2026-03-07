"""
재고 기반 생성 트리거 서비스

블로그의 CrawledPost 재고 수준을 확인하고,
Growth Profile 기반 임계값과 비교하여 생성이 필요한지 판단합니다.

설계 문서: generation_module_workplan.md - Phase 4 - 4.2.3
"""
import logging
import random
from typing import Optional, List, Tuple, Set
from dataclasses import dataclass

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.title import MainTitle
from ...models.crawled_post import CrawledPost
from ...models.category import BlogCategory

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
        min_inventory: Optional[int] = None,
        module_settings: Optional[dict] = None,
    ) -> InventoryCheckResult:
        """
        블로그의 재고 상태를 확인하고 생성 필요 여부를 판단

        Args:
            blog_id: 블로그 ID
            min_inventory: GP에서 결정된 최소 보유 수 (None이면 기본값 사용)
            module_settings: 프롬프트 모듈 settings (카테고리 필터용)

        Returns:
            InventoryCheckResult: 재고 확인 결과
        """
        # 1. 현재 재고 수량 조회
        inventory_count = await self._get_inventory_count(blog_id)

        # 2. 임계값 결정 (GP에서 직접 전달, 없으면 기본값)
        threshold = min_inventory if min_inventory is not None else DEFAULT_INVENTORY_THRESHOLD
        growth_stage = "gp_managed" if min_inventory is not None else "default"

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
            title = await self._find_available_title(blog_id, module_settings)
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
        self, blog_id: int, limit: int = 5,
        module_settings: Optional[dict] = None,
    ) -> List[MainTitle]:
        """
        블로그에 매칭된 사용 가능한 제목 목록 조회 (카테고리 필터링 적용)

        카테고리 소스 우선순위:
        1순위: module_settings.categories (프롬프트 모듈 설정)
        2순위: BlogCategory (블로그 설정)
        카테고리 미설정이면 전체 available 대상

        Args:
            blog_id: 블로그 ID
            limit: 최대 조회 수
            module_settings: 프롬프트 모듈 settings (카테고리 필터용)

        Returns:
            사용 가능한 MainTitle 목록
        """
        blog_id_str = str(blog_id)

        # 카테고리 소스 결정: 모듈 설정 우선, 없으면 BlogCategory 폴백
        if module_settings and module_settings.get("categories"):
            subtopic_ids, topic_only_ids = self._parse_module_categories(
                module_settings["categories"]
            )
            category_source = "module_settings"
        else:
            subtopic_ids, topic_only_ids = await self._get_blog_category_filter_ids(blog_id)
            category_source = "blog_category"

        has_category = bool(subtopic_ids or topic_only_ids)

        # 카테고리 OR 조건 빌드
        category_conditions = []
        if subtopic_ids:
            category_conditions.append(
                MainTitle.subtopic_id.in_(list(subtopic_ids))
            )
        if topic_only_ids:
            category_conditions.append(
                MainTitle.topic_id.in_(list(topic_only_ids))
            )

        if has_category:
            logger.debug(
                f"[INVENTORY] find_available_titles 카테고리 필터 | "
                f"blog_id={blog_id} | 소스={category_source} | "
                f"subtopic_ids={subtopic_ids} | topic_only_ids={topic_only_ids}"
            )

        # 1차: 매칭 + 카테고리 일치 제목
        matched_titles = await self._query_titles_list(
            blog_id_str, category_conditions,
            matched_only=True, limit=limit,
        )

        # 2차: 부족하면 카테고리 일치 available 제목 보충 (매칭 무관)
        if len(matched_titles) < limit:
            remaining = limit - len(matched_titles)
            exclude_ids = [t.id for t in matched_titles]
            fallback_titles = await self._query_titles_list(
                blog_id_str, category_conditions,
                matched_only=False, limit=remaining,
                exclude_ids=exclude_ids,
            )
            matched_titles.extend(fallback_titles)

        # 3차: 카테고리 미설정 블로그만 전체 available 폴백
        if not matched_titles and not has_category:
            matched_titles = await self._query_titles_list(
                blog_id_str, [],
                matched_only=False, limit=limit,
            )

        return matched_titles

    async def _query_titles_list(
        self,
        blog_id_str: str,
        category_conditions: list,
        matched_only: bool,
        limit: int,
        exclude_ids: Optional[List[int]] = None,
    ) -> List[MainTitle]:
        """
        필터 조건 조합으로 제목 목록 조회

        Args:
            blog_id_str: 블로그 ID 문자열
            category_conditions: 카테고리 OR 조건 리스트
            matched_only: True면 매칭 제목만, False면 전체 available
            limit: 최대 조회 수
            exclude_ids: 제외할 제목 ID 목록

        Returns:
            MainTitle 목록
        """
        conditions = [MainTitle.status == "available"]

        if matched_only:
            conditions.append(MainTitle.matched_blog_ids.isnot(None))
            conditions.append(MainTitle.matched_blog_ids.contains(blog_id_str))

        if category_conditions:
            conditions.append(or_(*category_conditions))

        if exclude_ids:
            conditions.append(MainTitle.id.notin_(exclude_ids))

        query = (
            select(MainTitle)
            .where(*conditions)
            .order_by(MainTitle.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

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

    def _parse_module_categories(
        self, categories: list
    ) -> Tuple[Set[int], Set[int]]:
        """
        모듈 settings.categories에서 subtopic_id / topic_id 집합 분리

        Args:
            categories: [{"topic_id": 1, "subtopic_id": 3}, ...]

        Returns:
            (subtopic_ids, topic_only_ids) 튜플
        """
        subtopic_ids: Set[int] = set()
        topic_only_ids: Set[int] = set()

        for cat in categories:
            if cat.get("subtopic_id"):
                subtopic_ids.add(cat["subtopic_id"])
            elif cat.get("topic_id"):
                topic_only_ids.add(cat["topic_id"])

        return subtopic_ids, topic_only_ids

    async def _get_blog_category_filter_ids(
        self, blog_id: int
    ) -> Tuple[Set[int], Set[int]]:
        """
        블로그의 활성 카테고리에서 subtopic_id / topic_id 집합 조회

        Args:
            blog_id: 블로그 ID

        Returns:
            (subtopic_ids, topic_only_ids) 튜플
        """
        bc_query = select(BlogCategory).where(
            BlogCategory.blog_id == blog_id,
            BlogCategory.is_active == True,
        )
        bc_result = await self.db.execute(bc_query)
        blog_categories = bc_result.scalars().all()

        subtopic_ids: Set[int] = set()
        topic_only_ids: Set[int] = set()

        for bc in blog_categories:
            if bc.subtopic_id:
                subtopic_ids.add(bc.subtopic_id)
            elif bc.topic_id:
                topic_only_ids.add(bc.topic_id)

        return subtopic_ids, topic_only_ids

    async def _find_available_title(
        self, blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> Optional[MainTitle]:
        """
        블로그에 사용 가능한 제목 1개를 랜덤 선택 (카테고리 필터링 적용)

        카테고리 소스 우선순위:
        1순위: module_settings.categories (프롬프트 모듈 설정)
        2순위: BlogCategory (블로그 설정)

        제목 선택 우선순위:
        1. 매칭 + 카테고리 일치 제목
        2. 카테고리 일치하는 available 제목 (매칭 무관)
        카테고리 미설정이면 전체 대상에서 선택
        """
        blog_id_str = str(blog_id)

        # 카테고리 소스 결정: 모듈 설정 우선, 없으면 BlogCategory 폴백
        if module_settings and module_settings.get("categories"):
            subtopic_ids, topic_only_ids = self._parse_module_categories(
                module_settings["categories"]
            )
            category_source = "module_settings"
        else:
            subtopic_ids, topic_only_ids = await self._get_blog_category_filter_ids(blog_id)
            category_source = "blog_category"

        has_category = bool(subtopic_ids or topic_only_ids)

        # 카테고리 OR 조건 빌드
        category_conditions = []
        if subtopic_ids:
            category_conditions.append(
                MainTitle.subtopic_id.in_(list(subtopic_ids))
            )
        if topic_only_ids:
            category_conditions.append(
                MainTitle.topic_id.in_(list(topic_only_ids))
            )

        if has_category:
            logger.debug(
                f"[INVENTORY] 카테고리 필터 | blog_id={blog_id} | "
                f"소스={category_source} | "
                f"subtopic_ids={subtopic_ids} | topic_only_ids={topic_only_ids}"
            )

        # 1차: 매칭 + 카테고리 일치 제목
        title = await self._query_title_with_filters(
            blog_id_str, category_conditions, matched_only=True
        )
        if title:
            logger.debug(
                f"[INVENTORY] 제목 선택: 매칭+카테고리 | "
                f"id={title.id} | '{title.title[:30]}'"
            )
            return title

        # 2차: 카테고리 일치 available 제목 (매칭 무관)
        title = await self._query_title_with_filters(
            blog_id_str, category_conditions, matched_only=False
        )
        if title:
            logger.debug(
                f"[INVENTORY] 제목 선택: 카테고리 일치 | "
                f"id={title.id} | '{title.title[:30]}'"
            )
            return title

        # 카테고리가 설정된 블로그인데 일치 제목 없음 -> None
        if has_category:
            logger.warning(
                f"[INVENTORY] blog_id={blog_id} | "
                f"카테고리 일치 제목 없음 (subtopic={subtopic_ids}, "
                f"topic={topic_only_ids})"
            )
            return None

        # 카테고리 미설정 블로그 -> 전체 available 제목 폴백
        return await self._query_title_with_filters(
            blog_id_str, [], matched_only=False
        )

    async def _query_title_with_filters(
        self,
        blog_id_str: str,
        category_conditions: list,
        matched_only: bool,
    ) -> Optional[MainTitle]:
        """
        필터 조건 조합으로 후보 제목 조회 후 랜덤 1개 선택

        Args:
            blog_id_str: 블로그 ID 문자열
            category_conditions: 카테고리 OR 조건 리스트
            matched_only: True면 매칭 제목만, False면 전체 available

        Returns:
            MainTitle 또는 None (랜덤 선택)
        """
        conditions = [MainTitle.status == "available"]

        if matched_only:
            conditions.append(MainTitle.matched_blog_ids.isnot(None))
            conditions.append(MainTitle.matched_blog_ids.contains(blog_id_str))

        if category_conditions:
            conditions.append(or_(*category_conditions))

        query = (
            select(MainTitle)
            .where(*conditions)
            .limit(10)
        )
        result = await self.db.execute(query)
        candidates = list(result.scalars().all())
        return random.choice(candidates) if candidates else None
