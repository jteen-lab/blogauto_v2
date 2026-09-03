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
        assert cfg.urls_per_domain == 30, "사이트맵 전량 적재로 돌아가면 안 된다"
        assert cfg.max_pending_domains == 50
        assert cfg.niche_mode == NICHE_MARK, "초기 기본은 되돌릴 수 있는 쪽"

    def test_out_of_range_falls_back(self):
        cfg = TitleCollectSettings.parse({"collect": {"seed_limit": 0,
                                                      "urls_per_domain": 9999}})
        assert cfg.seed_limit == 1 and cfg.urls_per_domain == 200

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

    def test_full_batch_stays_partial(self):
        d = NicheDomain(extract_status=EXTRACT_PENDING, extracted_count=0)
        DomainExtractor._advance(d, 30, 30)
        assert d.extract_status == EXTRACT_PARTIAL, "더 남았을 수 있다"
        assert d.extracted_count == 30

    def test_short_batch_is_done(self):
        d = NicheDomain(extract_status=EXTRACT_PARTIAL, extracted_count=10)
        DomainExtractor._advance(d, 3, 30)
        assert d.extract_status == EXTRACT_DONE
        assert d.extracted_count == 13

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
        assert 'getattr(source_title, "recombined_from_id", None)' in src
        assert "재조합 건너뜀" in src

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
