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
from .inventory_category_mixin import InventoryCategoryMixin

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


class InventoryTrigger(InventoryCategoryMixin):
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

        # F4: 프롬프트 모듈 니치 강제(옵트인 차단, 모듈 단위).
        subtopic_ids, topic_only_ids, category_source = self._apply_niche(
            module_settings, subtopic_ids, topic_only_ids, category_source
        )

        has_category = bool(subtopic_ids or topic_only_ids)
        sibling_ids = await self._resolve_siblings(blog_id, module_settings)

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
            sibling_blog_ids=sibling_ids,
        )

        # 2차: 부족하면 카테고리 일치 available 제목 보충 (매칭 무관)
        if len(matched_titles) < limit:
            remaining = limit - len(matched_titles)
            exclude_ids = [t.id for t in matched_titles]
            fallback_titles = await self._query_titles_list(
                blog_id_str, category_conditions,
                matched_only=False, limit=remaining,
                exclude_ids=exclude_ids,
                sibling_blog_ids=sibling_ids,
            )
            matched_titles.extend(fallback_titles)

        # 3차: 카테고리 미설정 블로그만 전체 available 폴백
        if not matched_titles and not has_category:
            matched_titles = await self._query_titles_list(
                blog_id_str, [],
                matched_only=False, limit=limit,
                sibling_blog_ids=sibling_ids,
            )

        return matched_titles

    async def count_available_titles(
        self,
        blog_id: int,
        module_settings: Optional[dict] = None,
    ) -> int:
        """이 블로그가 **실제로 꺼내 쓸 수 있는** 제목 수.

        키워드 모듈의 재고 판단이 이 값을 쓴다. 세는 기준과 꺼내는 기준이
        다르면, 꺼낼 수 없는 제목을 재고로 세어 "재고 충분" 으로 판단하거나
        (생성이 굶는다) 반대로 영원히 부족으로 판단해 API 를 낭비한다.
        실제로 후자가 일어났다(키워드 관리 검토서 D-5).

        Args:
            blog_id: 블로그 ID
            module_settings: 프롬프트 모듈 settings(카테고리/니치 강제용)

        Returns:
            꺼내 쓸 수 있는 제목 수
        """
        if module_settings and module_settings.get("categories"):
            subtopic_ids, topic_only_ids = self._parse_module_categories(
                module_settings["categories"]
            )
            source = "module_settings"
        else:
            subtopic_ids, topic_only_ids = \
                await self._get_blog_category_filter_ids(blog_id)
            source = "blog_category"

        subtopic_ids, topic_only_ids, source = self._apply_niche(
            module_settings, subtopic_ids, topic_only_ids, source
        )

        conditions = [MainTitle.status != "archived"]
        conditions.append(
            MainTitle.id.notin_(
                self._published_title_ids_subquery(str(blog_id))
            )
        )
        category_conditions = []
        if subtopic_ids:
            category_conditions.append(
                MainTitle.subtopic_id.in_(list(subtopic_ids)))
        if topic_only_ids:
            category_conditions.append(
                MainTitle.topic_id.in_(list(topic_only_ids)))
        if category_conditions:
            conditions.append(or_(*category_conditions))

        count = (await self.db.execute(
            select(func.count(MainTitle.id)).where(*conditions)
        )).scalar() or 0
        logger.debug(
            f"[INVENTORY] 사용 가능 제목 {count}개 | blog_id={blog_id} | "
            f"소스={source}"
        )
        return count

    async def _query_titles_list(
        self,
        blog_id_str: str,
        category_conditions: list,
        matched_only: bool,
        limit: int,
        exclude_ids: Optional[List[int]] = None,
        sibling_blog_ids: Optional[List[int]] = None,
    ) -> List[MainTitle]:
        """
        필터 조건 조합으로 제목 목록 조회 (블로그별 재고 정책)

        Args:
            blog_id_str: 블로그 ID 문자열
            category_conditions: 카테고리 OR 조건 리스트
            matched_only: True면 매칭 제목만, False면 카테고리 일치 제목 전체
            limit: 최대 조회 수
            exclude_ids: 제외할 제목 ID 목록

        Returns:
            MainTitle 목록
        """
        # archived 제외, 이 블로그가 이미 만든 제목 제외 (블로그별)
        conditions = [MainTitle.status != "archived"]
        conditions.append(
            MainTitle.id.notin_(
                self._published_title_ids_subquery(blog_id_str, sibling_blog_ids)
            )
        )

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

        # F4: 프롬프트 모듈 니치 강제(옵트인 차단, 모듈 단위).
        subtopic_ids, topic_only_ids, category_source = self._apply_niche(
            module_settings, subtopic_ids, topic_only_ids, category_source
        )

        has_category = bool(subtopic_ids or topic_only_ids)
        sibling_ids = await self._resolve_siblings(blog_id, module_settings)

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

        logger.info(
            f"[INVENTORY] 제목 검색 시작 | blog_id={blog_id} | "
            f"카테고리소스={category_source} | "
            f"has_category={has_category} | "
            f"subtopic_ids={subtopic_ids} | topic_only_ids={topic_only_ids}"
        )

        # 1차: 매칭 + 카테고리(subtopic) 일치 제목
        title = await self._query_title_with_filters(
            blog_id_str, category_conditions, matched_only=True,
            sibling_blog_ids=sibling_ids,
        )
        if title:
            logger.info(f"[INVENTORY] 제목 선택: 1차(매칭+카테고리) | id={title.id}")
            return title

        # 2차: 카테고리(subtopic) 일치 available 제목 (매칭 무관)
        title = await self._query_title_with_filters(
            blog_id_str, category_conditions, matched_only=False,
            sibling_blog_ids=sibling_ids,
        )
        if title:
            logger.info(f"[INVENTORY] 제목 선택: 2차(카테고리만) | id={title.id}")
            return title

        # 2.5차: subtopic 실패 시 topic 레벨로 폴백
        if has_category and subtopic_ids:
            topic_ids_all = self._extract_all_topic_ids(module_settings)
            if topic_ids_all:
                topic_cond = [MainTitle.topic_id.in_(list(topic_ids_all))]
                title = await self._query_title_with_filters(
                    blog_id_str, topic_cond, matched_only=False,
                    sibling_blog_ids=sibling_ids,
                )
                if title:
                    logger.info(
                        f"[INVENTORY] 제목 선택: 2.5차(topic폴백) | "
                        f"id={title.id} | topic_ids={topic_ids_all}")
                    return title

        # 카테고리 설정 블로그인데 일치 제목 없음
        if has_category:
            logger.warning(
                f"[INVENTORY] blog_id={blog_id} | "
                f"카테고리 일치 제목 없음 → None | "
                f"subtopic={subtopic_ids} | topic={topic_only_ids}")
            return None

        # 카테고리 미설정 블로그 → 전체 available 폴백
        title = await self._query_title_with_filters(
            blog_id_str, [], matched_only=False,
            sibling_blog_ids=sibling_ids,
        )
        if not title:
            logger.warning(f"[INVENTORY] 전체폴백 실패 | blog_id={blog_id}")
        return title

    async def _query_title_with_filters(
        self,
        blog_id_str: str,
        category_conditions: list,
        matched_only: bool,
        sibling_blog_ids: Optional[List[int]] = None,
    ) -> Optional[MainTitle]:
        """
        필터 조건 조합으로 후보 제목 조회 후 랜덤 1개 선택

        재고 정책은 블로그별로 산정한다:
        - 이 블로그가 이미 글을 만든 제목은 제외 (중복 방지)
        - 다른 블로그가 사용한 제목(글로벌 status='used')은 후보에 포함
        - status='archived'는 의도적으로 보관된 것이므로 제외

        Args:
            blog_id_str: 블로그 ID 문자열
            category_conditions: 카테고리 OR 조건 리스트
            matched_only: True면 매칭 제목만, False면 카테고리 일치 제목 전체

        Returns:
            MainTitle 또는 None (랜덤 선택)
        """
        # archived만 제외 (used도 다른 블로그 사용 흔적이므로 후보로 허용)
        conditions = [MainTitle.status != "archived"]

        # 이 블로그가 이미 글을 만든 제목은 제외 (블로그별 중복 방지)
        conditions.append(
            MainTitle.id.notin_(
                self._published_title_ids_subquery(blog_id_str, sibling_blog_ids)
            )
        )

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

        if not candidates:
            avail_r = await self.db.execute(
                select(func.count(MainTitle.id)).where(
                    MainTitle.status != "archived"))
            excl_r = await self.db.execute(
                select(func.count()).select_from(
                    self._published_title_ids_subquery(blog_id_str).subquery()))
            logger.info(
                f"[INVENTORY] 제목 후보 0개 | "
                f"blog={blog_id_str} | matched_only={matched_only} | "
                f"category={len(category_conditions)}개 | "
                f"비archived전체={avail_r.scalar() or 0} | "
                f"이블로그사용제외={excl_r.scalar() or 0}")
        else:
            logger.info(
                f"[INVENTORY] 제목 후보 {len(candidates)}개 | "
                f"blog={blog_id_str} | matched_only={matched_only}")

        return random.choice(candidates) if candidates else None
