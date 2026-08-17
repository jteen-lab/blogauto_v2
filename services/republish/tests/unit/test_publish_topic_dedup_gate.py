"""F8 — 발행 전 근접 중복(주제 중복) 게이트 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.publishing.topic_dedup_gate import (
    _tokenize,
    jaccard_similarity,
    check_topic_duplicate,
    PUBLISH_DEDUP_THRESHOLD,
)


class TestJaccard:
    def test_identical(self):
        a = _tokenize("서울 맛집 추천 베스트 정리")
        assert jaccard_similarity(a, a) == 1.0

    def test_disjoint(self):
        a = _tokenize("서울 맛집 추천")
        b = _tokenize("부동산 세금 계산법")
        assert jaccard_similarity(a, b) == 0.0

    def test_empty_returns_zero(self):
        assert jaccard_similarity(set(), _tokenize("무언가 제목")) == 0.0

    def test_tokenize_drops_short_and_punct(self):
        # 특수문자 제거 + 2자 미만 토큰 제외
        toks = _tokenize("A형 독감, 예방접종 시기!")
        assert "예방접종" in toks and "시기" in toks
        assert "a형" in toks  # 2자라 유지


def _db_returning(titles):
    """(id, title) 행을 반환하는 가짜 db.execute 구성."""
    rows = [(i + 1, t) for i, t in enumerate(titles)]
    result = MagicMock()
    result.all.return_value = rows
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


class TestCheckTopicDuplicate:
    @pytest.mark.asyncio
    async def test_blocks_near_duplicate(self):
        db = _db_returning(["서울 맛집 추천 베스트 정리"])
        # 어순만 다른 사실상 동일 제목 → 차단
        reason = await check_topic_duplicate(db, 1, "베스트 서울 맛집 추천 정리")
        assert reason is not None
        assert "중복 차단" in reason

    @pytest.mark.asyncio
    async def test_passes_distinct_topic(self):
        db = _db_returning(["서울 맛집 추천 베스트 정리"])
        reason = await check_topic_duplicate(db, 1, "부산 여행 코스 3박 4일 일정")
        assert reason is None

    @pytest.mark.asyncio
    async def test_passes_same_topic_different_title(self):
        # 주제(맛집)만 겹치고 실제 내용이 다른 정상 글은 통과(오차단 방지)
        db = _db_returning(["서울 강남 데이트 맛집 코스"])
        reason = await check_topic_duplicate(db, 1, "제주도 흑돼지 맛집 솔직 후기")
        assert reason is None

    @pytest.mark.asyncio
    async def test_excludes_self(self):
        db = _db_returning(["똑같은 제목 그대로"])
        # 비교 대상이 자기 자신(id=1)뿐이면 제외되어 통과
        reason = await check_topic_duplicate(
            db, 1, "똑같은 제목 그대로", exclude_post_id=1
        )
        assert reason is None

    @pytest.mark.asyncio
    async def test_empty_title_passes(self):
        db = _db_returning(["아무 제목"])
        assert await check_topic_duplicate(db, 1, "") is None

    def test_threshold_is_conservative(self):
        # 보수 임계값(정확일치 dedup 보완용): 0.8 이상
        assert PUBLISH_DEDUP_THRESHOLD >= 0.8
