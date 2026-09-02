"""키워드 탭 후속 수정 회귀 테스트.

사용자 지적:
    1. 선택 삭제 버튼 스타일이 다른 탭과 달랐다
    2. 분류 버튼이 매번 같은 2,000건을 훑어 진행이 없었다
    3. 키워드 수집에 금지어 필터가 걸리지 않았다
"""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.keyword_candidate import KeywordCandidate
from app.services.keyword_lab.runner import KeywordModuleRunner
from app.services.keyword_lab.title_gate import (
    FILTER_TARGET_KEYWORD, blocking_filter,
)

BASE = Path(__file__).resolve().parents[2]


def _filter(value, target="keyword", kind="keyword"):
    return SimpleNamespace(filter_value=value, filter_type=kind,
                           target_type=target, is_active=True)


class TestDeleteButtonStyle:
    """같은 동작은 같은 스타일 — 임시제목·정식제목 탭을 승계한다."""

    def _tpl(self):
        return (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")

    def test_uses_shared_button_classes(self):
        tpl = self._tpl()
        assert ("inline-flex items-center px-3 py-1.5 bg-red-500 text-white "
                "rounded-lg text-sm font-medium hover:bg-red-600") in tpl

    def test_selection_badge_matches(self):
        tpl = self._tpl()
        assert "bg-accent/10 text-accent rounded-full text-sm font-medium" in tpl
        assert "개 선택" in tpl

    def test_clear_selection_button(self):
        assert "선택 해제" in self._tpl()

    def test_old_style_gone(self):
        assert 'class="ml-auto px-3 py-1.5 bg-red-600' not in self._tpl()


class TestKeywordFilter:
    """데이터 관리의 '필터설정' 이 키워드 수집에도 걸린다."""

    def test_keyword_target_applies(self):
        assert blocking_filter([_filter("현금화")], "상품권 현금화",
                               FILTER_TARGET_KEYWORD) is not None

    def test_title_only_filter_is_ignored(self):
        f = _filter("현금화", target="title")
        assert blocking_filter([f], "상품권 현금화",
                               FILTER_TARGET_KEYWORD) is None

    def test_both_applies_to_keyword(self):
        f = _filter("현금화", target="both")
        assert blocking_filter([f], "상품권 현금화",
                               FILTER_TARGET_KEYWORD) is not None

    def test_title_target_still_default(self):
        # 인자를 안 주면 예전처럼 제목 판정
        f = _filter("현금화", target="title")
        assert blocking_filter([f], "상품권 현금화") is not None

    def test_ingest_applies_filter(self):
        src = (BASE / "app/services/keyword_lab/ingest.py").read_text(
            encoding="utf-8")
        assert "blocking_filter(filters, idea.keyword" in src
        assert "FILTER_TARGET_KEYWORD" in src

    def test_ads_path_applies_filter(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "blocking_filter(filters, kw, FILTER_TARGET_KEYWORD)" in src

    def test_blocked_count_surfaces(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True,
            "collect": {"saved": 40, "blocked": 7},
            "measure": {}, "classify": {}, "titles": {}})])
        assert "금지어 차단 7건" in out["message"]
        assert out["blocked"] == 7

    def test_quiet_when_nothing_blocked(self):
        out = KeywordModuleRunner._aggregate([("-", {
            "success": True, "collect": {"saved": 5}, "measure": {},
            "titles": {}})])
        assert "금지어" not in out["message"]


class TestClassifyProgress:
    """분류기는 결정적이다 — 같은 건을 다시 훑으면 결과가 같다."""

    def test_column_added(self):
        assert "classify_tried_at" in KeywordCandidate.__table__.columns

    def test_migration_present(self):
        src = (BASE / "alembic/versions/064_add_classify_progress.py").read_text(
            encoding="utf-8")
        assert 'COLUMN = "classify_tried_at"' in src

    def test_picks_untried_only(self):
        src = (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")
        assert "KeywordCandidate.classify_tried_at.is_(None)" in src
        assert "order_by(KeywordCandidate.id)" in src

    def test_records_failures_too(self):
        src = (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")
        # 실패를 기록하지 않으면 다음에 또 같은 것을 훑는다
        assert "row.classify_tried_at = now" in src

    def test_retry_all_clears_marks(self):
        src = (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")
        assert "retry_all" in src
        assert "values(classify_tried_at=None)" in src

    def test_explains_when_nothing_left(self):
        src = (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")
        # "왜 안 줄어드는지" 를 말해 준다
        assert "이미 다 훑었습니다" in src
        assert "분류표에 없는 말입니다" in src

    def test_router_accepts_retry(self):
        src = (BASE / "app/routers/data_keyword_pool.py").read_text(
            encoding="utf-8")
        assert "retry_all: bool = Body(False)" in src

    def test_screen_has_retry_button(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        assert "runClassify(true)" in tpl
        assert "처음부터 다시 분류" in tpl

    def test_screen_reports_progress(self):
        js = (BASE / "app/static/js/collection/keyword_pool.js").read_text(
            encoding="utf-8")
        assert "아직 안 훑은" in js
        assert "카테고리 붙음" in js


class TestMeasureExplained:
    def test_two_steps_documented(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        assert "검색량 보강" in tpl and "공급 측정" in tpl
        # 더 많이 재는 방법을 화면이 알려 준다
        assert "최대 200건" in tpl and "반복해서" in tpl
