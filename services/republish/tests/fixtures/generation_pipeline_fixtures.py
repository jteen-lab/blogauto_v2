"""
생성 파이프라인 테스트 픽스처

ContentGenerator, InventoryTrigger, FlowGenerateExecutor 테스트에
필요한 Mock 데이터 팩토리를 정의합니다.
"""
import pytest
from datetime import datetime
from typing import Optional, List
from unittest.mock import MagicMock, AsyncMock
from dataclasses import dataclass, field

from tests.fixtures.reference_collection_fixtures import (
    create_mock_db_session,
    create_document_summaries,
)


# ============================================================
# 모듈 설정 팩토리
# ============================================================

def create_module_settings_all_enabled() -> dict:
    """모든 옵션이 활성화된 모듈 설정"""
    return {
        "enable_title_prompt": True,
        "title_prompt": "원본 제목: {title}\nSEO 최적화해주세요.",
        "enable_reference_collection": True,
        "reference": {
            "enabled": True,
            "max_search": 30,
            "crawl_target": 10,
            "summary_count": 3,
            "summary_method": "ai",
            "ai_provider": "openai",
            "ai_model": "gpt-4o-mini",
        },
        "generation_prompt": (
            "제목: {title}\n\n{reference_materials}\n\n"
            "위 내용을 바탕으로 블로그 글을 작성해주세요."
        ),
        "inventory": {
            "rapid_growth_threshold": 50,
            "rapid_growth_inventory": 10,
            "growth_threshold": 150,
            "growth_inventory": 5,
            "stable_inventory": 2,
        },
        "internal_links": {
            "enabled": True,
            "intro_count": 3,
            "intro_link_type": "button",
            "conclusion_count": 3,
            "conclusion_list_style": "dash",
            "similarity_threshold": 75,
        },
    }


def create_module_settings_no_reference() -> dict:
    """참조자료 비활성화 설정"""
    return {
        "enable_title_prompt": False,
        "enable_reference_collection": False,
        "generation_prompt": (
            "제목: {title}\n\n{reference_materials}\n\n"
            "간단한 블로그 글을 작성해주세요."
        ),
    }


def create_module_settings_minimal() -> dict:
    """최소 설정 (제목 재조합, 참조자료 비활성화)"""
    return {
        "enable_title_prompt": False,
        "enable_reference_collection": False,
        "generation_prompt": "제목: {title}\n\n글을 작성해주세요.",
    }


# ============================================================
# 모델 Mock 팩토리
# ============================================================

def create_mock_blog(
    blog_id: int = 1,
    name: str = "테스트블로그",
    total_post_count: int = 10,
    placeholders: Optional[dict] = None,
    ai_config: Optional[dict] = None,
    growth_setting: Optional[MagicMock] = None,
) -> MagicMock:
    """Mock Blog 생성"""
    blog = MagicMock()
    blog.id = blog_id
    blog.name = name
    blog.url = f"https://{name}.blog.com"
    blog.total_post_count = total_post_count
    blog.placeholders = placeholders or {}
    blog.ai_config = ai_config or {}
    blog.growth_setting = growth_setting
    return blog


def create_mock_main_title(
    title_id: int = 1,
    title: str = "포항 이삿짐센터 추천 가이드",
    status: str = "available",
    matched_blog_ids: Optional[str] = "[1]",
    topic_id: Optional[int] = None,
    subtopic_id: Optional[int] = None,
    keywords: Optional[str] = None,
) -> MagicMock:
    """Mock MainTitle 생성 (mark_used 포함)"""
    mock = MagicMock()
    mock.id = title_id
    mock.title = title
    mock.status = status
    mock.matched_blog_ids = matched_blog_ids
    mock.topic_id = topic_id
    mock.subtopic_id = subtopic_id
    mock.keywords = keywords
    mock.created_at = datetime(2026, 1, 1)

    def _mark_used():
        mock.status = "used"

    mock.mark_used = MagicMock(side_effect=_mark_used)
    return mock


def create_mock_module(
    module_id: int = 1,
    name: str = "테스트 생성 모듈",
    settings: Optional[dict] = None,
) -> MagicMock:
    """Mock Module 생성"""
    module = MagicMock()
    module.id = module_id
    module.name = name
    module.settings = settings or create_module_settings_all_enabled()
    return module


def create_mock_growth_setting(
    rapid_growth_threshold: int = 50,
    rapid_growth_inventory: int = 10,
    growth_threshold: int = 150,
    growth_inventory: int = 5,
    stable_inventory: int = 2,
) -> MagicMock:
    """Mock BlogGrowthSetting 생성"""
    setting = MagicMock()
    setting.rapid_growth_threshold = rapid_growth_threshold
    setting.rapid_growth_inventory = rapid_growth_inventory
    setting.growth_threshold = growth_threshold
    setting.growth_inventory = growth_inventory
    setting.stable_inventory = stable_inventory

    def _get_growth_stage(current_post_count: int) -> str:
        if current_post_count <= rapid_growth_threshold:
            return "rapid_growth"
        elif current_post_count <= growth_threshold:
            return "growth"
        return "stable"

    def _get_inventory_threshold(current_post_count: int) -> int:
        if current_post_count <= rapid_growth_threshold:
            return rapid_growth_inventory
        elif current_post_count <= growth_threshold:
            return growth_inventory
        return stable_inventory

    setting.get_growth_stage = MagicMock(side_effect=_get_growth_stage)
    setting.get_inventory_threshold = MagicMock(
        side_effect=_get_inventory_threshold
    )
    return setting


def create_mock_crawled_post(
    post_id: int = 1,
    blog_id: int = 1,
    title: str = "테스트 포스트",
    url: Optional[str] = "https://blog.com/post/1",
    source: str = "generated",
    published_at: Optional[datetime] = None,
    generation_history_id: Optional[int] = None,
) -> MagicMock:
    """Mock CrawledPost 생성"""
    post = MagicMock()
    post.id = post_id
    post.blog_id = blog_id
    post.title = title
    post.url = url
    post.source = source
    post.match_status = "unmatched"
    post.generation_history_id = generation_history_id
    post.published_at = published_at
    post.created_at = datetime(2026, 1, 1)
    post.updated_at = datetime(2026, 1, 1)

    # 프로퍼티 Mock
    post.is_generated = (source == "generated")
    post.is_published = (published_at is not None)
    post.is_publishable = (source == "generated" and published_at is None)

    def _mark_published(published_url=None):
        post.published_at = datetime.now()
        if published_url:
            post.url = published_url

    post.mark_published = MagicMock(side_effect=_mark_published)
    return post


# ============================================================
# 서비스 결과 팩토리
# ============================================================

def create_mock_recombine_result(
    original: str = "포항 이삿짐센터 추천 가이드",
    recombined: str = "SEO 최적화 포항 이사업체 비교",
    is_modified: bool = True,
    ai_model: str = "gpt-4o-mini",
    ai_provider: str = "openai",
):
    """RecombineResult Mock 생성 (dataclass 직접 생성)"""
    from app.services.generation.title_recombiner import RecombineResult
    return RecombineResult(
        original_title=original,
        recombined_title=recombined,
        ai_model=ai_model,
        ai_provider=ai_provider,
        is_modified=is_modified,
    )


def create_mock_reference_result(
    count: int = 3,
    reference_id: int = 1,
):
    """ReferenceCollectionResult Mock 생성"""
    from app.services.generation.reference_collector import (
        ReferenceCollectionResult,
    )
    summaries = create_document_summaries(count) if count > 0 else []
    sources = [s.url for s in summaries]
    return ReferenceCollectionResult(
        count=count,
        summaries=summaries,
        sources=sources,
        reference_id=reference_id if count > 0 else None,
    )


def create_mock_generation_result(
    success: bool = True,
    title: str = "SEO 최적화 포항 이사업체 비교",
    html: str = "<h2>서론</h2><p>테스트 글</p>",
    reference_count: int = 3,
    error: Optional[str] = None,
):
    """GenerationResult Mock 생성"""
    from app.services.generation.generator import GenerationResult
    return GenerationResult(
        success=success,
        crawling_post_id=1 if success else None,
        generation_history_id=1 if success else None,
        recombined_title=title if success else None,
        final_html=html if success else None,
        reference_count=reference_count,
        generation_time_seconds=5,
        content_length=len(html) if html else 0,
        ai_model_title="gpt-4o-mini",
        ai_model_content="gpt-4o-mini",
        error=error,
    )


def create_mock_inventory_result(
    blog_id: int = 1,
    current_inventory: int = 0,
    threshold: int = 10,
    needs_generation: bool = True,
    growth_stage: str = "rapid_growth",
    title_id: Optional[int] = 1,
    title_text: Optional[str] = "포항 이삿짐센터 추천 가이드",
):
    """InventoryCheckResult Mock 생성"""
    from app.services.generation.inventory_trigger import (
        InventoryCheckResult,
    )
    return InventoryCheckResult(
        blog_id=blog_id,
        current_inventory=current_inventory,
        threshold=threshold,
        needs_generation=needs_generation,
        growth_stage=growth_stage,
        available_title_id=title_id if needs_generation else None,
        available_title_text=title_text if needs_generation else None,
    )


def create_mock_publish_result(
    blog_id: int = 1,
    crawled_post_id: Optional[int] = 1,
    needs_generation: bool = True,
    current_inventory: int = 0,
    threshold: int = 10,
):
    """PublishResult Mock 생성"""
    from app.services.generation.inventory_manager import PublishResult
    inventory_check = create_mock_inventory_result(
        blog_id=blog_id,
        current_inventory=current_inventory,
        threshold=threshold,
        needs_generation=needs_generation,
    )
    return PublishResult(
        blog_id=blog_id,
        crawled_post_id=crawled_post_id,
        published_at=datetime.now(),
        inventory_check=inventory_check,
    )


# ============================================================
# DB Mock 유틸리티
# ============================================================

def create_db_get_side_effect(**model_map):
    """
    모델별 db.get() 응답 매핑

    Args:
        **model_map: 모델클래스명 → {id: mock_instance} 매핑

    사용법:
        mock_db.get = AsyncMock(side_effect=create_db_get_side_effect(
            MainTitle={1: title_mock},
            Blog={1: blog_mock},
            Module={1: module_mock},
        ))
    """
    async def _get(model_class, id_value):
        class_name = model_class.__name__
        instances = model_map.get(class_name, {})
        return instances.get(id_value)
    return _get


def create_auto_id_add(start_id: int = 100):
    """
    db.add() 시 자동 id 할당 Mock

    flush() 호출 전 add된 객체에 id가 없으면 자동 할당합니다.
    """
    counter = [start_id]

    def _add(obj):
        if hasattr(obj, 'id') and obj.id is None:
            counter[0] += 1
            obj.id = counter[0]
    return _add


# ============================================================
# Phase D: 워밍업/발행 Mock 팩토리
# ============================================================

def create_mock_warmup_status(
    is_active: bool = False,
    days_elapsed: int = 0,
    daily_max: int = 3,
    today_published: int = 0,
    can_publish: bool = True,
    effective_interval: Optional[int] = None,
):
    """WarmupStatus Mock 팩토리"""
    from app.services.generation.warmup_manager import WarmupStatus
    return WarmupStatus(
        is_active=is_active,
        days_elapsed=days_elapsed,
        daily_max=daily_max,
        today_published=today_published,
        can_publish=can_publish,
        effective_interval=effective_interval,
    )


def create_mock_fes(
    fes_id: int = 1,
    flow_id: int = 1,
    module_id: int = 1,
    blog_id: Optional[int] = None,
    last_executed_at: Optional[datetime] = None,
    next_execution_at: Optional[datetime] = None,
    is_paused: bool = False,
) -> MagicMock:
    """FlowExecutionState Mock 팩토리"""
    fes = MagicMock()
    fes.id = fes_id
    fes.flow_id = flow_id
    fes.module_id = module_id
    fes.blog_id = blog_id
    fes.last_executed_at = last_executed_at
    fes.next_execution_at = next_execution_at
    fes.is_paused = is_paused
    fes.execution_count = 0
    fes.success_count = 0
    fes.failure_count = 0
    fes.created_at = datetime(2026, 1, 1)
    fes.updated_at = datetime(2026, 1, 1)
    return fes


def create_warmup_settings(
    enabled: bool = True,
    warmup_days: int = 14,
    initial_daily_posts: int = 1,
    max_daily_posts: int = 3,
    ramp_rate: float = 0.5,
) -> dict:
    """warmup 설정 dict 팩토리"""
    return {
        "enabled": enabled,
        "warmup_days": warmup_days,
        "initial_daily_posts": initial_daily_posts,
        "max_daily_posts": max_daily_posts,
        "ramp_rate": ramp_rate,
    }
