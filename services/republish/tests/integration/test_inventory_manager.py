"""
InventoryManager 재고 관리 서비스 통합 테스트

발행 모듈과 생성 모듈 사이의 인터페이스인 InventoryManager를 검증합니다.
FIFO 기반 발행 대상 조회, 발행 완료 처리, 발행 후 재고 확인 콜백,
재고 상태 조회 위임 등 4개 메서드의 정상/예외 시나리오를 테스트합니다.

테스트 대상: app/services/generation/inventory_manager.py
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.generation.inventory_manager import (
    InventoryManager,
    PublishResult,
)
from app.services.generation.inventory_trigger import InventoryCheckResult
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_db_session,
    create_mock_crawled_post,
    create_mock_inventory_result,
    create_module_settings_all_enabled,
)


# ============================================================
# 헬퍼: db.execute → scalar_one_or_none Mock
# ============================================================

def mock_execute_returning(post):
    """db.execute() 결과의 scalar_one_or_none()가 post를 반환하도록 설정"""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=post)

    async def _execute(query, *args, **kwargs):
        return result

    return AsyncMock(side_effect=_execute)


# ============================================================
# TestGetPostForPublish: FIFO 발행 대상 조회
# ============================================================

class TestGetPostForPublish:
    """InventoryManager.get_post_for_publish() 테스트"""

    @pytest.mark.asyncio
    async def test_returns_oldest_unpublished(self, mock_db):
        """미발행 생성글 중 가장 오래된 글을 FIFO로 반환한다"""
        post = create_mock_crawled_post(
            post_id=10, blog_id=1, title="첫 번째 생성글",
            source="generated", published_at=None,
        )
        mock_db.execute = mock_execute_returning(post)

        manager = InventoryManager(mock_db)
        result = await manager.get_post_for_publish(blog_id=1)

        assert result is not None
        assert result.id == 10
        assert result.title == "첫 번째 생성글"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self, mock_db):
        """미발행 생성글이 없으면 None을 반환한다"""
        mock_db.execute = mock_execute_returning(None)

        manager = InventoryManager(mock_db)
        result = await manager.get_post_for_publish(blog_id=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_with_generation_history_id(self, mock_db):
        """generation_history_id를 지정하면 해당 이력의 글만 조회한다"""
        post = create_mock_crawled_post(
            post_id=20, blog_id=1, title="특정 이력 글",
            generation_history_id=5,
        )
        mock_db.execute = mock_execute_returning(post)

        manager = InventoryManager(mock_db)
        result = await manager.get_post_for_publish(
            blog_id=1, generation_history_id=5,
        )

        assert result is not None
        assert result.id == 20
        assert result.generation_history_id == 5


# ============================================================
# TestMarkAsPublished: 발행 완료 처리
# ============================================================

class TestMarkAsPublished:
    """InventoryManager.mark_as_published() 테스트"""

    @pytest.mark.asyncio
    async def test_sets_published_at(self, mock_db):
        """발행 처리 시 published_at이 설정된다"""
        post = create_mock_crawled_post(
            post_id=1, blog_id=1, title="발행 대상 글",
        )
        mock_db.get = AsyncMock(return_value=post)

        manager = InventoryManager(mock_db)
        result = await manager.mark_as_published(crawled_post_id=1)

        post.mark_published.assert_called_once_with(None)
        mock_db.flush.assert_called_once()
        assert result is post

    @pytest.mark.asyncio
    async def test_sets_url_when_provided(self, mock_db):
        """published_url을 전달하면 URL이 업데이트된다"""
        post = create_mock_crawled_post(
            post_id=2, blog_id=1, title="URL 테스트 글",
        )
        mock_db.get = AsyncMock(return_value=post)
        published_url = "https://blog.com/published/2"

        manager = InventoryManager(mock_db)
        await manager.mark_as_published(
            crawled_post_id=2, published_url=published_url,
        )

        post.mark_published.assert_called_once_with(published_url)

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self, mock_db):
        """존재하지 않는 ID를 전달하면 ValueError가 발생한다"""
        mock_db.get = AsyncMock(return_value=None)

        manager = InventoryManager(mock_db)

        with pytest.raises(ValueError, match="CrawledPost를 찾을 수 없습니다"):
            await manager.mark_as_published(crawled_post_id=999)


# ============================================================
# TestOnPublishComplete: 발행 완료 콜백
# ============================================================

class TestOnPublishComplete:
    """InventoryManager.on_publish_complete() 테스트"""

    @pytest.mark.asyncio
    async def test_marks_and_checks_inventory(self, mock_db):
        """crawled_post_id가 있으면 발행 처리 후 재고를 확인한다"""
        post = create_mock_crawled_post(post_id=1, blog_id=1)
        mock_db.get = AsyncMock(return_value=post)

        inventory_result = create_mock_inventory_result(
            blog_id=1, current_inventory=2, threshold=10,
            needs_generation=True,
        )

        manager = InventoryManager(mock_db)
        manager.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result,
        )

        result = await manager.on_publish_complete(
            blog_id=1, crawled_post_id=1,
        )

        assert isinstance(result, PublishResult)
        assert result.blog_id == 1
        assert result.crawled_post_id == 1
        assert result.inventory_check.needs_generation is True
        assert result.inventory_check.current_inventory == 2
        post.mark_published.assert_called_once()

    @pytest.mark.asyncio
    async def test_without_crawled_post_id(self, mock_db):
        """crawled_post_id 없이 호출하면 재고 확인만 수행한다"""
        inventory_result = create_mock_inventory_result(
            blog_id=1, current_inventory=5, threshold=10,
            needs_generation=True,
        )

        manager = InventoryManager(mock_db)
        manager.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result,
        )

        result = await manager.on_publish_complete(blog_id=1)

        assert result.crawled_post_id is None
        assert result.inventory_check.current_inventory == 5
        # mark_as_published는 호출되지 않아야 한다
        mock_db.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_module_settings(self, mock_db):
        """module_settings가 inventory_trigger.check_inventory에 전달된다"""
        inventory_result = create_mock_inventory_result(
            blog_id=1, current_inventory=0, threshold=50,
            needs_generation=True, growth_stage="rapid_growth",
        )
        settings = create_module_settings_all_enabled()

        manager = InventoryManager(mock_db)
        manager.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result,
        )

        result = await manager.on_publish_complete(
            blog_id=1, module_settings=settings,
        )

        manager.inventory_trigger.check_inventory.assert_called_once_with(
            1, module_settings=settings,
        )
        assert result.inventory_check.threshold == 50


# ============================================================
# TestGetInventoryStatus: 재고 상태 조회 위임
# ============================================================

class TestGetInventoryStatus:
    """InventoryManager.get_inventory_status() 테스트"""

    @pytest.mark.asyncio
    async def test_delegates_to_trigger(self, mock_db):
        """InventoryTrigger.check_inventory에 정확히 위임한다"""
        inventory_result = create_mock_inventory_result(
            blog_id=3, current_inventory=7, threshold=10,
            needs_generation=True, growth_stage="growth",
        )
        settings = {"inventory": {"growth_inventory": 10}}

        manager = InventoryManager(mock_db)
        manager.inventory_trigger.check_inventory = AsyncMock(
            return_value=inventory_result,
        )

        result = await manager.get_inventory_status(
            blog_id=3, module_settings=settings,
        )

        assert isinstance(result, InventoryCheckResult)
        assert result.blog_id == 3
        assert result.current_inventory == 7
        assert result.growth_stage == "growth"
        manager.inventory_trigger.check_inventory.assert_called_once_with(
            3, module_settings=settings,
        )
