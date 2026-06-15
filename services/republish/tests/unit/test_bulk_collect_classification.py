"""대량수집 제목 저장의 카테고리 분류·제목 필터 패리티 테스트.

뉴스수집(keyword_collector_service)과 동일하게 ChunkProcessor가
제목 필터링 + 카테고리 자동 분류를 적용하는지 검증한다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.bulk_collect.chunk_processor import ChunkProcessor


def _make_processor() -> ChunkProcessor:
    """외부 의존성을 mock으로 채운 ChunkProcessor."""
    return ChunkProcessor(
        db=MagicMock(),
        domain_limiter=MagicMock(),
        timebox=MagicMock(),
    )


def _filter(value, target="title", ftype="keyword"):
    f = MagicMock()
    f.filter_value = value
    f.target_type = target
    f.filter_type = ftype
    f.increment_match = MagicMock()
    return f


class TestTitleFilter:
    """_match_title_filter (뉴스수집 _check_filter와 동일 규칙)"""

    def test_keyword_filter_matches_title(self):
        p = _make_processor()
        p._title_filters = [_filter("도박")]
        assert p._match_title_filter("온라인 도박 사이트 추천") is True
        p._title_filters[0].increment_match.assert_called_once()

    def test_pass_when_no_match(self):
        p = _make_processor()
        p._title_filters = [_filter("도박")]
        assert p._match_title_filter("경북 이사업체 후기") is False

    def test_keyword_only_target_skipped_for_title(self):
        """target_type=keyword 필터는 제목에 적용되지 않음"""
        p = _make_processor()
        p._title_filters = [_filter("이사", target="keyword")]
        assert p._match_title_filter("경북 이사업체") is False

    def test_both_target_applies(self):
        p = _make_processor()
        p._title_filters = [_filter("스팸", target="both")]
        assert p._match_title_filter("스팸 광고 글") is True

    def test_pattern_filter(self):
        p = _make_processor()
        p._title_filters = [_filter(r"\d{4}년", ftype="pattern")]
        assert p._match_title_filter("2026년 운세 정리") is True


class TestPersistClassification:
    """_persist_temp_titles: 분류값 채움 + 필터 제외"""

    @pytest.mark.asyncio
    async def test_applies_category_and_filter(self, monkeypatch):
        p = _make_processor()
        # 분류기/필터 사전 주입 → _ensure_classifiers의 DB 로드 스킵
        matcher = MagicMock()
        matcher.match_and_apply_to_title = AsyncMock(
            return_value=(7, 70, 700),
        )
        p._category_matcher = matcher
        p._title_filters = [_filter("도박")]

        added = []
        p.db.add = MagicMock(side_effect=lambda obj: added.append(obj))

        import app.services.title_dedup as td
        monkeypatch.setattr(
            td, "title_exists", AsyncMock(return_value=False),
        )

        rows = [
            SimpleNamespace(
                title_fetch_status="done",
                title="경북 이사업체 후기확인",
                domain="a.com", url="https://a.com/1",
            ),
            SimpleNamespace(
                title_fetch_status="done",
                title="온라인 도박 사이트 추천",
                domain="b.com", url="https://b.com/2",
            ),
        ]
        await p._persist_temp_titles(rows)

        # 도박 제목은 필터 제외, 이사 제목만 저장 + 분류값 채워짐
        assert len(added) == 1
        saved = added[0]
        assert saved.topic_id == 7
        assert saved.subtopic_id == 70
        assert saved.matched_keyword_id == 700
        matcher.match_and_apply_to_title.assert_awaited_once()
