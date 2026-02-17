"""
InventoryTrigger 재고 확인 로직 통합 테스트

블로그의 CrawledPost 재고 수준을 확인하고,
모듈 설정 또는 BlogGrowthSetting 임계값과 비교하여
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
            - ("scalar_one_or_none", value): result.scalar_one_or_none() 반환
            - ("scalars_all", value): result.scalars().all() 반환
    """
    call_count = [0]

    async def _mock_execute(query, *args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1

        if idx >= len(responses):
            result = MagicMock()
            result.scalar = MagicMock(return_value=None)
            result.scalar_one_or_none = MagicMock(return_value=None)
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars_mock)
            return result

        method, value = responses[idx]
        result = MagicMock()

        if method == "scalar":
            result.scalar = MagicMock(return_value=value)
        elif method == "scalar_one_or_none":
            result.scalar_one_or_none = MagicMock(return_value=value)
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
    async def test_rapid_growth_needs_generation(
        self, mock_db, sample_blog, sample_title,
    ):
        """급성장기 블로그에서 재고 0일 때 생성이 필요하다고 판단"""
        # 모듈 설정: inventory 포함
        settings = create_module_settings_all_enabled()

        # db.execute 호출 순서:
        # 1) _get_inventory_count → scalar=0
        # 2) _get_threshold → Blog 조회 (post_count=10, rapid_growth)
        # 3) _find_available_title 1차 → 매칭 제목 있음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", sample_blog),
            ("scalar_one_or_none", sample_title),
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        assert result.needs_generation is True
        assert result.growth_stage == "rapid_growth"
        assert result.threshold == 10
        assert result.current_inventory == 0
        assert result.available_title_id == sample_title.id

    @pytest.mark.asyncio
    async def test_sufficient_inventory_skips(self, mock_db):
        """재고가 충분하면 생성을 건너뛴다"""
        blog = create_mock_blog(blog_id=1, total_post_count=10)
        settings = create_module_settings_all_enabled()

        # 재고 5 >= 임계값(rapid_growth_inventory=10)은 아님
        # 재고 10 >= 10이면 건너뜀
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 10),           # 재고 10개
            ("scalar_one_or_none", blog),  # Blog (급성장기: threshold=10)
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        assert result.needs_generation is False
        assert result.current_inventory == 10
        assert result.threshold == 10
        assert result.available_title_id is None

    @pytest.mark.asyncio
    async def test_growth_stage_threshold_5(self, mock_db):
        """성장기 블로그(80글)는 임계값 5, 단계 growth"""
        blog = create_mock_blog(blog_id=2, total_post_count=80)
        title = create_mock_main_title(title_id=5, title="성장기 제목")
        settings = create_module_settings_all_enabled()

        # post_count=80 > rapid_growth_threshold(50), <= growth_threshold(150)
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", blog),
            ("scalar_one_or_none", title),
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=2, module_settings=settings,
        )

        assert result.threshold == 5
        assert result.growth_stage == "growth"
        assert result.needs_generation is True

    @pytest.mark.asyncio
    async def test_module_settings_override(self, mock_db):
        """모듈 inventory 설정이 BlogGrowthSetting보다 우선 적용된다"""
        # BlogGrowthSetting이 있는 블로그
        growth_setting = create_mock_growth_setting(
            rapid_growth_inventory=20,
        )
        blog = create_mock_blog(
            blog_id=1, total_post_count=10,
            growth_setting=growth_setting,
        )
        title = create_mock_main_title(title_id=1)

        # 모듈 설정의 rapid_growth_inventory=10이 우선
        settings = create_module_settings_all_enabled()

        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", blog),
            ("scalar_one_or_none", title),
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        # BlogGrowthSetting의 20이 아닌 모듈 설정의 10이 적용
        assert result.threshold == 10
        assert result.growth_stage == "rapid_growth"

    @pytest.mark.asyncio
    async def test_no_growth_setting_default(self, mock_db):
        """BlogGrowthSetting이 없으면 기본값 3을 사용한다"""
        blog = create_mock_blog(
            blog_id=1, total_post_count=10,
            growth_setting=None,
        )
        title = create_mock_main_title(title_id=1)

        # module_settings에 inventory 없음 -> BlogGrowthSetting 폴백
        settings_no_inventory = {
            "generation_prompt": "제목: {title}\n글 작성",
        }

        # db.execute 호출 순서 (inventory 없는 경우):
        # 1) _get_inventory_count → scalar=0
        # 2) _get_threshold → Blog+selectinload 조회 (growth_setting=None)
        # 3) _find_available_title 1차 → 매칭 제목 있음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", blog),
            ("scalar_one_or_none", title),
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings_no_inventory,
        )

        assert result.threshold == DEFAULT_INVENTORY_THRESHOLD
        assert result.growth_stage == "default"
        assert result.needs_generation is True

    @pytest.mark.asyncio
    async def test_no_available_title_skips(self, mock_db, sample_blog):
        """재고 부족이지만 사용 가능한 제목이 없으면 생성을 건너뛴다"""
        settings = create_module_settings_all_enabled()

        # _find_available_title에서 1차, 2차 모두 None
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", sample_blog),
            ("scalar_one_or_none", None),  # 1차 매칭 제목 없음
            ("scalar_one_or_none", None),  # 2차 폴백도 없음
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        assert result.needs_generation is False
        assert result.available_title_id is None
        assert result.available_title_text is None

    @pytest.mark.asyncio
    async def test_matched_title_priority(self, mock_db, sample_blog):
        """매칭된 제목이 폴백 제목보다 우선 선택된다"""
        settings = create_module_settings_all_enabled()
        matched = create_mock_main_title(
            title_id=10,
            title="매칭된 제목",
            matched_blog_ids="[1]",
        )

        # 1차 매칭에서 바로 찾으므로 2차 폴백 호출 없음
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", sample_blog),
            ("scalar_one_or_none", matched),
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=1, module_settings=settings,
        )

        assert result.available_title_id == matched.id
        assert result.available_title_text == "매칭된 제목"

    @pytest.mark.asyncio
    async def test_blog_not_found(self, mock_db):
        """블로그를 찾을 수 없으면 기본 임계값과 unknown 단계를 반환"""
        settings = create_module_settings_all_enabled()

        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalar", 0),
            ("scalar_one_or_none", None),  # Blog 없음
        ]))

        trigger = InventoryTrigger(mock_db)
        result = await trigger.check_inventory(
            blog_id=999, module_settings=settings,
        )

        assert result.threshold == DEFAULT_INVENTORY_THRESHOLD
        assert result.growth_stage == "unknown"
        # 재고 0 < 3 이므로 생성 필요하지만 제목 없어서 False
        # blog_not_found 시 _get_threshold에서 바로 return하므로
        # needs_generation = (0 < 3) = True -> _find_available_title 호출
        # 하지만 execute 응답이 더 없으므로 None -> False로 다운그레이드
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

        # find_available_titles(blog_id=1, limit=5):
        # 1차 조회: 매칭된 제목 2개 (limit=5이므로 부족 -> 폴백 조회)
        # 2차 조회: 폴백 제목 1개
        mock_db.execute = AsyncMock(side_effect=build_execute_side_effect([
            ("scalars_all", [matched_1, matched_2]),
            ("scalars_all", [fallback]),
        ]))

        trigger = InventoryTrigger(mock_db)
        titles = await trigger.find_available_titles(blog_id=1, limit=5)

        assert len(titles) == 3
        assert titles[0].id == matched_1.id
        assert titles[1].id == matched_2.id
        assert titles[2].id == fallback.id
