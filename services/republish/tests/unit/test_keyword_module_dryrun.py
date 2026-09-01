"""검증 모드(dry_run)와 실행 게이트 회귀 테스트.

배경: 플로우에서 1회 실행했더니 "성공" 으로만 보이고 수집이 0건이었다.
    실제로는 **재고 충분으로 건너뛴 것**이었고, 블로그가 연결되지 않아
    전체 재고(2,249)를 블로그 기준(30)과 비교하고 있었다.

바뀐 점
    1. 블로그가 없으면 재고 판단이 불가능하므로 게이트를 통과시킨다
    2. 사용자가 직접 누른 단발 실행은 force 로 돈다
    3. 아무것도 안 돌았으면 사유가 요약 **맨 앞**에 나온다
    4. 검증 모드에서는 제목을 데이터 관리에 저장하지 않고 결과만 준다
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.keyword_lab.runner import KeywordModuleRunner
from app.services.keyword_lab.settings import KeywordModuleSettings
from app.services.keyword_lab.title_gate import TitleGate

BASE = Path(__file__).resolve().parents[2]


class TestInventoryGate:
    """블로그가 없으면 재고로 막지 않는다."""

    def test_gate_requires_a_blog(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "if not force and blog is not None" in src

    def test_reason_comment_kept(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        # 왜 통과시키는지가 코드에 남아 있어야 다음 사람이 되돌리지 않는다
        assert "판단 불가는 통과로 본다" in src


class TestSingleRunForces:
    """직접 누른 실행이 조용히 건너뛰면 테스트가 불가능하다."""

    def test_flow_single_run_forces(self):
        src = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        assert "target_module, kw_blogs, db, force=True" in src

    def test_background_flow_does_not_force(self):
        src = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        # 자동 실행은 재고를 봐야 한다 — 매번 도는 것은 API 낭비
        assert "keyword_module, kw_blogs, db\n" in src


class TestSummaryMessage:
    def test_skip_reason_comes_first(self):
        out = KeywordModuleRunner._aggregate(
            [("A", {"success": True, "skipped": True,
                    "message": "재고 충분 (2249/30)"})])
        assert out["message"].startswith("실행 안 됨 — 재고 충분")

    def test_dry_run_is_stated(self):
        out = KeywordModuleRunner._aggregate([("A", {
            "success": True, "collect": {"saved": 12},
            "measure": {"measured": 5},
            "titles": {"made": 0, "dry_run": True, "preview": [
                {"title": "전기기사 실기 준비", "state": "ready"}]}})])
        assert "검증 모드 — 저장 안 함" in out["message"]
        assert out["dry_run"] is True

    def test_sample_titles_shown(self):
        out = KeywordModuleRunner._aggregate([("A", {
            "success": True, "collect": {"saved": 1}, "measure": {},
            "titles": {"made": 0, "dry_run": True, "preview": [
                {"title": "전기기사 실기 준비", "state": "ready"},
                {"title": "상품권 현금화", "state": "blocked"}]}})])
        # 통과한 것만 예시로 보여 준다
        assert "전기기사 실기 준비" in out["message"]
        assert "상품권 현금화" not in out["message"]

    def test_normal_mode_reports_saved_count(self):
        out = KeywordModuleRunner._aggregate([("A", {
            "success": True, "collect": {"saved": 3}, "measure": {},
            "titles": {"made": 7, "dry_run": False, "preview": []}})])
        assert "제목 7편" in out["message"]
        assert "검증 모드" not in out["message"]

    def test_preview_is_capped(self):
        rows = [("A", {"success": True, "collect": {}, "measure": {},
                       "titles": {"made": 0, "dry_run": True,
                                  "preview": [{"title": f"t{i}",
                                               "state": "ready"}
                                              for i in range(200)]}})]
        assert len(KeywordModuleRunner._aggregate(rows)["preview"]) == 60


class TestDryRunSetting:
    def test_default_is_on(self):
        # 검증 없이 재고를 오염시키는 쪽이 되돌리기 어렵다
        assert KeywordModuleSettings.parse({}).dry_run is True

    def test_can_be_turned_off(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"dry_run": False}})
        assert cfg.dry_run is False

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"dry_run": False}})
        assert cfg.to_dict()["dry_run"] is False


class TestGateDryRun:
    """검증 모드에서는 DB 를 건드리지 않는다."""

    @pytest.mark.asyncio
    async def test_no_db_writes(self):
        calls = []
        gate = TitleGate(db=SimpleNamespace(add=lambda x: calls.append(x)),
                         user_id=1)
        gate._filters = []
        gate._matcher = None
        row = SimpleNamespace(keyword="전기기사", topic_id=3, subtopic_id=4)

        out = await gate.admit(["전기기사 실기 준비 기간"], row, dry_run=True)
        assert calls == [], "검증 모드인데 DB 에 추가했다"
        assert out["dry_run"] is True
        assert out["admitted"] == 0
        assert out["preview"][0]["state"] == "ready"

    @pytest.mark.asyncio
    async def test_blocked_title_is_reported(self):
        blocked = SimpleNamespace(filter_value="현금화", filter_type="keyword",
                                  target_type="title", is_active=True)
        gate = TitleGate(db=None, user_id=1)
        gate._filters = [blocked]
        gate._matcher = None
        row = SimpleNamespace(keyword="상품권", topic_id=1, subtopic_id=1)

        out = await gate.admit(["상품권 현금화 방법"], row, dry_run=True)
        assert out["blocked"] == 1
        assert out["preview"][0]["reason"] == "필터 차단"

    @pytest.mark.asyncio
    async def test_unclassified_is_reported(self):
        gate = TitleGate(db=None, user_id=1)
        gate._filters = []
        gate._matcher = None
        row = SimpleNamespace(keyword="무엇", topic_id=None, subtopic_id=None)

        out = await gate.admit(["분류 안 되는 제목입니다"], row, dry_run=True)
        assert out["queued"] == 1
        assert out["preview"][0]["state"] == "unclassified"


class TestTitleMakerRespectsDryRun:
    def test_does_not_mark_titled(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        # 검증 모드에서 소비 표시를 남기면 저장을 켰을 때 다시 못 만든다
        assert "if not cfg.dry_run:\n                row.titled = True" in src

    def test_cluster_status_not_advanced(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert "if not cfg.dry_run:\n                cluster.status" in src

    def test_form_exposes_toggle(self):
        js = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "formData.keyword.dry_run" in js
        serial = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "dry_run: !!k.dry_run" in serial


class TestSeedErrorIsActionable:
    def test_message_tells_what_to_do(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "시드 키워드를 입력하거나" in src
        assert "블로그를 연결" in src
