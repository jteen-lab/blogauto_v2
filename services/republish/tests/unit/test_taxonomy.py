"""분류표 관리(W12·W14~W16) 회귀 테스트.

**미분류는 쓰레기가 아니라 분류표의 구멍 목록이다.** 분류 매칭이 문자열
포함 검사라, 등록된 키워드 896개에 없는 말은 무조건 미분류가 된다.

분류표를 잘못 바꾸면 재고 전체의 분류가 틀어지므로 plan/apply/rollback 을
고정한다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from pathlib import Path

import pytest

from app.services.taxonomy import ai_suggest, changes

BASE = Path(__file__).resolve().parents[2]


class TestChangeValidation:
    def test_unknown_op_dropped(self):
        assert changes.normalize([{"op": "drop_table", "term": "x"}]) == []

    def test_add_requires_subtopic(self):
        assert changes.normalize([{"op": "add_keyword", "term": "a"}]) == []

    def test_remove_requires_keyword_id(self):
        assert changes.normalize([{"op": "remove_keyword", "term": "a"}]) == []

    def test_numeric_string_is_accepted(self):
        out = changes.normalize(
            [{"op": "add_keyword", "term": "실비보험", "subtopic_id": "3"}])
        assert out == [{"op": "add_keyword", "term": "실비보험",
                        "subtopic_id": 3}]

    def test_empty_term_dropped(self):
        assert changes.normalize(
            [{"op": "add_keyword", "term": "  ", "subtopic_id": 1}]) == []

    def test_non_dict_ignored(self):
        assert changes.normalize(["문자열", None, 42]) == []

    def test_batch_is_capped(self):
        """실수 하나가 통째로 번지는 것을 막는다."""
        items = [{"op": "add_keyword", "term": f"t{i}", "subtopic_id": 1}
                 for i in range(changes.MAX_OPS + 50)]
        assert len(changes.normalize(items)) == changes.MAX_OPS

    def test_only_category_ops_are_open(self):
        """1차 범위는 카테고리뿐. 전체 설정을 한 번에 열지 않는다."""
        assert set(changes.OPERATIONS) == {"add_keyword", "remove_keyword"}


class TestAiSuggest:
    def test_parses_json_amid_prose(self):
        answer = ('설명입니다 [{"term":"실비보험","subtopic_id":3,'
                  '"confidence":0.9,"reason":"보험"}] 끝')
        out = ai_suggest.parse(answer)
        assert out[0]["term"] == "실비보험" and out[0]["subtopic_id"] == 3

    def test_bad_answer_is_empty(self):
        assert ai_suggest.parse("설명만 있음") == []
        assert ai_suggest.parse("") == []
        assert ai_suggest.parse('{"not": "a list"}') == []

    def test_confidence_clamped(self):
        out = ai_suggest.parse('[{"term":"a","subtopic_id":1,"confidence":9}]')
        assert out[0]["confidence"] == 1.0

    def test_low_confidence_is_held(self):
        """승인 목록이 지저분하면 사람이 대충 승인하게 된다."""
        result = ai_suggest.split(
            [{"term": "a", "subtopic_id": 1, "confidence": 0.3}])
        assert result["approved"] == [] and len(result["held"]) == 1

    def test_no_place_is_held(self):
        """자리를 못 찾았으면 억지로 넣지 않는다."""
        result = ai_suggest.split(
            [{"term": "a", "subtopic_id": None, "confidence": 0.99}])
        assert result["approved"] == []

    @pytest.mark.asyncio
    async def test_no_ai_returns_empty(self):
        out = await ai_suggest.AiTaxonomySuggester(None).run([{"term": "a"}],
                                                             [])
        assert out["approved"] == [] and out["error"]

    @pytest.mark.asyncio
    async def test_hallucinated_terms_are_dropped(self):
        """후보에 없던 말을 AI 가 지어내는 경우가 있다."""
        async def ask(prompt):
            return ('[{"term":"지어낸말","subtopic_id":1,"confidence":0.9},'
                    '{"term":"실비보험","subtopic_id":2,"confidence":0.9}]')

        out = await ai_suggest.AiTaxonomySuggester(ask).run(
            [{"term": "실비보험", "count": 100}], [])
        assert [r["term"] for r in out["approved"]] == ["실비보험"]

    @pytest.mark.asyncio
    async def test_ai_failure_is_contained(self):
        async def boom(prompt):
            raise RuntimeError("한도 초과")

        out = await ai_suggest.AiTaxonomySuggester(boom).run(
            [{"term": "a"}], [])
        assert out["approved"] == [] and "한도" in out["error"]

    def test_prompt_allows_null_placement(self):
        prompt = ai_suggest.build_prompt(
            [{"term": "a", "count": 1, "samples": []}],
            [{"id": 1, "name": "주제", "subtopics": [
                {"id": 2, "name": "하위", "keywords": []}]}])
        assert "null" in prompt and "억지로" in prompt


class TestSuggestRules:
    def test_thresholds(self):
        from app.services.taxonomy import suggest as s

        assert s.MIN_COUNT >= 50, "적게 나오는 말은 노이즈다"
        assert s.DEFAULT_TOP <= 50, "한 화면에서 처리할 수 있어야 한다"

    def test_no_ai_dependency(self):
        """규칙 기반 추천은 AI 없이 돌아야 한다 — 비용 0, 선행조건 없음."""
        src = (BASE / "app/services/taxonomy/suggest.py").read_text(
            encoding="utf-8")
        assert "AIService" not in src and "anthropic" not in src


class TestSafety:
    def test_plan_does_not_mutate(self):
        """plan 은 계산만 한다. 이걸 어기면 미리보기가 의미를 잃는다."""
        src = (BASE / "app/services/taxonomy/changes.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def plan("):src.index("async def apply(")]
        assert "db.add(Keyword" not in block
        assert "is_deleted = True" not in block

    def test_apply_records_snapshot(self):
        src = (BASE / "app/services/taxonomy/changes.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def apply("):
                    src.index("async def rollback(")]
        assert "row.snapshot" in block

    def test_rollback_is_soft(self):
        """하드 삭제하면 그 사이 분류된 제목이 깨진다."""
        src = (BASE / "app/services/taxonomy/changes.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def rollback("):]
        assert "db.delete" not in block

    def test_actor_is_recorded(self):
        """누가 바꿨는지 남아야 한다 — 화면·에이전트·스크립트."""
        from app.models.taxonomy_change import ACTORS

        assert set(ACTORS) == {"ui", "agent", "script"}

    def test_router_registered(self):
        from app.main import app

        paths = {r.path for r in app.routes}
        for path in ("/api/v1/admin/taxonomy",
                     "/api/v1/admin/taxonomy/plan",
                     "/api/v1/admin/taxonomy/suggest",
                     "/api/v1/admin/taxonomy/history"):
            assert path in paths, path

    def test_no_cli_embedded(self):
        """운영 서버에 개발 도구를 내장하지 않는다(계획서 §9-5 B안 배제)."""
        src = (BASE / "app/services/taxonomy/ai_suggest.py").read_text(
            encoding="utf-8")
        assert "subprocess" not in src and "claude -p" not in src


class TestUiWiring:
    def test_suggest_panel_included(self):
        src = (BASE / "app/templates/collection/_titles.html").read_text(
            encoding="utf-8")
        assert "_niche_suggest.html" in src

    def test_plan_before_apply_in_ui(self):
        """화면도 plan → 확인 → apply 를 지켜야 한다."""
        tpl = (BASE / "app/templates/collection/_niche_suggest.html").read_text(
            encoding="utf-8")
        plan_at = tpl.index("taxonomy/plan")
        apply_at = tpl.index("taxonomy/apply")
        assert plan_at < apply_at
        assert "confirm(" in tpl, "회수 예상 건수를 보여 주고 확인받는다"

    def test_ai_suggestion_is_not_auto_applied(self):
        """AI 제안은 목록에 채우기만 한다. 적용은 사람이 누른다."""
        tpl = (BASE / "app/templates/collection/_niche_suggest.html").read_text(
            encoding="utf-8")
        block = tpl[tpl.index("async askAi()"):tpl.index("async get(url)")]
        assert "taxonomy/apply" not in block

    def test_niche_mode_defaults_to_mark(self):
        """W17 — 차단은 분류표를 채운 뒤에 켠다."""
        js = (BASE / "app/static/js/collection/title_workbench.js").read_text(
            encoding="utf-8")
        assert "niche_mode: 'mark'" in js
        tpl = (BASE
               / "app/templates/collection/_title_workbench.html").read_text(
            encoding="utf-8")
        assert 'x-model="collect.niche_mode"' in tpl
        assert "니치 추천으로 분류표를 채운 뒤" in tpl
