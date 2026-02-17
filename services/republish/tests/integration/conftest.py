"""
통합 테스트 공통 fixtures

ContentGenerator, InventoryTrigger, FlowGenerateExecutor
통합 테스트에서 사용되는 공통 pytest fixtures를 정의합니다.
"""
import pytest
from unittest.mock import AsyncMock

from tests.fixtures.reference_collection_fixtures import (
    create_mock_db_session,
)
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_blog,
    create_mock_main_title,
    create_mock_module,
    create_mock_growth_setting,
    create_module_settings_all_enabled,
    create_module_settings_no_reference,
)


@pytest.fixture
def mock_db():
    """공통 Mock DB 세션"""
    return create_mock_db_session()


@pytest.fixture
def sample_blog():
    """표준 테스트 블로그 (급성장기, 글 10개)"""
    return create_mock_blog(
        blog_id=1, name="테스트블로그", total_post_count=10
    )


@pytest.fixture
def growth_blog():
    """성장기 블로그 (글 80개)"""
    return create_mock_blog(
        blog_id=2, name="성장기블로그", total_post_count=80,
        growth_setting=create_mock_growth_setting(),
    )


@pytest.fixture
def sample_title():
    """사용 가능한 테스트 제목"""
    return create_mock_main_title(
        title_id=1,
        title="포항 이삿짐센터 추천 가이드",
        status="available",
        matched_blog_ids="[1]",
    )


@pytest.fixture
def prompt_module():
    """모든 옵션 활성화된 프롬프트 모듈"""
    return create_mock_module(
        module_id=1,
        name="테스트 생성 모듈",
        settings=create_module_settings_all_enabled(),
    )


@pytest.fixture
def minimal_module():
    """최소 설정 프롬프트 모듈 (참조자료/제목재조합 비활성화)"""
    return create_mock_module(
        module_id=2,
        name="최소 모듈",
        settings=create_module_settings_no_reference(),
    )
