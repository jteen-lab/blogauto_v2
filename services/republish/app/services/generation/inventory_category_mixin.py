"""재고 조회용 카테고리·제외 조건 해석 (믹스인).

`inventory_trigger.py` 가 500줄을 넘어 조건 해석부만 떼어냈다. 판정 규칙은
그대로이며, 재고를 **세는 쪽**과 **꺼내는 쪽**이 같은 조건을 쓰도록
한 곳에 모아 두는 것이 목적이다(키워드 관리 검토서 D-5).

설계 문서: docs/plans/keyword_module_redesign_plan.md
"""
import logging
from typing import List, Optional, Set, Tuple

from sqlalchemy import func, or_, select

from ...models.category import BlogCategory
from ...models.crawled_post import CrawledPost
from ...models.title import MainTitle
from .adsense_niche import resolve_module_niche

logger = logging.getLogger(__name__)


class InventoryCategoryMixin:
    """블로그/모듈 설정에서 재고 조회 조건을 만든다."""

    @staticmethod
    def _published_title_ids_subquery(
        blog_id_str: Optional[str] = None,
        sibling_blog_ids: Optional[list] = None,
    ):
        """
        이미 사용된 생성 CrawledPost와 연결된 MainTitle ID 서브쿼리.

        source="generated"인 CrawledPost와 연결된 MainTitle을 제외하여
        동일 제목으로 중복 글이 생성되지 않도록 한다.

        Args:
            blog_id_str: 명시하면 **이 블로그가 생성한 글의 MainTitle만** 제외.
                         재고 정책은 블로그별이므로 다른 블로그가 사용했다고
                         이 블로그의 생성 후보에서 빼지 않는다.
                         None이면 전 블로그 통합 (하위 호환).
            sibling_blog_ids: 같은 도메인·같은 모듈에 묶인 형제 블로그 ID.
                         지정하면 그 블로그들이 쓴 제목도 함께 제외한다
                         (계획서 N2 조건부 중복 정책). 비우면 기존 동작.

        Note:
            기존에는 published_at IS NOT NULL 조건이 있어 발행 완료된 것만
            제외했지만, 미발행이라도 이미 글이 만들어진 제목은 같은 블로그에서
            재생성할 필요가 없으므로 published_at 조건은 제거한다.
            source="crawled"는 그대로 제외(유사도 매칭 결과에 의한 가짜 매칭 방지).

        Returns:
            제외 대상 MainTitle ID의 서브쿼리.
        """
        query = (
            select(CrawledPost.matched_main_title_id)
            .where(
                CrawledPost.matched_main_title_id.isnot(None),
                CrawledPost.source == "generated",
            )
        )
        if blog_id_str is not None:
            ids = []
            try:
                ids.append(int(blog_id_str))
            except (TypeError, ValueError):
                pass
            # 형제 블로그(같은 도메인·같은 모듈)가 쓴 제목도 제외 — N2 조건부 정책
            for sid in (sibling_blog_ids or []):
                try:
                    ids.append(int(sid))
                except (TypeError, ValueError):
                    continue
            if ids:
                query = query.where(CrawledPost.blog_id.in_(set(ids)))
        return query

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

    @staticmethod
    def _extract_all_topic_ids(
        module_settings: Optional[dict],
    ) -> Set[int]:
        """
        카테고리 설정에서 topic_id를 모두 추출 (subtopic 유무 무관)

        subtopic 레벨 필터 실패 시 topic 레벨 폴백용입니다.
        """
        topic_ids: Set[int] = set()
        for cat in (module_settings or {}).get("categories", []):
            if cat.get("topic_id"):
                topic_ids.add(cat["topic_id"])
        return topic_ids

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

    async def _publishable_inventory(self, blog_id: int) -> Tuple[int, int]:
        """(발행 가능한 재고 수, 전체 재고 수).

        **세는 쪽과 꺼내는 쪽이 어긋나면 교착이 난다.** 재고는 전체로 세면서
        발행은 카테고리로 거르면, 카테고리 밖 글이 재고 자리를 차지한 채
        생성은 "재고 충분" 으로 건너뛰고 발행은 "발행할 글 없음" 으로 생성을
        기다린다. **둘 다 영원히 움직이지 않는다.**

        실측(수작남): 재고 3건이 전부 블로그 카테고리 밖 하위주제
        (문화 정보 2 · 월급 관리 1)라 8/31 발행을 끝으로 열흘간 생성도
        발행도 멈췄다.

        조건은 `InventoryManager.get_post_for_publish()` 와 같다 —
        카테고리가 없거나 매칭 정보가 없는 글은 그대로 후보로 둔다.

        Args:
            blog_id: 블로그 ID

        Returns:
            (발행 가능 수, 전체 수). 카테고리 미설정이면 두 값이 같다.
        """
        base = [
            CrawledPost.blog_id == blog_id,
            CrawledPost.source == "generated",
            CrawledPost.published_at.is_(None),
        ]
        total = (await self.db.execute(
            select(func.count(CrawledPost.id)).where(*base)
        )).scalar() or 0

        subtopic_ids, topic_only_ids = \
            await self._get_blog_category_filter_ids(blog_id)
        cat_conds = []
        if subtopic_ids:
            cat_conds.append(MainTitle.subtopic_id.in_(list(subtopic_ids)))
        if topic_only_ids:
            cat_conds.append(MainTitle.topic_id.in_(list(topic_only_ids)))
        if not cat_conds:
            # 카테고리를 안 정한 블로그는 전부 발행 대상이다.
            # 여기서 0 을 돌려주면 무한 생성이 된다.
            return total, total

        allowed = select(MainTitle.id).where(or_(*cat_conds))
        publishable = (await self.db.execute(
            select(func.count(CrawledPost.id)).where(
                *base,
                or_(
                    CrawledPost.matched_main_title_id.is_(None),
                    CrawledPost.matched_main_title_id.in_(allowed),
                ),
            )
        )).scalar() or 0
        return publishable, total

    async def _resolve_siblings(
        self, blog_id: int, module_settings: Optional[dict],
    ) -> List[int]:
        """형제 블로그 ID 목록.

        같은 도메인·같은 모듈에 붙은 블로그가 이미 쓴 제목을 후보에서 뺀다
        (계획서 N2). 한 소유자의 여러 사이트가 같은 주제를 다루면 검색엔진이
        대량 생산으로 읽는다 — doooit082 계열 4개에 105종 제목이 중복
        게재됐다.

        2026-08-30: **DB 조회를 여기서 하지 않는다.** 호출자가 미리 계산해
        `_sibling_ids` 로 넘긴다. 재고 조회 한복판에서 블로그를 다시 읽으면
        책임이 섞이고, 쿼리 순서에 의존하는 코드가 생긴다.
        명시적으로 false 를 넣은 경우에만 끈다.
        """
        settings = module_settings or {}
        if settings.get("exclude_sibling_titles") is False:
            return []

        ids = settings.get("_sibling_ids")
        if not isinstance(ids, (list, tuple, set)):
            return []
        return sorted({i for i in ids if isinstance(i, int) and i != blog_id})

    def _apply_niche(self, module_settings, subtopic_ids, topic_only_ids, source):
        """니치 강제 활성 시 카테고리 필터를 니치 topic으로 대체(모듈 단위).

        프롬프트 모듈 settings의 ``niche_enabled``+``niche_topic_ids`` 기준.
        이탈 주제 제목은 애초에 선택되지 않아 재시도 루프도 방지된다.
        Returns: (subtopic_ids, topic_only_ids, category_source)
        """
        niche_ids = resolve_module_niche(module_settings)
        if not niche_ids:
            return subtopic_ids, topic_only_ids, source
        logger.info("[INVENTORY] F4 니치 강제(모듈) | topic_ids=%s", niche_ids)
        return set(), set(niche_ids), "adsense_niche"
