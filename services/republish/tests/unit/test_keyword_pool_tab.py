"""S2 — 데이터 관리 키워드 탭이 정본을 다룬다.

배경(docs/plans/keyword_pipeline_restructure_review.md §5-1):
    기존 탭은 seed_keywords 를 보여줬는데 그 테이블에는 지표 컬럼이 아예
    없어 "수집만 된 키워드를 기준값으로 분류" 가 불가능했다.
    정본(keyword_candidates)을 지표·판정과 함께 보여주고, 자동 모듈이
    하는 일을 사람이 **같은 코드로** 직접 돌릴 수 있게 한다.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.data_keyword_pool import SORTABLE, router
from app.services.keyword_lab import pool_ops

BASE = Path(__file__).resolve().parents[2]


class TestRoutes:
    def _paths(self):
        return {r.path for r in router.routes}

    @pytest.mark.parametrize("path", [
        "/data/keyword-pool",
        "/data/keyword-pool/stats",
        "/data/keyword-pool/classify",
        "/data/keyword-pool/rejudge",
        "/data/keyword-pool/measure",
        "/data/keyword-pool/task/{task_id}",
        "/data/keyword-pool/delete",
    ])
    def test_route_exists(self, path):
        assert path in self._paths()

    def test_registered_in_app(self):
        src = (BASE / "app/main.py").read_text(encoding="utf-8")
        assert "data_keyword_pool_router" in src

    def test_metrics_are_sortable(self):
        # 지표로 줄 세우지 못하면 분류 작업이 안 된다
        for key in ("search_volume", "monthly_pub_count", "saturation",
                    "verdict"):
            assert key in SORTABLE


class TestMeasureIsBackgrounded:
    """측정은 키워드당 검색 API 2회라 오래 걸린다."""

    def _src(self):
        return (BASE / "app/routers/data_keyword_pool.py").read_text(
            encoding="utf-8")

    def test_uses_task_token(self):
        src = self._src()
        assert "asyncio.create_task(_measure_in_background(" in src
        assert '"status": "running", "task_id": task_id' in src

    def test_own_session(self):
        # 요청 세션은 응답과 함께 닫힌다
        assert "db_manager.get_session()" in self._src()

    def test_failure_is_stored(self):
        assert '"status": "failed"' in self._src()


class TestDeleteGuard:
    def test_requires_a_target(self):
        # 대상 없이 전체 삭제되면 6천 건이 날아간다
        src = (BASE / "app/routers/data_keyword_pool.py").read_text(
            encoding="utf-8")
        assert 'if not ids and not verdict:' in src
        assert '"대상이 비어 있습니다"' in src


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar(self):
        return len(self.rows)


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    async def execute(self, *a, **k):
        return _Rows(self.rows)

    async def commit(self):
        self.committed = True


class TestRejudge:
    """기준값만 바꿔 다시 판정 — API 호출 없음."""

    def _row(self, keyword, volume, pub):
        return SimpleNamespace(
            keyword=keyword, search_volume=volume, doc_count=None,
            monthly_pub_count=pub, verdict="pending", verdict_reason=None,
            risk_label=None)

    @pytest.mark.asyncio
    async def test_applies_thresholds(self):
        rows = [self._row("전기기사", 5000, 20),      # 통과
                self._row("맛집", 500000, 10),        # 상한 초과
                self._row("희귀어", 10, 1)]           # 하한 미달
        db = _Db(rows)
        out = await pool_ops.rejudge(db, 1, min_volume=100,
                                     max_volume=100000, min_saturation=0.2)
        assert out["total"] == 3
        assert out["by_verdict"]["adopt"] == 1
        assert out["by_verdict"]["reject"] == 2
        assert db.committed

    @pytest.mark.asyncio
    async def test_returns_thresholds_used(self):
        out = await pool_ops.rejudge(_Db([]), 1, 300, 50000, 0.5)
        assert out["thresholds"] == {"min_volume": 300, "max_volume": 50000,
                                     "min_saturation": 0.5}


class TestPoolOpsShape:
    def _src(self):
        return (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")

    def test_measure_enriches_volume_first(self):
        # 이관된 옛 시드는 검색량조차 없다
        src = self._src()
        assert "_enrich_volumes" in src
        assert "enrich_volumes" in src

    def test_measure_reuses_module_service(self):
        # 사람이 돌리든 모듈이 돌리든 같은 코드여야 한다
        assert "KeywordLabService" in self._src()

    def test_classify_makes_no_api_call(self):
        src = self._src()
        assert "CategoryMatcherService" in src
        assert "API 를 부르지 않는다" in src


class TestScreen:
    def test_pool_view_included_first(self):
        html = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "collection/_keyword_pool.html" in html
        # 기존 시드 목록은 전환기 동안 접어서 남긴다
        assert "기존 시드 키워드 목록" in html
        assert html.index("_keyword_pool.html") < html.index("_keywords.html")

    def test_script_loaded(self):
        html = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "collection/keyword_pool.js" in html

    def test_three_actions_present(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        for action in ("runClassify()", "runMeasure()", "runRejudge()"):
            assert action in tpl

    def test_metrics_columns_shown(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        for col in ("search_volume", "monthly_pub_count", "saturation",
                    "verdict"):
            assert col in tpl

    def test_polls_instead_of_holding_request(self):
        js = (BASE / "app/static/js/collection/keyword_pool.js").read_text(
            encoding="utf-8")
        assert "keyword-pool/task/${taskId}" in js
        assert "서버가 빈 응답을 돌려줬습니다" in js

    @pytest.mark.parametrize("path", [
        "app/routers/data_keyword_pool.py",
        "app/services/keyword_lab/pool_ops.py",
        "app/static/js/collection/keyword_pool.js",
        "app/templates/collection/_keyword_pool.html",
    ])
    def test_files_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
