"""스타일별 재조합 회귀 테스트.

운영에서 다섯 스타일이 거의 같은 제목으로 수렴했다. 원인 두 가지:

1. 스타일 설명이 **분위기**였다("감성적이고 따뜻한"). AI 가 형태로
   옮기지 못해 전부 비슷해졌다.
2. 스타일마다 따로 호출해 **서로를 몰랐다.** 같은 프롬프트에 한 줄만
   바뀌니 같은 답이 나왔다.

추가 지시사항 칸에 스타일별 지시를 다 넣으면 **모든 호출에 다섯 개가 전부
들어간다** — 실제로 그래서 모든 스타일에 '당신' 과 의문형이 섞였다.

계획서: docs/plans/title_tab_workplan.md §4-5
"""
from pathlib import Path

from app.services.generation import title_style_batch as batch
from app.services.generation.title_recombiner import (
    STYLE_PROMPTS, build_base_prompt, style_instruction,
)

BASE = Path(__file__).resolve().parents[2]


class TestStyleInstructions:
    def test_defaults_describe_form_not_mood(self):
        """'따뜻하게' 로는 AI 가 스타일을 구분하지 못한다."""
        assert "당신" in STYLE_PROMPTS["emotional"]
        assert "숫자" in STYLE_PROMPTS["practical"]
        assert "의문사" in STYLE_PROMPTS["question"]
        assert "명사로 끝낼 것" in STYLE_PROMPTS["minimal"]
        # 옛 추상 표현이 남아 있으면 안 된다
        assert "감성적이고 따뜻한" not in STYLE_PROMPTS["emotional"]

    def test_override_wins(self):
        assert style_instruction("minimal", {"minimal": "한 단어"}) == "한 단어"

    def test_blank_override_falls_back(self):
        """화면에서 지우면 기본값으로 돌아가야 한다."""
        assert style_instruction("minimal", {"minimal": "  "}) == \
            STYLE_PROMPTS["minimal"]

    def test_unknown_style_is_none(self):
        assert style_instruction(None) is None
        assert style_instruction("없는스타일") is None


class TestBasePromptShared:
    def test_no_style_text_in_base(self):
        """공통 본문에 스타일 지시가 섞이면 모든 스타일이 그것을 지킨다."""
        prompt = build_base_prompt("제목", None, None)
        for text in STYLE_PROMPTS.values():
            assert text not in prompt

    def test_keywords_included(self):
        prompt = build_base_prompt("제목", None, ["전기기사"])
        assert "전기기사" in prompt

    def test_extra_text_included(self):
        prompt = build_base_prompt("제목", "- 20자 이내", None)
        assert "20자 이내" in prompt


class TestBatchGeneration:
    STYLES = ["emotional", "minimal"]
    LABELS = {"emotional": "감성형", "minimal": "심플"}
    INST = {"emotional": "당신으로 부를 것", "minimal": "명사로 끝낼 것"}

    def test_prompt_demands_distinct_titles(self):
        """한 번에 물어야 서로 겹치지 않게 쓸 수 있다."""
        prompt = batch.build_prompt("본문", self.STYLES, self.LABELS,
                                    self.INST)
        assert "서로 뚜렷하게 달라야" in prompt
        assert "emotional" in prompt and "minimal" in prompt

    def test_prompt_prioritises_style(self):
        prompt = batch.build_prompt("본문", self.STYLES, self.LABELS,
                                    self.INST)
        assert "스타일을 우선" in prompt

    def test_parses_json_amid_prose(self):
        answer = ('설명 [{"style":"emotional","title":"A"},'
                  '{"style":"minimal","title":"B"}] 끝')
        assert batch.parse(answer, self.STYLES) == {"emotional": "A",
                                                    "minimal": "B"}

    def test_drops_unrequested_styles(self):
        """AI 가 코드를 지어내는 경우가 있다."""
        answer = '[{"style":"없음","title":"X"},{"style":"minimal","title":"B"}]'
        assert batch.parse(answer, self.STYLES) == {"minimal": "B"}

    def test_bad_answer_is_empty(self):
        assert batch.parse("그냥 텍스트", self.STYLES) == {}
        assert batch.parse("", self.STYLES) == {}
        assert batch.parse('{"not":"a list"}', self.STYLES) == {}

    def test_partial_is_incomplete(self):
        """일부만 오면 빈칸이 생긴다 — 개별 호출로 돌아가야 한다."""
        assert not batch.is_complete({"emotional": "A"}, self.STYLES)
        assert batch.is_complete({"emotional": "A", "minimal": "B"},
                                 self.STYLES)

    def test_falls_back_to_per_style(self):
        src = (BASE / "app/services/generation/title_recombiner.py").read_text(
            encoding="utf-8")
        assert "배치 실패 → 스타일별 개별 호출" in src
        assert "_batch_styles" in src


class TestFormWiring:
    FORM = BASE / "app/static/js/modules/prompt-form.js"
    TPL = BASE / "app/static/js/modules/prompt-form-template.js"

    def test_style_prompts_editable(self):
        tpl = self.TPL.read_text(encoding="utf-8")
        assert "titleRecombine.stylePrompts[style.value]" in tpl
        assert "promptModule.styleDefaults" in tpl

    def test_blank_values_not_saved(self):
        """저장해 두면 기본값으로 못 돌아간다."""
        src = self.FORM.read_text(encoding="utf-8")
        assert "style_prompts: Object.fromEntries(" in src
        assert ".filter(([, v]) => v && String(v).trim())" in src

    def test_loaded_from_settings(self):
        src = self.FORM.read_text(encoding="utf-8")
        assert "settings.title_recombine.style_prompts || {}" in src

    def test_warns_about_common_field(self):
        """추가 지시사항에 스타일별 내용을 적으면 전부 섞인다."""
        tpl = self.TPL.read_text(encoding="utf-8")
        assert "모든 스타일에 공통" in tpl
        assert "결과가 같아집니다" in tpl

    def test_defaults_match_server(self):
        """화면 placeholder 와 서버 기본값이 어긋나면 오해한다."""
        src = self.FORM.read_text(encoding="utf-8")
        for code in ("emotional", "practical", "question", "viral", "minimal"):
            head = STYLE_PROMPTS[code].split(".")[0][:12]
            assert head in src, code


class TestStyleTemplates:
    """블로그 성격마다 먹히는 제목 형태가 다르다."""

    def test_four_templates(self):
        from app.services.generation.style_templates import TEMPLATES

        assert len(TEMPLATES) == 4
        codes = {t["code"] for t in TEMPLATES}
        assert codes == {"trust", "review", "howto", "prep"}

    def test_every_template_covers_all_styles(self):
        from app.services.generation.style_templates import TEMPLATES
        from app.services.generation.title_recombiner import STYLE_PROMPTS

        for template in TEMPLATES:
            assert set(template["prompts"]) == set(STYLE_PROMPTS), \
                template["code"]

    def test_styles_touch_different_parts(self):
        """같은 자리를 건드리면 결과가 비슷해진다.

        minimal 은 문장 끝을, question 은 묻는 형태를 정한다. 다섯 지시가
        모두 '느낌' 만 말하면 같은 자리를 건드려 비슷한 제목이 나온다.
        """
        from app.services.generation.style_templates import TEMPLATES

        for template in TEMPLATES:
            prompts = template["prompts"]
            code = template["code"]
            assert "끝낼 것" in prompts["minimal"], code
            assert any(word in prompts["question"]
                       for word in ("시작", "묻는")), code
            # 다섯 지시가 서로 달라야 한다
            assert len(set(prompts.values())) == 5, code

    def test_trust_template_avoids_clickbait(self):
        """금융·건강에서 단정형 낚시는 애드센스 심사에도 불리하다."""
        from app.services.generation.style_templates import BY_CODE

        assert "단정하지 말 것" in BY_CODE["trust"]["prompts"]["viral"]

    def test_recommend_matches_real_blogs(self):
        """운영 블로그의 실제 니치로 확인한다."""
        from app.services.generation.style_templates import recommend

        assert recommend(["금융/대출"]) == "trust"
        assert recommend(["재테크/돈관리"]) == "trust"
        assert recommend(["여행/관광", "음식/레시피"]) == "review"
        assert recommend(["컴퓨터/IT", "AI/인공지능"]) == "howto"
        assert recommend(["취업/자격증"]) == "prep"

    def test_recommend_uses_majority(self):
        """여러 니치를 쓰는 블로그가 많다."""
        from app.services.generation.style_templates import recommend

        # 여행 2 · 금융 1 → 체험형
        assert recommend(["여행/관광", "음식/레시피", "금융/대출"]) == "review"

    def test_no_match_returns_none(self):
        """짐작해서 고르면 엉뚱한 지시가 들어간다."""
        from app.services.generation.style_templates import recommend

        assert recommend(["알 수 없는 주제"]) is None
        assert recommend([]) is None
        assert recommend([""]) is None

    def test_router_registered(self):
        from app.main import app

        paths = {r.path for r in app.routes}
        assert "/api/v1/recombine-templates" in paths
        assert "/api/v1/recombine-templates/recommend" in paths

    def test_id_parsing_is_defensive(self):
        from app.routers.style_templates import _parse_ids

        assert _parse_ids("1, 2,x,,3") == [1, 2, 3]
        assert _parse_ids(None) == []


class TestTemplateUi:
    FORM = BASE / "app/static/js/modules/prompt-form.js"
    TPL = BASE / "app/static/js/modules/prompt-form-template.js"

    def test_dropdown_and_recommend_button(self):
        tpl = self.TPL.read_text(encoding="utf-8")
        assert 'x-model="promptModule.styleTemplate"' in tpl
        assert "applyStyleTemplate()" in tpl
        assert "recommendStyleTemplate()" in tpl

    def test_apply_fills_all_fields(self):
        src = self.FORM.read_text(encoding="utf-8")
        assert "stylePrompts = { ...found.prompts }" in src

    def test_recommend_needs_blogs(self):
        src = self.FORM.read_text(encoding="utf-8")
        assert "블로그를 먼저 고르세요" in src

    def test_recommend_does_not_guess(self):
        """맞는 템플릿이 없으면 채우지 않는다."""
        src = self.FORM.read_text(encoding="utf-8")
        block = src[src.index("async recommendStyleTemplate()"):
                    src.index("// 프롬프트 모듈 유효성 검증")]
        assert "if (!d.code) {" in block

    def test_loaded_on_prompt_module(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "this.loadStyleTemplates()" in js


class TestTitleLength:
    """AI 는 글자수를 세지 못한다 — 우리가 센다."""

    def test_parse_range(self):
        from app.services.generation.title_length import parse_range

        assert parse_range({"min_length": 25, "max_length": 30}) == (25, 30)
        assert parse_range({}) == (0, 0)
        assert parse_range({"max_length": "x"}) == (0, 0)

    def test_swapped_range_is_fixed(self):
        """뒤집힌 채 두면 아무 제목도 통과하지 못한다."""
        from app.services.generation.title_length import parse_range

        assert parse_range({"min_length": 30, "max_length": 25}) == (25, 30)

    def test_instruction_none_when_unset(self):
        from app.services.generation.title_length import instruction

        assert instruction(0, 0) is None
        assert "25자 이상 30자 이내" in instruction(25, 30)

    def test_fits(self):
        from app.services.generation.title_length import fits

        assert fits("가" * 27, 25, 30)
        assert not fits("가" * 10, 25, 30)
        assert fits("가" * 10, 0, 0), "미설정이면 검사하지 않는다"

    def test_retry_hint_states_actual_length(self):
        """AI 는 자기가 쓴 제목이 몇 자인지 모른다. 숫자를 줘야 고친다."""
        from app.services.generation.title_length import retry_hint

        assert "35자" in retry_hint("가" * 35, 25, 30)
        assert "15자" in retry_hint("가" * 15, 25, 30)

    def test_length_goes_first_in_prompt(self):
        """뒤에 두면 스타일 지시에 묻힌다 — 실제로 그랬다."""
        from app.services.generation.title_recombiner import build_base_prompt

        prompt = build_base_prompt("제목", "- 부호 금지", None, (25, 30))
        assert prompt.index("25자 이상") < prompt.index("다음 블로그 제목을")

    def test_retry_wired(self):
        src = (BASE / "app/services/generation/title_recombiner.py").read_text(
            encoding="utf-8")
        assert "_fit_length" in src
        # 두 번은 하지 않는다 — 호출이 통제를 벗어난다
        block = src[src.index("async def _fit_length("):
                    src.index("async def _batch_styles(")]
        assert block.count("_fit_length") == 1

    def test_batch_drops_bad_lengths(self):
        """배치를 통째로 다시 부르면 맞았던 제목까지 바뀐다."""
        src = (BASE / "app/services/generation/title_recombiner.py").read_text(
            encoding="utf-8")
        assert "if fits_length(self._clean_title(title), low, high)" in src

    def test_form_has_length_inputs(self):
        tpl = (BASE / "app/static/js/modules/prompt-form-template.js").read_text(
            encoding="utf-8")
        js = (BASE / "app/static/js/modules/prompt-form.js").read_text(
            encoding="utf-8")
        assert "titleRecombine.minLength" in tpl
        assert "min_length: this.promptModule.titleRecombine.minLength" in js
        assert "AI는 글자수를 세지 못하므로" in tpl


class TestExampleLength:
    """AI 는 지시문보다 **예시**를 따라간다."""

    def test_template_examples_are_long_enough(self):
        import re

        from app.services.generation.style_templates import TEMPLATES

        for template in TEMPLATES:
            for code, text in template["prompts"].items():
                match = re.search(r"예: (.+)", text)
                assert match, (template["code"], code)
                assert len(match.group(1)) >= 20, (template["code"], code)

    def test_default_examples_are_long_enough(self):
        import re

        from app.services.generation.title_recombiner import STYLE_PROMPTS

        for code, text in STYLE_PROMPTS.items():
            match = re.search(r"예: (.+)", text)
            assert match and len(match.group(1)) >= 20, code

    def test_form_defaults_match_server(self):
        from app.services.generation.title_recombiner import STYLE_PROMPTS

        js = (BASE / "app/static/js/modules/prompt-form.js").read_text(
            encoding="utf-8")
        for code, text in STYLE_PROMPTS.items():
            assert text in js, code
