"""제목 파이프라인 재설계 회귀 테스트.

배경(운영 실측 2026-09-02):
    collected_urls 126,671건 중 98.9%는 제목까지 수집돼 있었지만
    is_processed 는 0.02%. temp_titles 105,004건의 정식 통과율은 2%.
    수집이 부족한 게 아니라 **과잉이고 관문이 뒤에 있었다**.

바꾼 것:
    1. 경쟁 제목을 재고가 아니라 각도 신호로만 쓴다
    2. 소재를 제목이 아니라 질문에서 뽑는다(질문 팬아웃)
    3. URL 12만 건을 도메인 자산 287개로 요약한다

계획서: docs/plans/title_pipeline_redesign_plan.md
"""
from pathlib import Path

import pytest

from app.services.keyword_lab.sources import questions
from app.services.keyword_lab.sources.base import (
    ALL_SOURCES, SOURCE_LABEL, SRC_QUESTION_FANOUT,
)
from app.services.title_gen import angles
from app.services.title_gen.niche import host_of, in_niche

BASE = Path(__file__).resolve().parents[2]


class TestNicheHost:
    @pytest.mark.parametrize("link,expected", [
        ("https://www.a.tistory.com/1", "a.tistory.com"),
        ("https://a.tistory.com/1", "a.tistory.com"),
        ("https://blog.naver.com/who/123", "blog.naver.com"),
        (None, ""),
        ("", ""),
        ("not a url", ""),
    ])
    def test_host_of(self, link, expected):
        assert host_of(link) == expected

    def test_empty_niche_passes_everything(self):
        """목록이 비면 판정하지 않는다 — 초기에 각도가 사라지면 안 된다."""
        assert in_niche("https://anything.com/1", set()) is True

    def test_matches_exact(self):
        assert in_niche("https://a.tistory.com/1", {"a.tistory.com"})

    def test_rejects_other_domain(self):
        assert not in_niche("https://b.com/1", {"a.tistory.com"})

    def test_subdomain_is_matched(self):
        assert in_niche("https://sub.a.com/1", {"a.com"})

    def test_missing_link_is_not_niche(self):
        assert not in_niche(None, {"a.com"})


class TestAnglesPrioritise:
    """니치 도메인은 **앞으로 당긴다**. 배제하지 않는다."""

    class _Search:
        def __init__(self, items):
            self.items = items

        async def search_blog(self, keyword, display=10):
            return {"success": True, "items": self.items}

    @pytest.mark.asyncio
    async def test_niche_first_others_kept(self):
        search = self._Search([
            {"title": "그 밖 블로그 제목입니다", "link": "https://z.com/1"},
            {"title": "니치 블로그 제목입니다", "link": "https://a.tistory.com/1"},
        ])
        out = await angles.fetch(search, "전기기사", niche={"a.tistory.com"})
        assert out[0].startswith("니치"), out
        assert len(out) == 2, "그 밖 도메인을 버리면 새 경쟁자를 놓친다"

    @pytest.mark.asyncio
    async def test_no_niche_keeps_order(self):
        search = self._Search([
            {"title": "첫 번째 제목입니다", "link": "https://z.com/1"},
            {"title": "두 번째 제목입니다", "link": "https://a.com/1"},
        ])
        out = await angles.fetch(search, "전기기사")
        assert out == ["첫 번째 제목입니다", "두 번째 제목입니다"]

    @pytest.mark.asyncio
    async def test_failure_is_empty(self):
        class Boom:
            async def search_blog(self, *a, **k):
                raise RuntimeError("차단")

        assert await angles.fetch(Boom(), "전기기사") == []


class TestQuestionFanout:
    def test_source_registered(self):
        assert SRC_QUESTION_FANOUT in ALL_SOURCES
        assert SOURCE_LABEL[SRC_QUESTION_FANOUT]

    @pytest.mark.parametrize("text,ok", [
        ("전기기사 실기 왜 어려운가", True),
        ("전기기사 실기 어떻게 준비", True),
        ("전기기사 실기 준비", False),      # 의문사 없음
        ("전기기사 실기", False),            # 시드 그대로
        ("왜", False),                       # 너무 짧음
        ("", False),
    ])
    def test_is_question(self, text, ok):
        assert questions.is_question(text, "전기기사 실기") is ok

    @pytest.mark.asyncio
    async def test_fan_out_dedupes_and_caps(self, monkeypatch):
        async def fake(seed, limit, client):
            from app.services.keyword_lab.sources.base import KeywordIdea
            # 어느 의문사로 물어도 같은 것을 돌려주는 상황
            return [KeywordIdea(keyword="전기기사 실기 왜 어려운가",
                                source="naver_suggest", engine="naver")]

        monkeypatch.setattr(questions, "naver_suggest", fake)
        monkeypatch.setattr(questions.asyncio, "sleep",
                            lambda *a, **k: _noop())
        out = await questions.fan_out("전기기사 실기", "naver", limit=10)
        assert len(out) == 1, "중복 질문을 여러 번 넣으면 안 된다"
        assert out[0].source == SRC_QUESTION_FANOUT

    @pytest.mark.asyncio
    async def test_seed_echo_is_dropped(self, monkeypatch):
        async def fake(seed, limit, client):
            from app.services.keyword_lab.sources.base import KeywordIdea
            return [KeywordIdea(keyword="전기기사 실기",
                                source="naver_suggest", engine="naver")]

        monkeypatch.setattr(questions, "naver_suggest", fake)
        monkeypatch.setattr(questions.asyncio, "sleep",
                            lambda *a, **k: _noop())
        assert await questions.fan_out("전기기사 실기") == []

    def test_no_paa_scraping(self):
        """PAA 스크래핑을 넣지 않는다 — 약관 위반이고 차단되면 멈춘다."""
        src = (BASE / "app/services/keyword_lab/sources/questions.py").read_text(
            encoding="utf-8")
        assert "google.com/search" not in src
        assert "PAA" in src, "쓰지 않는 이유가 코드에 남아 있어야 한다"


class TestWiring:
    def test_registry_dispatches(self):
        src = (BASE / "app/services/keyword_lab/sources/registry.py").read_text(
            encoding="utf-8")
        assert "SRC_QUESTION_FANOUT" in src and "questions.collect" in src

    def test_module_form_exposes_toggle(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        js = (BASE / "app/static/js/modules/form.js").read_text(encoding="utf-8")
        assert "src_question_fanout" in tpl
        assert "['src_question_fanout', 'question_fanout']" in js

    def test_manual_collect_exposes_toggle(self):
        html = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        js = (BASE / "app/static/js/collection/keyword_pool.js").read_text(
            encoding="utf-8")
        assert "src_question_fanout" in html
        assert "sources.push('question_fanout')" in js

    def test_runner_passes_niche(self):
        src = (BASE / "app/services/title_gen/runner.py").read_text(
            encoding="utf-8")
        assert "active_domains" in src and "niche=domains" in src


async def _noop():
    return None
