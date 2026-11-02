"""꺼내 쓸 수 있는 제목 수 세기 (믹스인).

`inventory_trigger.py` 가 500줄에 닿아(2026-11-02 A1 title_pick 추가) 세는 쪽만 떼어냈다.
세는 기준과 꺼내는 기준은 같아야 한다 — 그래서 같은 조건 함수를 쓴다.

순서도: docs/flowcharts/approved4_a1_volume.md
"""
import logging
from typing import Optional

from sqlalchemy import func, select

from ...models.title import MainTitle
from . import title_pick_order as pick
from .title_scope import blog_cpa_scope, title_condition

logger = logging.getLogger(__name__)


class InventoryCountMixin:
    """재고 제목 수 세기. InventoryCategoryMixin 과 함께 쓴다."""

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
        # 꺼내는 기준과 같아야 한다. 다르면 못 꺼낼 제목을 재고로 세어
        # "재고 충분" 으로 판단하고 생성이 굶는다(키워드 관리 검토서 D-5).
        owned, subs = await blog_cpa_scope(self.db, blog_id)
        conditions.append(title_condition(category_conditions, owned, subs))
        conditions.extend(pick.conditions(pick.pick_opts(module_settings)))

        count = (await self.db.execute(
            select(func.count(MainTitle.id)).where(*conditions)
        )).scalar() or 0
        logger.debug(
            f"[INVENTORY] 사용 가능 제목 {count}개 | blog_id={blog_id} | "
            f"소스={source}"
        )
        return count
