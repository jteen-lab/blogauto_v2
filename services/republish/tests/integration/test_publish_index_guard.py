"""
MATCH-040 E: 발행 시 인덱스(matched_main_title_id) 누락 방지 회귀 테스트

ContentGenerator 가 글 생성 시점에 (정식제목 ↔ 발행글) 짝꿍 ID 를
matched_main_title_id 로 부여한다. 발행 처리 (mark_published) 가 이 짝꿍
정보를 실수로 지우지 않는지 보호한다.

이 가드가 깨지면:
    - 발행 후 발행글이 다음 auto_match 에서 pending 으로 재분류됨
    - 30 초 매칭이 다시 발생함 (BlogMainTitleScan 사전체크가 무의미해짐)
    - 사용자 체감 = "또 매번 느려진다"
"""
from datetime import datetime

import pytest

from app.models.crawled_post import CrawledPost


@pytest.fixture
def matched_post() -> CrawledPost:
    """매칭 인덱스가 부여된 발행글 카드."""
    post = CrawledPost(
        blog_id=1,
        title="테스트 발행글",
        url="https://example.com/p/1",
        source="generated",
        match_status="matched",
        matched_main_title_id=47,
        match_score=92.5,
        publish_attempts=0,
    )
    return post


def test_mark_published_preserves_matched_main_title_id(matched_post):
    """발행 완료 처리는 matched_main_title_id 를 절대 건드리지 않아야 한다."""
    original_id = matched_post.matched_main_title_id

    matched_post.mark_published(
        published_url="https://blog.example.com/posts/42",
        platform_post_id="42",
    )

    assert matched_post.matched_main_title_id == original_id, (
        "mark_published 가 matched_main_title_id 를 변경했습니다. "
        "이 회귀가 들어가면 발행 직후 발행글이 다시 pending 으로 잡혀 "
        "auto_match 30초 폭탄이 재발합니다. CrawledPost.mark_published "
        "구현을 확인하세요."
    )


def test_mark_published_preserves_match_status(matched_post):
    """발행 완료 처리는 match_status 를 'matched' 그대로 둬야 한다."""
    matched_post.mark_published()
    assert matched_post.match_status == "matched", (
        "mark_published 가 match_status 를 변경했습니다."
    )


def test_mark_published_preserves_match_score(matched_post):
    """발행 완료 처리는 match_score 를 그대로 둬야 한다."""
    original_score = matched_post.match_score
    matched_post.mark_published()
    assert matched_post.match_score == original_score


def test_mark_published_sets_published_at_only(matched_post):
    """mark_published 가 실제로 published_at 을 설정하는지(본 동작 검증)."""
    assert matched_post.published_at is None
    matched_post.mark_published(published_url="https://x/y")
    assert matched_post.published_at is not None
    assert matched_post.url == "https://x/y"


def test_record_publish_failure_does_not_touch_matched_main_title_id(
    matched_post,
):
    """발행 실패 기록도 매칭 인덱스를 건드리지 않아야 한다."""
    original_id = matched_post.matched_main_title_id
    matched_post.record_publish_failure("timeout")
    assert matched_post.matched_main_title_id == original_id
    assert matched_post.match_status == "matched"
