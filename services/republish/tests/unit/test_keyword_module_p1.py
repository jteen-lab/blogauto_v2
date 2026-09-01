"""키워드 모듈 P1 — 품질 관문 통과와 재고 기준 통일 회귀 테스트.

배경(docs/plans/keyword_management_review.md):
    D-5 재고를 세는 기준과 제목을 꺼내는 기준이 달라 사장 재고가 쌓였다
    D-7 금지어 필터·유사도 그룹핑·중복 검사를 전부 우회했다
"""
import types
from pathlib import Path

import pytest

from app.services.generation.inventory_trigger import InventoryTrigger
from app.services.keyword_lab import inventory as inv
from app.services.keyword_lab.title_gate import TitleGate, blocking_filter

BASE = Path(__file__).resolve().parents[2]


def _filter(value, kind="keyword", target="title", active=True):
    return types.SimpleNamespace(
        filter_value=value, filter_type=kind,
        target_type=target, is_active=active)


class TestBlockingFilter:
    """금지어 판정은 기존 수집과 같은 규칙을 쓴다."""

    def test_keyword_hit(self):
        hit = blocking_filter([_filter("현금화")], "상품권 현금화 방법")
        assert hit is not None

    def test_keyword_miss(self):
        assert blocking_filter([_filter("현금화")], "김치찌개 끓이는 법") is None

    def test_case_insensitive(self):
        assert blocking_filter([_filter("VPN")], "무료 vpn 추천") is not None

    def test_pattern_type(self):
        f = _filter(r"\d{3}-\d{4}", kind="pattern")
        assert blocking_filter([f], "문의 010-1234 번호") is not None

    def test_broken_pattern_is_skipped(self):
        f = _filter("[unclosed", kind="pattern")
        # 잘못된 정규식이 전체 판정을 죽이면 안 된다
        assert blocking_filter([f], "아무 제목") is None

    def test_target_type_keyword_only_is_ignored(self):
        f = _filter("현금화", target="keyword")
        assert blocking_filter([f], "상품권 현금화") is None

    def test_target_both_applies(self):
        f = _filter("현금화", target="both")
        assert blocking_filter([f], "상품권 현금화") is not None

    def test_empty_inputs(self):
        assert blocking_filter([], "제목") is None
        assert blocking_filter([_filter("x")], "") is None


class TestTempStaging:
    """분류 성공 여부를 status 로 남긴다 — 미분류는 회수 큐가 된다."""

    def _gate(self):
        return TitleGate(db=None, user_id=1)

    def test_classified_is_categorized(self):
        temp = self._gate()._build_temp("제목", 1, 2, 3)
        assert temp.status == "categorized"
        assert (temp.topic_id, temp.subtopic_id) == (1, 2)

    def test_unclassified_stays_new(self):
        temp = self._gate()._build_temp("제목", None, None, None)
        assert temp.status == "new"

    def test_topic_only_counts_as_classified(self):
        assert self._gate()._build_temp("제목", 7, None, None).status == "categorized"

    def test_collection_stage_marks_origin(self):
        assert self._gate()._build_temp("제목", 1, 1, 1).collection_stage == "keyword_module"


class TestTitleMakerUsesGate:
    """D-7 — 제목이 main_titles 로 직행하지 않는다."""

    def test_no_direct_main_title_insert(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert "MainTitle(" not in src
        assert "TitleGate" in src

    def test_gate_moves_through_transfer_service(self):
        src = (BASE / "app/services/keyword_lab/title_gate.py").read_text(
            encoding="utf-8")
        assert "TitleTransferService" in src
        assert "move_to_main" in src
        assert "auto_group=True" in src


class TestInventoryUnification:
    """D-5 — 세는 기준과 꺼내는 기준이 같다."""

    def test_trigger_exposes_count(self):
        assert hasattr(InventoryTrigger, "count_available_titles")

    def test_runner_no_longer_counts_on_its_own(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "async def _inventory(" not in src
        assert "available_titles(" in src and "target_inventory(" in src

    def test_available_titles_delegates_to_trigger(self):
        src = (BASE / "app/services/keyword_lab/inventory.py").read_text(
            encoding="utf-8")
        assert "count_available_titles" in src


class TestTargetInventory:
    """목표 재고 = max(하한, 일일발행 × 리드타임 × 안전계수)."""

    @pytest.mark.asyncio
    async def test_no_blog_uses_floor(self):
        cfg = types.SimpleNamespace(min_inventory=30)
        assert await inv.target_inventory(None, None, cfg) == 30

    @pytest.mark.asyncio
    async def test_no_history_uses_floor(self, monkeypatch):
        monkeypatch.setattr(inv, "daily_publish_rate",
                            lambda db, blog_id, days=14: _async(0.0))
        cfg = types.SimpleNamespace(min_inventory=30)
        blog = types.SimpleNamespace(id=1)
        assert await inv.target_inventory(None, blog, cfg) == 30

    @pytest.mark.asyncio
    async def test_fast_blog_exceeds_floor(self, monkeypatch):
        # 하루 20편 × 3일 × 1.5 = 90 > 하한 30
        monkeypatch.setattr(inv, "daily_publish_rate",
                            lambda db, blog_id, days=14: _async(20.0))
        cfg = types.SimpleNamespace(min_inventory=30)
        blog = types.SimpleNamespace(id=1)
        assert await inv.target_inventory(None, blog, cfg) == 90

    @pytest.mark.asyncio
    async def test_slow_blog_keeps_floor(self, monkeypatch):
        # 하루 1편 × 3일 × 1.5 = 5 < 하한 30
        monkeypatch.setattr(inv, "daily_publish_rate",
                            lambda db, blog_id, days=14: _async(1.0))
        cfg = types.SimpleNamespace(min_inventory=30)
        blog = types.SimpleNamespace(id=1)
        assert await inv.target_inventory(None, blog, cfg) == 30

    @pytest.mark.asyncio
    async def test_rounds_up(self, monkeypatch):
        # 하루 2.4편 × 3일 × 1.5 = 10.8 → 11
        monkeypatch.setattr(inv, "daily_publish_rate",
                            lambda db, blog_id, days=14: _async(2.4))
        cfg = types.SimpleNamespace(min_inventory=0)
        blog = types.SimpleNamespace(id=1)
        assert await inv.target_inventory(None, blog, cfg) == 11


async def _async(value):
    return value


class TestFileSizeRule:
    """CLAUDE.md 규칙 3 — 파일 500줄 이하."""

    @pytest.mark.parametrize("path", [
        "app/services/generation/inventory_trigger.py",
        "app/services/generation/inventory_category_mixin.py",
        "app/services/keyword_lab/title_gate.py",
        "app/services/keyword_lab/inventory.py",
        "app/services/keyword_lab/runner.py",
        "app/services/keyword_lab/title_maker.py",
    ])
    def test_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
