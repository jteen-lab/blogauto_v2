"""제목 작업대(W1~W4·W10·W11) 회귀 테스트.

핵심 결함이 둘이었다.
    1. 도메인이 한 번 밀리면 다시 꺼내지지 않았다(진행 상태가 없었다)
    2. 니치 대조가 없어 "분류는 됐지만 쓰는 블로그가 없는" 제목이 쌓였다

계획서: docs/plans/title_tab_workplan.md
"""
import asyncio
from pathlib import Path

import pytest

from app.models.niche_domain import (
    EXTRACT_DONE, EXTRACT_PARTIAL, EXTRACT_PENDING, NicheDomain,
)
from app.services.title_collect.extractor import DomainExtractor, _priority
from app.services.title_collect.niche_gate import (
    NicheGate, VERDICT_OFF, VERDICT_PASS, VERDICT_SKIP, VERDICT_UNKNOWN,
)
from app.services.title_collect.settings import (
    NICHE_BLOCK, NICHE_MARK, TitleCollectSettings,
)
from app.services.title_collect.store import clean
from app.services.title_collect.workbench import _summarize, _total
from app.services import title_source as ts

BASE = Path(__file__).resolve().parents[2]


class TestSettings:
    def test_defaults(self):
        cfg = TitleCollectSettings.parse({})
        assert cfg.seed_limit == 10
        assert cfg.titles_per_keyword == 30
        assert cfg.extract_urls == 100
        assert cfg.niche_mode == NICHE_MARK, "초기 기본은 되돌릴 수 있는 쪽"

    def test_no_throttles_remain(self):
        """상한을 두면 초기 상태(도메인 전부 미처리)에서 교착이 생긴다.

        옛 설계의 도메인당 URL·회차당 새 도메인·미완료 도메인 상한 때문에
        ①이 영구히 건너뛰어졌다. 수집은 수집만 한다.
        """
        cfg = TitleCollectSettings.parse({})
        for gone in ("urls_per_domain", "domains_per_cycle",
                     "max_pending_domains", "extract_domains",
                     "titles_per_domain"):
            assert not hasattr(cfg, gone), gone

    def test_out_of_range_falls_back(self):
        cfg = TitleCollectSettings.parse(
            {"collect": {"seed_limit": 0, "titles_per_keyword": 9999}})
        assert cfg.seed_limit == 1 and cfg.titles_per_keyword == 100

    def test_unknown_niche_mode(self):
        assert TitleCollectSettings.parse(
            {"collect": {"niche_mode": "??"}}).niche_mode == NICHE_MARK

    def test_round_trip(self):
        cfg = TitleCollectSettings.parse({"collect": {"niche_mode": "block"}})
        assert cfg.to_dict()["niche_mode"] == NICHE_BLOCK


class TestNicheGate:
    def _gate(self, topics, mode=NICHE_MARK):
        gate = NicheGate(db=None, mode=mode)
        gate._topics = topics
        return gate

    def test_no_active_topics_skips(self):
        """카테고리가 없으면 판정하지 않는다 — 전량 차단 사고 방지."""
        assert asyncio.run(self._gate(set()).judge(1)) == VERDICT_SKIP

    def test_in_niche(self):
        assert asyncio.run(self._gate({1, 2}).judge(2)) == VERDICT_PASS

    def test_off_niche(self):
        assert asyncio.run(self._gate({1}).judge(9)) == VERDICT_OFF

    def test_unclassified(self):
        assert asyncio.run(self._gate({1}).judge(None)) == VERDICT_UNKNOWN

    def test_mark_mode_always_stores(self):
        """표시 모드는 무관해도 저장한다 — 무엇이 걸렸는지 보이는 편이 낫다."""
        assert asyncio.run(self._gate({1}).should_store(9)) is True

    def test_block_mode_drops_off_niche(self):
        gate = self._gate({1}, NICHE_BLOCK)
        assert asyncio.run(gate.should_store(9)) is False
        assert asyncio.run(gate.should_store(1)) is True

    def test_block_mode_keeps_unclassified(self):
        """미분류는 회수 큐다. 차단 모드에서도 버리지 않는다."""
        gate = self._gate({1}, NICHE_BLOCK)
        assert asyncio.run(gate.should_store(None)) is True


class TestExtractProgress:
    """도메인이 방치되던 원인 — 진행 상태를 남기지 않았다."""

    def test_partial_comes_first(self):
        partial = NicheDomain(domain="p", extract_status=EXTRACT_PARTIAL,
                              extracted_count=20, promoted_count=0)
        pending = NicheDomain(domain="n", extract_status=EXTRACT_PENDING,
                              extracted_count=100, promoted_count=90)
        rows = sorted([pending, partial], key=_priority)
        assert rows[0].domain == "p", "하다 만 것을 먼저 끝낸다"

    def test_quality_orders_within_stage(self):
        good = NicheDomain(domain="g", extract_status=EXTRACT_PARTIAL,
                           extracted_count=100, promoted_count=50)
        bad = NicheDomain(domain="b", extract_status=EXTRACT_PARTIAL,
                          extracted_count=100, promoted_count=1)
        rows = sorted([bad, good], key=_priority)
        assert rows[0].domain == "g"

    def test_small_sample_is_neutral(self):
        """표본이 적으면 좋다고도 나쁘다고도 볼 수 없다 — 중간에 둔다."""
        new = NicheDomain(domain="new", extract_status=EXTRACT_PARTIAL,
                          extracted_count=2, promoted_count=2)
        bad = NicheDomain(domain="bad", extract_status=EXTRACT_PARTIAL,
                          extracted_count=100, promoted_count=1)
        good = NicheDomain(domain="good", extract_status=EXTRACT_PARTIAL,
                           extracted_count=100, promoted_count=90)
        rows = sorted([bad, new, good], key=_priority)
        assert [r.domain for r in rows] == ["good", "new", "bad"]


class TestSitemapExtraction:
    """② 도메인 추출 — 사이트맵 기반, 예산은 회차 전체, 이어서 캔다."""

    def _domain(self, **kw):
        base = {"domain": "a.com", "extract_status": EXTRACT_PENDING,
                "extracted_count": 0, "url_count": 0}
        base.update(kw)
        return NicheDomain(**base)

    def _extractor(self, urls, titles=None):
        class Parser:
            async def fetch_urls(self, domain, max_urls=None):
                # 상한을 걸면 캘 수 있는 것을 버린다
                assert max_urls is None, "사이트맵 URL 수를 자르면 안 된다"
                return list(urls)

        async def fetch_title(url, client=None):
            return (titles or {}).get(url, f"제목 {url}")

        return DomainExtractor(db=None, user_id=1, sitemap_parser=Parser(),
                               title_fetcher=fetch_title)

    @pytest.mark.asyncio
    async def test_resumes_from_offset(self):
        """다음 회차는 멈춘 자리에서 이어 캔다."""
        urls = [f"https://a.com/{i}" for i in range(500)]
        extractor = self._extractor(urls)
        domain = self._domain(extracted_count=100)
        store = _FakeStore()

        got, empty = await extractor._drain(domain, 50, store, None)

        assert not empty
        assert got["seen"] == 50
        assert domain.extracted_count == 150, "101번째부터 이어서"
        assert domain.extract_status == EXTRACT_PARTIAL
        assert store.urls[0] == "https://a.com/100"

    @pytest.mark.asyncio
    async def test_url_count_is_not_capped(self):
        """관측 수는 사이트맵 실제 URL 수다. 801개로 자르지 않는다."""
        urls = [f"https://a.com/{i}" for i in range(10_000)]
        extractor = self._extractor(urls)
        domain = self._domain()

        await extractor._drain(domain, 10, _FakeStore(), None)

        assert domain.url_count == 10_000

    @pytest.mark.asyncio
    async def test_done_when_drained(self):
        urls = [f"https://a.com/{i}" for i in range(30)]
        extractor = self._extractor(urls)
        domain = self._domain(extracted_count=25)

        await extractor._drain(domain, 100, _FakeStore(), None)

        assert domain.extracted_count == 30
        assert domain.extract_status == EXTRACT_DONE

    @pytest.mark.asyncio
    async def test_no_sitemap_is_closed(self):
        """못 읽는 도메인을 계속 열면 회차가 그것만 반복한다."""
        extractor = self._extractor([])
        domain = self._domain()

        got, empty = await extractor._drain(domain, 100, _FakeStore(), None)

        assert empty and got["seen"] == 0
        assert domain.extract_status == EXTRACT_DONE

    @pytest.mark.asyncio
    async def test_budget_is_run_wide(self):
        """예산은 도메인당이 아니라 회차 전체다.

        30개 남은 도메인에서 30개만 쓰고, 남은 예산은 다음 도메인 몫이다.
        """
        urls = [f"https://a.com/{i}" for i in range(30)]
        extractor = self._extractor(urls)
        domain = self._domain()

        got, _ = await extractor._drain(domain, 100, _FakeStore(), None)

        assert got["seen"] == 30, "남은 예산 70은 다음 도메인으로 넘어간다"


class _FakeStore:
    """TitleStore 대역 — 무엇이 들어왔는지만 본다."""

    def __init__(self):
        self.urls = []
        self.samples = []

    async def add(self, title, url, keyword, candidate_id, source,
                  expires_at=None):
        self.urls.append(url)
        return {"stored": True, "reason": "ok", "domain": "a.com"}


class TestCollectorScope:
    """① 제목 수집 — 검색하고 제목·도메인만 남긴다."""

    def test_does_not_crawl_urls(self):
        src = (BASE / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        assert "sitemap" not in src.lower(), "URL 캐기는 ②의 몫이다"

    def test_registers_domain_without_url_count(self):
        src = (BASE / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        assert "url_count=0" in src

    def test_no_skip_gate(self):
        """건너뛰는 조건은 시드가 없을 때뿐이다."""
        src = (BASE / "app/services/title_collect/collector.py").read_text(
            encoding="utf-8")
        assert "max_pending_domains" not in src
        assert "신규 수집을 건너뜁니다" not in src


class TestSummary:
    def test_counts_both_sections(self):
        out = {"collect": {"search": {"saved": 12},
                           "extract": {"saved": 30, "domains": 5}},
               "gen": {"l1": {"made": 7}}}
        assert _total(out) == 0, "collect.saved 합계가 아직 없으면 0"
        text = _summarize(out)
        assert "수집 12건" in text and "추출 30건" in text and "L1 7편" in text

    def test_skip_reason_comes_first(self):
        out = {"collect": {"search": {"saved": 0, "skipped": True,
                                      "message": "미완료 도메인 60개"}}}
        assert _summarize(out).startswith("⚠ 미완료 도메인 60개")

    def test_nothing_enabled(self):
        assert "실행한 섹션이 없습니다" in _summarize({})


class TestTitleSource:
    def test_groups_cover_all_codes(self):
        grouped = set(ts.GENERATED) | set(ts.COLLECTED) | set(ts.LEGACY)
        assert grouped == set(ts.ALL_SOURCES)

    def test_every_code_has_label_and_tone(self):
        for code in ts.ALL_SOURCES:
            assert ts.LABEL.get(code), code
            assert ts.TONE.get(code), code

    def test_unknown_group_is_empty(self):
        assert ts.codes_for_group("없는묶음") == []

    def test_unknown_code_falls_back(self):
        assert ts.label("모르는코드") == "모르는코드"


class TestStoreClean:
    @pytest.mark.parametrize("raw,expected", [
        ("<b>전기기사</b> 실기", "전기기사 실기"),
        ("제목&nbsp;하나", "제목 하나"),
        ("  공백   정리  ", "공백 정리"),
        ("", ""),
    ])
    def test_clean(self, raw, expected):
        assert clean(raw) == expected


class TestWiring:
    def test_panel_included(self):
        src = (BASE / "app/templates/collection/_titles.html").read_text(
            encoding="utf-8")
        assert "_title_workbench.html" in src

    def test_sections_are_checkbox_gated(self):
        tpl = (BASE / "app/templates/collection/_title_workbench.html").read_text(
            encoding="utf-8")
        # 체크해야 설정이 열린다 — 키워드 탭과 같은 구조
        assert 'x-model="collect.enabled"' in tpl
        assert 'x-model="gen.enabled"' in tpl
        assert 'x-show="collect.enabled"' in tpl
        assert 'x-show="gen.enabled"' in tpl

    def test_blog_list_parsed_correctly(self):
        """응답은 {"blogs": [...]} 다. items 를 먼저 보면 목록이 빈다."""
        js = (BASE / "app/static/js/collection/title_workbench.js").read_text(
            encoding="utf-8")
        assert "d.blogs || d.items" in js

    def test_ai_selection_exposed(self):
        """AI 를 못 고르면 L1·L3 이 통째로 0편이 된다."""
        tpl = (BASE
               / "app/templates/collection/_title_workbench.html").read_text(
            encoding="utf-8")
        js = (BASE / "app/static/js/collection/title_workbench.js").read_text(
            encoding="utf-8")
        assert 'x-model="gen.ai_provider"' in tpl
        assert "ai_provider: ''" in js

    def test_failure_reason_surfaces(self):
        """'L1 0편' 만 보이고 사유가 로그에만 있으면 안 된다."""
        src = (BASE / "app/services/title_collect/workbench.py").read_text(
            encoding="utf-8")
        assert 'out.get("errors")' in src
        assert "제목 생성 AI 를 고르거나" in src

    def test_blog_ai_is_the_fallback(self):
        """AI 를 비우면 블로그의 제목 AI 를 쓴다. 매번 고르게 하면 실수한다."""
        src = (BASE / "app/services/title_collect/workbench.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def _make_ask("):
                    src.index("async def _store_news(")]
        assert 'ai_config.get("title_ai")' in block
        assert 'writing_ai.get("provider")' in block
        assert "_make_ask(gen, blog)" in src

    def test_model_is_a_dropdown(self):
        """모델명을 직접 적게 하면 오타 하나로 생성이 통째로 실패한다."""
        tpl = (BASE
               / "app/templates/collection/_title_workbench.html").read_text(
            encoding="utf-8")
        js = (BASE / "app/static/js/collection/title_workbench.js").read_text(
            encoding="utf-8")
        assert 'x-model="gen.ai_model"' in tpl
        assert "modelsFor(gen.ai_provider)" in tpl
        assert "ai-models?capability=text" in js
        # 저장된 값이 목록에 없으면 select 가 빈 값을 되쓴다
        assert "if (saved && !list.includes(saved))" in js

    def test_sitemap_is_not_capped(self):
        """801개 상한은 옛 집계값일 뿐, 추출은 전체를 읽는다."""
        src = (BASE / "app/services/title_collect/extractor.py").read_text(
            encoding="utf-8")
        assert "max_urls=None" in src
        assert "domain.url_count = len(urls)" in src

    def test_news_has_no_rule_fallback(self):
        """AI 없이 뉴스 원문을 붙여 만들면 원문이 재고에 들어간다."""
        src = (BASE / "app/services/title_gen/news_gen.py").read_text(
            encoding="utf-8")
        assert "에는 어떤 영향이 있을까" not in src.split('"""')[-1]
        assert "제목 생성 AI 를 고르세요" in src

    def test_uses_polling_not_long_request(self):
        """Caddy 가 60초에 헤더를 끊는다. 배경 실행 + 폴링이어야 한다."""
        js = (BASE / "app/static/js/collection/title_workbench.js").read_text(
            encoding="utf-8")
        assert "title-workbench/status" in js and "setInterval" in js

    def test_router_registered(self):
        from app.main import app

        paths = {r.path for r in app.routes}
        assert "/api/v1/title-workbench/run" in paths
        assert "/api/v1/title-workbench/status" in paths

    def test_source_filter_in_list_api(self):
        src = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert "source_group" in src and "codes_for_group" in src


class TestDomainOps:
    """W5·W6 — 대량삭제 판정과 품질 점수."""

    def test_threshold_uses_count_only(self):
        """비율(%) 기준을 쓰지 않는다.

        100건짜리 도메인에서 30건을 지워야 반응하면 이 기능을 만든 의미가
        없다. 운영자는 3~5건이면 결이 다름을 안다.
        """
        from app.services.title_collect import domain_ops

        src = (BASE / "app/services/title_collect/domain_ops.py").read_text(
            encoding="utf-8")
        assert "ratio" not in src and "percent" not in src
        assert domain_ops.DEFAULT_THRESHOLD == 5

    @pytest.mark.parametrize("value,expected", [
        (None, 5), ("", 5), (0, 3), (1, 3), (5, 5), (15, 15), (99, 20),
        ("x", 5),
    ])
    def test_clamp_threshold(self, value, expected):
        from app.services.title_collect.domain_ops import clamp_threshold

        assert clamp_threshold(value) == expected

    def test_quality_needs_sample(self):
        """표본이 적으면 점수를 믿을 수 없다."""
        assert NicheDomain(extracted_count=9, promoted_count=9
                           ).quality_score() is None
        assert NicheDomain(extracted_count=10, promoted_count=1
                           ).quality_score() == 0.1

    def test_blocked_domain_is_not_collected(self):
        assert NicheDomain(is_blocked=True).usable_for_collect() is False
        assert NicheDomain(is_blocked=False).usable_for_collect() is True

    def test_block_uses_separate_field(self):
        """is_active(각도 참조)를 재수집 차단에 겸용하면 안 된다."""
        src = (BASE / "app/services/title_collect/domain_ops.py").read_text(
            encoding="utf-8")
        assert "is_blocked = True" in src
        assert "is_active = False" not in src

    def test_bulk_delete_reports_hits(self):
        src = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert "record_deletions" in src and "domain_hits" in src

    def test_popup_wired(self):
        index = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "_domain_purge.html" in index
        assert "domain-purge" in index

    def test_promotion_counted(self):
        """승격률의 분자가 실제로 올라가야 한다."""
        src = (BASE / "app/services/title_transfer_service.py").read_text(
            encoding="utf-8")
        assert "_count_promotions" in src
        assert "promoted_count" in src

    def test_transfer_carries_candidate_id(self):
        src = (BASE / "app/services/title_transfer_service.py").read_text(
            encoding="utf-8")
        assert "candidate_id=getattr(temp_title" in src


class TestRecombine:
    """W7~W9 — 재조합 이동·건너뛰기·그룹 소진·최신성."""

    def test_no_double_recombine(self):
        """이미 재조합된 제목을 또 돌리면 원문에서 두 단계 멀어진다."""
        src = (BASE / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        assert "if is_recombined(source_title):" in src
        assert "재조합 건너뜀" in src

    def test_recombined_check_is_type_safe(self):
        """truthy 검사만 하면 목/프록시가 걸려 원본까지 건너뛴다."""
        from unittest.mock import MagicMock

        from app.services.generation.title_lifecycle import is_recombined

        class Real:
            recombined_from_id = 5

        class Fresh:
            recombined_from_id = None

        assert is_recombined(Real()) is True
        assert is_recombined(Fresh()) is False
        assert is_recombined(MagicMock()) is False
        assert is_recombined(object()) is False

    def test_group_is_consumed(self):
        """그룹 전체 소진(C안). 재조합만 소진하면 원본으로 또 쓴다."""
        gen = (BASE / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        assert "consume_group(self.db, source_title)" in gen
        life = (BASE / "app/services/generation/title_lifecycle.py").read_text(
            encoding="utf-8")
        assert "MainTitle.group_id == source_title.group_id" in life
        assert "row.mark_used()" in life

    def test_style_is_recorded(self):
        src = (BASE / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        assert "title_style=selected_style" in src

    def test_keywords_passed_to_recombiner(self):
        src = (BASE / "app/services/generation/generator.py").read_text(
            encoding="utf-8")
        assert "keywords=title_keywords(source_title)" in src
        recomb = (BASE / "app/services/generation/title_recombiner.py"
                  ).read_text(encoding="utf-8")
        assert "반드시 유지할 핵심어" in recomb

    def test_result_keeps_origin_group(self):
        """별도 그룹을 만들지 않는다 — 같은 그룹 안에서 필드로 구분."""
        src = (BASE / "app/services/recombine/service.py").read_text(
            encoding="utf-8")
        assert "group_id=origin.group_id" in src
        assert "is_group_representative=False" in src
        assert "recombined_from_id=origin.id" in src

    def test_badge_in_list(self):
        tpl = (BASE / "app/templates/collection/_titles_main.html").read_text(
            encoding="utf-8")
        assert "recombined_from_id" in tpl and "♻" in tpl


class TestFreshness:
    """W9 — 최신성. 규칙으로 후보를 고르고 AI 는 최소로 쓴다."""

    def _now(self):
        from datetime import datetime, timezone
        return datetime(2026, 9, 3, tzinfo=timezone.utc)

    def _old(self):
        from datetime import datetime, timezone
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_past_year_is_stale(self):
        from app.services.recombine.freshness import is_stale

        assert is_stale("2024년 전기기사 접수", self._old(), self._now())

    def test_fresh_title_untouched(self):
        from app.services.recombine.freshness import is_stale

        assert not is_stale("전기기사 실기 준비법", self._old(), self._now())

    def test_year_swap_needs_no_ai(self):
        """가장 흔한 경우다. AI 비용 0으로 끝나야 한다."""
        from app.services.recombine.freshness import plan

        out = plan("2024년 전기기사 접수", self._old(), self._now())
        assert out["rule_only"] == "2026년 전기기사 접수"
        assert out["needs_ai"] is False

    def test_future_year_not_rewritten(self):
        """'2027년 시행' 을 과거로 당기면 안 된다."""
        from app.services.recombine.freshness import refresh_years

        assert refresh_years("2027년 시행", self._now()) == "2027년 시행"

    def test_time_word_needs_ai(self):
        from app.services.recombine.freshness import plan

        out = plan("올해 전기기사 준비법", self._old(), self._now())
        assert out["stale"] and out["needs_ai"] and out["rule_only"] is None

    def test_no_created_at_is_not_stale(self):
        from app.services.recombine.freshness import is_stale

        assert not is_stale("올해 준비법", None, self._now())


class TestStylePicker:
    """W8 — 성과 가중 선택. 무작위를 없애지 않는다."""

    def test_single_style_short_circuit(self):
        import asyncio

        from app.services.generation.style_picker import pick

        assert asyncio.run(pick(None, ["viral"])) == "viral"

    def test_empty_returns_none(self):
        import asyncio

        from app.services.generation.style_picker import pick

        assert asyncio.run(pick(None, [])) is None

    def test_weight_is_capped(self):
        """한 스타일이 판을 독점하면 탐색이 죽는다."""
        from app.services.generation import style_picker as sp

        assert sp.MAX_WEIGHT <= 3.0 and sp.BASE_WEIGHT > 0

    def test_small_sample_ignored(self):
        from app.services.generation import style_picker as sp

        assert sp.MIN_SAMPLE >= 5, "1건 성공을 100%로 읽으면 안 된다"


class TestKeywordAxisExpansion:
    """W13 — 확장 재조합 ②. candidate_id 연결이 전제다."""

    @pytest.mark.asyncio
    async def test_no_candidate_means_no_axes(self):
        """무엇으로 넓힐지 모르는 채 확장하면 엉뚱한 제목이 나온다."""
        from app.models.title import MainTitle
        from app.services.recombine.service import RecombineService

        service = RecombineService(db=None, user_id=1)
        row = MainTitle(title="제목", candidate_id=None)
        assert await service._question_axes(row) == []

    def test_axes_use_rule_based_questions(self):
        """AI 없이 축을 넓힌다 — 의도 분류가 이미 질문을 만든다."""
        src = (BASE / "app/services/recombine/service.py").read_text(
            encoding="utf-8")
        assert "from ..keyword_lab.intent import questions" in src

    def test_expand_is_opt_in(self):
        """기본은 꺼짐. 확장이 항상 좋은 것은 아니다."""
        import inspect

        from app.services.recombine.service import RecombineService

        params = inspect.signature(RecombineService.run).parameters
        assert params["expand"].default is False

    def test_ui_and_api_wired(self):
        tpl = (BASE / "app/templates/collection/_recombine_panel.html"
               ).read_text(encoding="utf-8")
        api = (BASE / "app/routers/title_recombine.py").read_text(
            encoding="utf-8")
        assert 'x-model="expand"' in tpl
        assert "expand: bool = False" in api
        assert "expand=payload.expand" in api
