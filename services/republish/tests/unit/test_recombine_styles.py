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
