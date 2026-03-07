"""
InventoryTrigger 재고 확인 로직 통합 테스트

블로그의 CrawledPost 재고 수준을 확인하고,
GP(min_inventory) 또는 기본 임계값과 비교하여
생성 필요 여부를 판단하는 로직을 검증합니다.

테스트 대상: app/services/generation/inventory_trigger.py
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.services.generation.inventory_trigger import (
    InventoryTrigger,
    InventoryCheckResult,
    DEFAULT_INVENTORY_THRESHOLD,
)
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_db_session,
    create_mock_blog,
    create_mock_main_title,
    create_mock_growth_setting,
    create_module_settings_all_enabled,
)


# ============================================================
# 헬퍼: db.execute 호출 순서 기반 Mock 빌더
# ============================================================

def build_execute_side_effect(responses: list):
    """
    db.execute() 호출 순서에 따라 다른 결과를 반환하는 side_effect 생성

    Args:
        responses: 각 호출에 대한 (method, value) 튜플 리스트
            - ("scalar", value): result.scalar() 반환
            - ("scalars_all", value): result.scalars().all() 반환
    """
    call_count = [0]

    async def _mock_execute(query, *args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1

        if idx >= len(responses):
            result = MagicMock()
            result.scalar = MagicMock(return_value=None)
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars_mock)
            return result

        method, value = responses[idx]
        result = MagicMock()

        if method == "scalar":
            result.scalar = MagicMock(return_value=value)
        elif method == "scalars_all":
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=value)
            result.scalars = MagicMock(return_value=scalars_mock)

        return result

    return _mock_execute


# ============================================================
# TestInventoryCheck: check_inventory() 핵심 로직 테스트
# ============================================================

class TestInventoryCheck:
    """InventoryTrigger.check_inventory() 통합 테스트"""

    @pytest.mark.asyncio
    async def test_gp_managed_needs_generation(
        self, mock_db, sample_title,
    ):
        """GP가 min_inventory=10 제공 시 재고 0이면 생성 필요"""
        settings = create_module_settings_all_enabled()

        # db.execute 호출 순서 (module_settings에 categories 없음):
        # 1) _get_inventory_count → scalar=0
        # 2) _get_blog_category_filter_ids → BlogCategory 없음
        # 3) _query_title_with_filters(matched_only=True) → 매칭 제목 있음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),            # BlogCategory 없음
            ("scalars_all", [sample_title]),  # 1차 매칭 제목
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, min_inventory=10, module_settings=settings,
        )

        assert result.needs_generation is True
        assert result.growth_stage == "gp_managed"
        assert result.threshold == 10
        assert result.current_inventory == 0
        assert result.available_title_id == sample_title.id

    @pytest.mark.asyncio
    async def test_sufficient_inventory_skips(self, mock_db):
        """재고가 충분하면 생성을 건너뛴다"""
        settings = create_module_settings_all_enabled()

        # 재고 10 >= min_inventory 10 → 건너뜀 (제목 조회 없음)
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 10),  # 재고 10개 (충분)
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, min_inventory=10, module_settings=settings,
        )

        assert result.needs_generation is False
        assert result.current_inventory == 10
        assert result.threshold == 10
        assert result.available_title_id is None

    @pytest.mark.asyncio
    async def test_gp_custom_threshold(self, mock_db):
        """GP가 min_inventory=5를 제공하면 해당 값이 임계값으로 사용"""
        title = create_mock_main_title(title_id=5, title="성장기 제목")
        settings = create_module_settings_all_enabled()

        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),       # BlogCategory 없음
            ("scalars_all", [title]),  # 1차 매칭 제목
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=2, min_inventory=5, module_settings=settings,
        )

        assert result.threshold == 5
        assert result.growth_stage == "gp_managed"
        assert result.needs_generation is True

    @pytest.mark.asyncio
    async def test_module_categories_filter(self, mock_db):
        """module_settings.categories가 있으면 BlogCategory 조회 없이 필터링"""
        title = create_mock_main_title(title_id=1)
        settings = create_module_settings_all_enabled()
        settings["categories"] = [
            {"topic_id": 1, "subtopic_id": 3},
            {"topic_id": 2},
        ]

        # categories가 있으므로 BlogCategory 조회 스킵
        # db.execute 호출 순서:
        # 1) _get_inventory_count → scalar=0
        # 2) _query_title_with_filters(matched_only=True) → 매칭 제목
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", [title]),  # 1차 매칭+카테고리 제목
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, min_inventory=10, module_settings=settings,
        )

        assert result.threshold == 10
        assert result.growth_stage == "gp_managed"
        assert result.available_title_id == title.id

    @pytest.mark.asyncio
    async def test_no_min_inventory_uses_default(self, mock_db):
        """min_inventory 미전달 시 DEFAULT_INVENTORY_THRESHOLD(3) 사용"""
        title = create_mock_main_title(title_id=1)
        settings = {"generation_prompt": "제목: {title}\n글 작성"}

        # min_inventory 미전달, categories도 없음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),       # BlogCategory 없음
            ("scalars_all", [title]),  # 1차 매칭 제목
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        assert result.threshold == DEFAULT_INVENTORY_THRESHOLD
        assert result.growth_stage == "default"
        assert result.needs_generation is True

    @pytest.mark.asyncio
    async def test_no_available_title_skips(self, mock_db):
        """재고 부족이지만 사용 가능한 제목이 없으면 생성을 건너뛴다"""
        settings = create_module_settings_all_enabled()

        # BlogCategory 없음 → 카테고리 미설정 → 3회 title 조회 모두 빈 결과
        # 1차: matched_only=True, 2차: matched_only=False, 3차: 전체 폴백
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),  # BlogCategory 없음
            ("scalars_all", []),  # 1차 매칭: 없음
            ("scalars_all", []),  # 2차 폴백: 없음
            ("scalars_all", []),  # 3차 전체 폴백: 없음
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, min_inventory=10, module_settings=settings,
        )

        assert result.needs_generation is False
        assert result.available_title_id is None
        assert result.available_title_text is None

    @pytest.mark.asyncio
    async def test_matched_title_priority(self, mock_db):
        """매칭된 제목이 1차에서 바로 선택된다"""
        settings = create_module_settings_all_enabled()
        matched = create_mock_main_title(
            title_id=10,
            title="매칭된 제목",
            matched_blog_ids="[1]",
        )

        # 1차 매칭에서 바로 찾으므로 2차 폴백 호출 없음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),         # BlogCategory 없음
            ("scalars_all", [matched]),  # 1차 매칭: 있음
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, min_inventory=10, module_settings=settings,
        )

        assert result.available_title_id == matched.id
        assert result.available_title_text == "매칭된 제목"

    @pytest.mark.asyncio
    async def test_default_threshold_no_title(self, mock_db):
        """min_inventory 없고 제목도 없으면 기본 임계값 + 생성 불가"""
        settings = create_module_settings_all_enabled()

        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalars_all", []),  # BlogCategory 없음
            ("scalars_all", []),  # 1차 매칭: 없음
            ("scalars_all", []),  # 2차 폴백: 없음
            ("scalars_all", []),  # 3차 전체 폴백: 없음
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=999, module_settings=settings,
        )

        assert result.threshold == DEFAULT_INVENTORY_THRESHOLD
        assert result.growth_stage == "default"
        # 재고 0 < 3이므로 생성 필요하지만 제목 없어서 False로 다운그레이드
        assert result.needs_generation is False


# ============================================================
# TestFindAvailableTitles: find_available_titles() 테스트
# ============================================================

class TestFindAvailableTitles:
    """InventoryTrigger.find_available_titles() 통합 테스트"""

    @pytest.mark.asyncio
    async def test_find_matched_and_fallback(self, mock_db):
        """매칭 제목 2개 + 폴백 제목 1개 = 총 3개 반환"""
        matched_1 = create_mock_main_title(
            title_id=1, title="매칭 제목 1", matched_blog_ids="[1]",
        )
        matched_2 = create_mock_main_title(
            title_id=2, title="매칭 제목 2", matched_blog_ids="[1, 3]",
        )
        fallback = create_mock_main_title(
            title_id=3, title="폴백 제목", matched_blog_ids=None,
        )

        # find_available_titles(blog_id=1, limit=5, module_settings=None):
        # module_settings 없음 -> _get_blog_category_filter_ids() 호출
        # 1) BlogCategory 조회 -> 빈 결과 (카테고리 미설정)
        # 2) _query_titles_list(매칭) -> 매칭 2개 (부족 -> 보충 조회)
        # 3) _query_titles_list(보충) -> 폴백 1개
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalars_all", []),                    # BlogCategory 조회 (없음)
            ("scalars_all", [matched_1, matched_2]),  # 1차 매칭 제목
            ("scalars_all", [fallback]),               # 2차 보충 제목
        ]))

        trigger = InventoryTrigger(mock_db)
        titles = await trigger.find_available_titles(blog_id=1, limit=5)

        assert len(titles) == 3
        assert titles[0].id == matched_1.id
        assert titles[1].id == matched_2.id
        assert titles[2].id == fallback.id
