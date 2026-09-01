"""키워드 모듈 P2 — 엔진별 지표·월간 발행량·검색량 상한 테스트.

계획서: docs/plans/keyword_module_redesign_plan.md §2 B2

바뀐 축:
    공급 = 누적 문서수 → **최근 30일 발행량**
    판정 = 하한만 → 하한 + **상한**
"""
from datetime import datetime
from pathlib import Path

import pytest

from app.models.keyword_metric import ENGINES, PRIMARY_ENGINE, KeywordMetric
from app.services.keyword_lab import supply as sup
from app.services.keyword_lab.scoring import (
    MAX_SEARCH_VOLUME, Thresholds, judge, saturation_of, supply_of,
)
from app.services.keyword_lab.settings import KeywordModuleSettings

BASE = Path(__file__).resolve().parents[2]


class TestThresholds:
    def test_defaults(self):
        th = Thresholds()
        assert th.min_volume == 100 and th.max_volume == MAX_SEARCH_VOLUME

    def test_build_accepts_max(self):
        th = Thresholds.build(500, 0.3, 20000)
        assert (th.min_volume, th.max_volume) == (500, 20000)

    def test_zero_max_falls_back(self):
        # 상한 0 이면 아무것도 통과 못 한다 — 기본값으로 되돌린다
        assert Thresholds.build(100, 0.2, 0).max_volume == MAX_SEARCH_VOLUME

    def test_max_below_min_falls_back(self):
        assert Thresholds.build(1000, 0.2, 500).max_volume == MAX_SEARCH_VOLUME

    def test_garbage_values(self):
        th = Thresholds.build("abc", "xyz", "nope")
        assert th.min_volume == 100 and th.max_volume == MAX_SEARCH_VOLUME


class TestSupplyMetric:
    def test_prefers_monthly_publication(self):
        assert supply_of(20, 1_000_000) == 20

    def test_falls_back_to_doc_count(self):
        assert supply_of(None, 1234) == 1234

    def test_both_missing(self):
        assert supply_of(None, None) is None

    def test_zero_publication_is_not_none(self):
        # 이번 달에 아무도 안 썼다 = 빈 자리. None(미측정)과 다르다
        assert supply_of(0, 999) == 0

    def test_saturation_uses_supply(self):
        assert saturation_of(1000, 20) == 50.0

    def test_saturation_zero_supply(self):
        assert saturation_of(500, 0) == 500.0

    def test_saturation_missing(self):
        assert saturation_of(None, 10) is None


class TestJudge:
    def test_reject_above_upper_bound(self):
        verdict, reason, _ = judge("맛집", 500_000, 100)
        assert verdict == "reject" and "상한" in reason

    def test_reject_below_lower_bound(self):
        verdict, reason, _ = judge("희귀어", 10, 100)
        assert verdict == "reject" and "하한" in reason

    def test_adopt_uses_publication_when_present(self):
        # 누적 100만이어도 이번 달 발행이 20이면 자리가 있다
        verdict, reason, _ = judge("전기기사", 5000, 1_000_000,
                                   monthly_pub_count=20)
        assert verdict == "adopt" and "발행" in reason

    def test_reject_when_publication_is_crowded(self):
        # 누적이 적어도 이번 달에 쏟아지면 자리가 없다
        verdict, reason, _ = judge("전기기사", 500, 10,
                                   monthly_pub_count=5000)
        assert verdict == "reject" and "포화" in reason

    def test_pending_without_supply(self):
        verdict, reason, _ = judge("전기기사", 500, None)
        assert verdict == "pending" and "공급" in reason

    def test_pending_without_volume(self):
        assert judge("전기기사", None, 100)[0] == "pending"

    def test_risk_type_goes_to_hold(self):
        verdict, _, risk = judge("병원 고객센터 전화번호", 500, 10,
                                 monthly_pub_count=5)
        assert verdict == "hold" and risk == "연락처"

    def test_custom_upper_bound(self):
        th = Thresholds.build(100, 0.2, 1000)
        assert judge("키워드", 2000, 10, th)[0] == "reject"


class TestPublicationCount:
    """네이버는 기간 필터가 없다 — 최신순 표본으로 센다."""

    def _items(self, dates):
        return [{"postdate": d} for d in dates]

    def test_parse_postdate(self):
        assert sup.parse_postdate("20260815") == datetime(2026, 8, 15)

    def test_parse_bad_postdate(self):
        for bad in ("", None, "2026-08-15", "abcd1234", "20261345"):
            assert sup.parse_postdate(bad) is None

    def test_counts_only_recent(self):
        today = datetime(2026, 9, 1)
        items = self._items(["20260830", "20260820", "20260101"])
        fresh, capped = sup.count_recent(items, 30, today)
        assert fresh == 2 and capped is False

    def test_boundary_is_inclusive(self):
        today = datetime(2026, 9, 1)
        fresh, _ = sup.count_recent(self._items(["20260802"]), 30, today)
        assert fresh == 1

    def test_capped_when_sample_is_full(self):
        today = datetime(2026, 9, 1)
        items = self._items(["20260831"] * sup.PUB_SAMPLE_SIZE)
        fresh, capped = sup.count_recent(items, 30, today)
        assert fresh == sup.PUB_SAMPLE_SIZE and capped is True

    def test_not_capped_when_sample_partial(self):
        today = datetime(2026, 9, 1)
        items = self._items(["20260831"] * 10)
        assert sup.count_recent(items, 30, today)[1] is False

    def test_empty_items(self):
        assert sup.count_recent([], 30, datetime(2026, 9, 1)) == (0, False)


class _FakeSearch:
    """search_blog 두 번(누적/최신순)을 흉내낸다."""

    def __init__(self, total=1234, items=None, second_ok=True):
        self.total, self.items, self.second_ok = total, items or [], second_ok
        self.calls = []

    async def search_blog(self, query, display=10, start=1, sort="sim"):
        self.calls.append((query, display, sort))
        if sort == "date":
            if not self.second_ok:
                return {"success": False, "error": "rate limited"}
            return {"success": True, "items": self.items}
        return {"success": True, "total": self.total, "items": []}


class TestMeasureSupply:
    @pytest.mark.asyncio
    async def test_returns_both_metrics(self):
        items = [{"postdate": datetime.now().strftime("%Y%m%d")}] * 5
        search = _FakeSearch(total=9999, items=items)
        out = await sup.measure_supply(search, "전기기사")
        assert out["success"] is True
        assert out["doc_count"] == 9999
        assert out["monthly_pub_count"] == 5

    @pytest.mark.asyncio
    async def test_two_calls_only(self):
        search = _FakeSearch()
        await sup.measure_supply(search, "전기기사")
        assert len(search.calls) == 2
        assert search.calls[1][2] == "date"

    @pytest.mark.asyncio
    async def test_sample_failure_keeps_doc_count(self):
        search = _FakeSearch(total=50, second_ok=False)
        out = await sup.measure_supply(search, "전기기사")
        # 누적은 받았으므로 실패가 아니다. 발행량만 비어 있다.
        assert out["success"] is True
        assert out["doc_count"] == 50
        assert out["monthly_pub_count"] is None

    @pytest.mark.asyncio
    async def test_total_failure(self):
        class Dead:
            async def search_blog(self, *a, **k):
                return {"success": False, "error": "키 없음"}

        out = await sup.measure_supply(Dead(), "전기기사")
        assert out["success"] is False and out["error"] == "키 없음"


class TestEngineMetrics:
    def test_engine_constants(self):
        assert PRIMARY_ENGINE in ENGINES
        assert set(ENGINES) == {"naver", "google"}

    def test_unique_per_candidate_and_engine(self):
        uniques = [c for c in KeywordMetric.__table__.constraints
                   if c.__class__.__name__ == "UniqueConstraint"]
        assert {col.name for col in uniques[0].columns} == {"candidate_id",
                                                            "engine"}

    def test_has_publication_columns(self):
        cols = KeywordMetric.__table__.columns
        for name in ("monthly_pub_count", "pub_count_capped",
                     "volume_is_range"):
            assert name in cols


class TestSettings:
    def test_new_keys_parsed(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"max_volume": 50000, "pub_window_days": 7}})
        assert cfg.max_volume == 50000 and cfg.pub_window_days == 7

    def test_defaults(self):
        cfg = KeywordModuleSettings.parse({})
        assert cfg.max_volume == 100_000 and cfg.pub_window_days == 30

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"max_volume": 4242}})
        assert cfg.to_dict()["max_volume"] == 4242

    def test_window_never_zero(self):
        assert KeywordModuleSettings.parse(
            {"keyword": {"pub_window_days": 0}}).pub_window_days == 1


class TestCollectAndMeasureShareThresholds:
    """D-8 — 수집 시점과 측정 시점이 같은 기준을 쓴다."""

    def test_service_holds_thresholds(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "self.thresholds" in src
        assert "judge(keyword, volume, None, self.thresholds)" in src


class TestScreenShowsPublication:
    def test_column_added(self):
        js = (BASE / "app/static/js/keyword_lab/app.js").read_text(
            encoding="utf-8")
        assert "monthly_pub_count" in js
        assert "max_volume: this.maxVolume" in js

    def test_module_form_has_upper_bound(self):
        js = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "formData.keyword.max_volume" in js
        assert "formData.keyword.pub_window_days" in js
