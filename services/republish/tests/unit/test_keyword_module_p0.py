"""키워드 모듈 P0 — 3경로 연결·플래그 분리·블로그별 격리 회귀 테스트.

배경(docs/plans/keyword_management_review.md):
    D-1 모듈 저장이 미선언 변수 참조로 죽었다
    D-2 오토런이 없는 속성(flow.flow_blogs)을 읽어 항상 실패했다
    D-3 플로우 실행 경로에 keyword 분기가 없었다
    D-4 promoted 한 칸을 겸용해 상위 키워드가 제목 대상에서 빠졌다
    D-6 유일성이 사용자 전역이라 두 번째 블로그부터 0건이 됐다
"""
import re
from pathlib import Path

import pytest

from app.models.keyword_candidate import KeywordCandidate
from app.services.keyword_lab.runner import KeywordModuleRunner

BASE = Path(__file__).resolve().parents[2]


class TestFlagSeparation:
    """D-4 — promoted(시드로 씀) 와 titled(제목 만듦) 는 다른 칸이다."""

    def test_titled_column_exists(self):
        assert "titled" in KeywordCandidate.__table__.columns

    def test_promoted_and_titled_are_distinct(self):
        cols = KeywordCandidate.__table__.columns
        assert cols["promoted"].name != cols["titled"].name

    def test_title_maker_targets_titled_flag(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        # 대상 선정은 titled 로, promoted 로 거르면 시드로 쓴 키워드가 빠진다
        assert "KeywordCandidate.titled.is_(False)" in src
        assert "KeywordCandidate.promoted.is_(False)" not in src
        assert "row.titled = True" in src

    def test_expander_still_marks_promoted(self):
        src = (BASE / "app/services/keyword_lab/expander.py").read_text(
            encoding="utf-8")
        assert "row.promoted = True" in src


class TestBlogScopedUniqueness:
    """D-6 — 후보 유일성은 블로그별이다."""

    def test_unique_constraint_includes_blog_id(self):
        uniques = [
            c for c in KeywordCandidate.__table__.constraints
            if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert uniques, "유니크 제약이 없다"
        cols = {col.name for col in uniques[0].columns}
        assert cols == {"user_id", "blog_id", "keyword"}

    def test_existing_keywords_filters_by_blog(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "async def _existing_keywords(self, blog_id" in src
        assert "KeywordCandidate.blog_id == blog_id" in src


class TestAggregate:
    """여러 블로그 결과를 하나로 합친다."""

    def test_all_success(self):
        rows = [
            ("A", {"success": True, "collect": {"saved": 10},
                   "measure": {"measured": 5}, "classify": {"matched": 9}}),
            ("B", {"success": True, "collect": {"saved": 4},
                   "measure": {"measured": 2}, "classify": {"matched": 3}}),
        ]
        out = KeywordModuleRunner._aggregate(rows)
        assert out["success"] is True
        assert (out["collected"], out["measured"],
                out["classified"]) == (14, 7, 12)
        assert out["blogs"] == 2 and out["ok"] == 2

    def test_skipped_is_not_failure(self):
        rows = [("A", {"success": True, "skipped": True, "message": "재고 충분"})]
        out = KeywordModuleRunner._aggregate(rows)
        assert out["success"] is True
        assert out["skipped_count"] == 1
        assert out["details"][0]["status"] == "skipped"

    def test_partial_failure_still_success(self):
        rows = [
            ("A", {"success": False, "error": "키 없음"}),
            ("B", {"success": True, "collect": {"saved": 3},
                   "measure": {}, "titles": {}}),
        ]
        out = KeywordModuleRunner._aggregate(rows)
        assert out["success"] is True
        assert out["failed"] == 1 and out["ok"] == 1
        assert out["errors"] == ["키 없음"]

    def test_all_failed_is_failure(self):
        rows = [("A", {"success": False, "error": "키 없음"})]
        out = KeywordModuleRunner._aggregate(rows)
        assert out["success"] is False
        assert out["error"] == "키 없음"

    def test_none_result_counts_as_failure(self):
        out = KeywordModuleRunner._aggregate([("A", None)])
        assert out["success"] is False


class TestExecutionPaths:
    """D-2 / D-3 — 3경로가 모두 같은 실행기를 부른다."""

    def test_scheduler_uses_blog_links_not_flow_blogs(self):
        src = (BASE / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        # Flow 모델에 flow_blogs 속성은 없다(관계명은 blog_links)
        assert "flow.flow_blogs" not in src
        assert "run_for_blogs" in src

    def test_flows_execute_has_keyword_branch(self):
        src = (BASE / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        assert 'elif type_code == "keyword":' in src          # 단일 모듈 실행
        assert 'if "keyword" in modules_by_type:' in src      # 플로우 전체 실행
        assert "async def _execute_keyword_module(" in src

    def test_runner_exposes_multi_blog_entry(self):
        assert hasattr(KeywordModuleRunner, "run_for_blogs")
        assert hasattr(KeywordModuleRunner, "run")


class TestModuleFormSerialization:
    """D-1 — 모듈 저장이 미선언 변수 참조로 죽지 않는다."""

    def test_keyword_branch_assigns_to_data_settings(self):
        src = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        start = src.index("prepareRequestData()")
        branch = src.index("type_code === 'keyword'", start)
        body = src[branch:branch + 1600]
        assert "data.settings = {" in body
        # 선언 없는 지역 변수 settings 에 대입하면 ReferenceError 가 난다
        assert not re.search(r"(?<!\.)\bsettings\.(keyword|schedule)\s*=", body)
