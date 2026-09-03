"""제목 수정 팝업 회귀 테스트.

**카테고리만 바꾸면 오분류가 반복된다.** 그 제목을 잘못 분류한 키워드가
그대로 남아 다음에 또 같은 곳으로 간다. 그래서 제목·주제·하위주제·키워드를
한자리에서 고친다.

여기서 만든 니치는 카테고리 관리와 **같은 API** 를 쓰므로 그쪽에도 바로
보이고, 임시제목 탭의 재분류가 바뀐 분류표로 다시 분류한다.

계획서: docs/plans/title_tab_workplan.md §9
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
TPL = BASE / "app/templates/collection/_title_edit.html"
LIST = BASE / "app/templates/collection/_titles.html"
INDEX = BASE / "app/templates/collection/index.html"


class TestInlineEditRemoved:
    def test_double_click_edit_is_gone(self):
        """제목만 고치면 오분류 원인이 남는다."""
        src = LIST.read_text(encoding="utf-8")
        assert "dblclick" not in src
        assert "더블클릭하여 수정" not in src

    def test_dead_handlers_removed(self):
        src = INDEX.read_text(encoding="utf-8")
        for gone in ("startEditTitle", "saveEditTitle", "cancelEditTitle",
                     "editingTitleId", "editingTitleValue"):
            assert gone not in src, gone

    def test_edit_button_in_actions(self):
        src = LIST.read_text(encoding="utf-8")
        assert "$dispatch('edit-title', title)" in src
        # PC 테이블과 모바일 카드 양쪽
        assert src.count("$dispatch('edit-title', title)") >= 2


class TestPopupCoversWholeNiche:
    def test_included(self):
        assert "_title_edit.html" in INDEX.read_text(encoding="utf-8")

    def test_edits_title_and_niche(self):
        src = TPL.read_text(encoding="utf-8")
        assert 'x-model="form.title"' in src
        assert 'x-model.number="form.topic_id"' in src
        assert 'x-model.number="form.subtopic_id"' in src

    def test_can_create_new_niche(self):
        """기존 분류에 없는 니치를 새로 만들어야 하는 경우가 있다."""
        src = TPL.read_text(encoding="utf-8")
        for fn in ("createTopic()", "createSubtopic()", "createKeyword()"):
            assert fn in src, fn

    def test_uses_category_management_api(self):
        """같은 API 를 써야 카테고리 관리에도 그대로 보인다."""
        src = TPL.read_text(encoding="utf-8")
        assert "/api/v1/categories/topics" in src
        assert "/api/v1/categories/subtopics" in src
        assert "/api/v1/categories/keywords" in src

    def test_keyword_can_be_edited_and_removed(self):
        """오분류의 원인은 대개 범위가 넓은 키워드다."""
        src = TPL.read_text(encoding="utf-8")
        assert "renameKeyword(k)" in src and "removeKeyword(k)" in src

    def test_explains_combo_rule(self):
        src = TPL.read_text(encoding="utf-8")
        assert "A+B" in src and "둘 다" in src

    def test_shows_why_classified(self):
        """어떤 키워드에 걸렸는지 알아야 원인을 고칠 수 있다."""
        src = TPL.read_text(encoding="utf-8")
        assert "matchedKeyword" in src

    def test_refreshes_list_after_save(self):
        src = TPL.read_text(encoding="utf-8")
        assert "titles-changed" in src


class TestApiSupportsNicheEdit:
    def test_update_schema_has_niche_fields(self):
        from app.routers.data_titles import TempTitleUpdate

        fields = TempTitleUpdate.model_fields
        for name in ("title", "topic_id", "subtopic_id",
                     "matched_keyword_id"):
            assert name in fields, name

    def test_zero_means_clear(self):
        """None 은 '안 바꿈' 이다. 미분류로 되돌리려면 0 이 필요하다."""
        src = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert "title_obj.topic_id = data.topic_id or None" in src
        assert 'x-model' not in src  # 서버 코드에 템플릿 조각이 섞이지 않게

    def test_status_follows_topic(self):
        """분류됐는데 status 가 new 로 남으면 목록 필터가 어긋난다."""
        src = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert '"categorized" if data.topic_id else "new"' in src

    def test_list_exposes_matched_keyword(self):
        from app.routers.data_titles import TempTitleResponse

        assert "matched_keyword" in TempTitleResponse.model_fields


class TestCandidateInput:
    def test_term_is_editable_and_visible(self):
        """'검사' 를 '난임+검사' 로 좁히는 것이 흔한 경우다."""
        src = (BASE / "app/templates/collection/_niche_suggest.html").read_text(
            encoding="utf-8")
        assert 'x-model="row.term"' in src
        # 입력칸처럼 보여야 사람이 고칠 생각을 한다
        assert "border-2 border-gray-300" in src
        assert 'placeholder="예: 난임+검사"' in src
