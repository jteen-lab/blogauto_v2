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
        assert "saveKeyword(k)" in src and "removeKeyword(k)" in src

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


class TestNicheCrudInPopup:
    """기존 항목도 고치고 지울 수 있어야 한다."""

    def test_topic_can_be_renamed_and_deleted(self):
        src = TPL.read_text(encoding="utf-8")
        assert "renameTopic()" in src and "deleteTopic()" in src

    def test_subtopic_can_be_renamed_and_deleted(self):
        src = TPL.read_text(encoding="utf-8")
        assert "renameSubtopic()" in src and "deleteSubtopic()" in src

    def test_keyword_attributes_editable(self):
        """우선순위·난이도가 없으면 매칭 순서를 조정할 수 없다."""
        src = TPL.read_text(encoding="utf-8")
        for field in ("k.priority", "k.difficulty", "k.search_volume"):
            assert field in src, field
        assert "saveKeyword(k)" in src

    def test_priority_meaning_is_explained(self):
        """낮을수록 먼저 매칭된다 — 반대로 알면 잘못 설정한다."""
        assert "낮을수록 먼저 매칭" in TPL.read_text(encoding="utf-8")

    def test_delete_warns_about_reclassify(self):
        src = TPL.read_text(encoding="utf-8")
        assert "미분류로 돌아갑니다" in src

    def test_uses_category_crud_endpoints(self):
        src = TPL.read_text(encoding="utf-8")
        assert "/api/v1/categories/topics/${current.id}" in src
        assert "/api/v1/categories/subtopics/${current.id}" in src
        assert "/api/v1/categories/keywords/${row.id}" in src


class TestDomainDeletionCounting:
    """도메인 정리 확인이 안 뜨던 원인 — 개별 삭제를 세지 않았다."""

    def test_single_delete_counts(self):
        """이 기능이 필요한 사람이 바로 하나씩 지우던 사람이다."""
        src = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        block = src[src.index('@router.delete("/temp/{title_id}")'):]
        assert "record_deletions" in block
        assert "domain_hits" in block

    def test_single_delete_passes_threshold(self):
        src = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "?domain_threshold=${this.domainDeleteThreshold}" in src

    def test_single_delete_opens_popup(self):
        src = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        # 일괄·개별 양쪽에서 팝업이 열려야 한다
        assert src.count("new CustomEvent('domain-purge'") >= 2

    def test_domain_filter_exists(self):
        """같은 도메인 제목이 여러 페이지에 흩어지면 모아 지울 수 없다."""
        api = (BASE / "app/routers/data_titles.py").read_text(encoding="utf-8")
        tpl = (BASE / "app/templates/collection/_titles.html").read_text(
            encoding="utf-8")
        js = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert 'domain: Optional[str] = Query(' in api
        assert "filterByDomain(title.domain)" in tpl
        assert "params.append('domain', this.titleDomain)" in js

    def test_list_exposes_domain(self):
        from app.routers.data_titles import TempTitleResponse

        assert "domain" in TempTitleResponse.model_fields


class TestKeywordSchemaAcceptsExisting:
    """기존 데이터를 거부하면 이름조차 고칠 수 없다(422)."""

    def test_zero_difficulty_is_allowed(self):
        """운영 키워드 383개가 difficulty=0 이다."""
        from app.schemas.category import KeywordUpdateRequest

        row = KeywordUpdateRequest(name="검사", difficulty=0, priority=5)
        assert row.difficulty == 0

    def test_zero_difficulty_on_create(self):
        from app.schemas.category import KeywordCreateRequest

        row = KeywordCreateRequest(subtopic_id=1, name="검사", difficulty=0)
        assert row.difficulty == 0

    def test_range_still_enforced(self):
        import pytest as _pytest
        from pydantic import ValidationError

        from app.schemas.category import KeywordUpdateRequest

        with _pytest.raises(ValidationError):
            KeywordUpdateRequest(name="x", difficulty=11)

    def test_client_sends_zero_not_one(self):
        """`?? 1` 로 올리면 0 인 값이 조용히 1 로 바뀐다."""
        src = TPL.read_text(encoding="utf-8")
        assert "difficulty: row.difficulty ?? 0" in src


class TestNewKeywordForm:
    """새 키워드도 속성을 함께 받는다."""

    def test_inline_form_replaces_prompt(self):
        src = TPL.read_text(encoding="utf-8")
        assert "prompt('새 키워드" not in src
        assert 'x-model="newKw.name"' in src

    def test_form_has_attributes(self):
        src = TPL.read_text(encoding="utf-8")
        for field in ("newKw.priority", "newKw.difficulty",
                      "newKw.search_volume"):
            assert field in src, field

    def test_create_sends_attributes(self):
        src = TPL.read_text(encoding="utf-8")
        block = src[src.index("async createKeyword()"):
                    src.index("async saveKeyword(row)")]
        assert "priority: this.newKw.priority" in block
        assert "difficulty: this.newKw.difficulty" in block
        assert "search_volume: this.newKw.search_volume" in block


class TestRecombinePanelWiring:
    """드롭다운이 비고, 대상이 무작위로 보이던 자리."""

    PANEL = BASE / "app/templates/collection/_recombine_panel.html"

    def test_queries_prompt_modules(self):
        """재조합 프롬프트는 prompt 타입 모듈의 설정에 있다.

        'generate' 타입으로 물으면 운영에 0개라 목록이 빈다.
        """
        src = self.PANEL.read_text(encoding="utf-8")
        assert "module_type_code=prompt" in src
        assert "type=generate" not in src

    def test_reads_correct_response_key(self):
        """응답 키는 modules 다. items 를 읽으면 항상 빈다."""
        from app.schemas.module import ModuleListResponse

        assert "modules" in ModuleListResponse.model_fields
        assert "items" not in ModuleListResponse.model_fields
        src = self.PANEL.read_text(encoding="utf-8")
        assert "d.modules" in src

    def test_marks_disabled_modules(self):
        """재조합이 꺼진 모듈을 고르면 원본이 그대로 돌아온다."""
        src = self.PANEL.read_text(encoding="utf-8")
        assert "title_recombine?.enabled" in src
        assert "재조합 꺼짐" in src

    def test_uses_checked_titles_not_random(self):
        """대상은 목록에서 체크한 제목이다. 무작위가 아니다."""
        src = self.PANEL.read_text(encoding="utf-8")
        assert "const rows = this.selectedMainTitles;" in src
        # 내부 API 를 뒤지면 버전이 바뀔 때 조용히 빈 배열이 된다.
        # 주석에는 남아 있으므로 실제 접근만 본다.
        assert "node._x_dataStack" not in src

    def test_explains_selection_to_user(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert "무작위로 고르지 않습니다" in src

    def test_warns_when_no_module(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert "프롬프트 모듈이 없습니다" in src


class TestRecombineNeedsProvider:
    """0건만 뜨던 원인 — AI 제공자가 없으면 원본이 그대로 돌아온다."""

    PANEL = BASE / "app/templates/collection/_recombine_panel.html"
    SERVICE = BASE / "app/services/recombine/service.py"

    def test_panel_has_ai_selector(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert 'x-model="provider"' in src
        assert "modelsFor(provider)" in src

    def test_provider_is_sent(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert "provider: this.provider || null" in src

    def test_service_falls_back_to_active_key(self):
        """화면에서 안 골랐다고 조용히 0건을 돌려주면 안 된다."""
        src = self.SERVICE.read_text(encoding="utf-8")
        assert "_default_provider" in src
        assert 'AIApiKey.status == "active"' in src

    def test_no_provider_reports_reason(self):
        src = self.SERVICE.read_text(encoding="utf-8")
        assert "등록된 활성 AI 키가 없습니다" in src

    def test_unchanged_title_reports_reason(self):
        """재조합기는 실패해도 예외 대신 원본을 돌려준다."""
        src = self.SERVICE.read_text(encoding="utf-8")
        assert "제목이 바뀌지 않았습니다" in src

    def test_error_shown_in_panel(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert 'x-show="result.error"' in src


class TestKeywordInventoryRemoved:
    def test_min_inventory_gone_from_form(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "min_inventory" not in tpl
        assert "재고 하한" not in tpl

    def test_not_serialized(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "min_inventory" not in js


class TestRecombineExplainsZero:
    """0건인데 사유가 안 보이던 자리 — 실제로 두 번 겪었다."""

    SERVICE = BASE / "app/services/recombine/service.py"
    PANEL = BASE / "app/templates/collection/_recombine_panel.html"

    def test_reasons_counted(self):
        src = self.SERVICE.read_text(encoding="utf-8")
        assert "self.reasons" in src and "_count(" in src

    def test_not_stale_is_counted(self):
        """최신성 모드는 낡은 제목만 손본다. 그 사실을 말해야 한다."""
        src = self.SERVICE.read_text(encoding="utf-8")
        block = src[src.index("if freshness:"):src.index("if self.recombiner is None")]
        assert '_count("not_stale")' in block

    def test_every_none_path_counts(self):
        """사유 없이 None 을 돌려주면 화면이 아무것도 못 말한다."""
        src = self.SERVICE.read_text(encoding="utf-8")
        for reason in ("not_stale", "already", "duplicate", "no_ai",
                       "ai_error", "unchanged"):
            assert f'_count("{reason}")' in src, reason

    def test_explain_reads_naturally(self):
        from app.services.recombine.service import _explain

        text = _explain({"not_stale": 5}, 5)
        assert "5건 중" in text and "낡지 않아" in text
        assert _explain({}, 0) is None

    def test_error_filled_when_nothing_made(self):
        src = self.SERVICE.read_text(encoding="utf-8")
        assert "_explain(self.reasons, len(rows)) if not made else None" in src

    def test_panel_warns_about_freshness_mode(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert "낡지 않은 제목은 건너뜁니다" in src

    def test_panel_shows_fallback_message(self):
        src = self.PANEL.read_text(encoding="utf-8")
        assert '!result.made && !result.error' in src


class TestPromptTestUsesModuleSettings:
    """모듈 테스트는 모듈에 설정된 값으로 돌아야 한다.

    수동 화면처럼 매번 고르게 하면, 이미 설정된 값을 다시 입력하는 셈이고
    안 골랐을 때 원인을 알기 어렵다.
    """

    JS = BASE / "app/static/js/modules/prompt-test.js"
    TESTER = BASE / "app/services/generation/pipeline_tester.py"

    def test_blog_defaults_to_module_setting(self):
        src = self.JS.read_text(encoding="utf-8")
        block = src[src.index("getTestBlogId() {"):
                    src.index("async previewRenewal()")]
        assert "this.getSelectedBlogOptions()" in block
        assert "this.promptTest.testBlogId = options[0].id" in block

    def test_error_points_at_module_settings(self):
        """'블로그를 선택하세요' 는 어디서 고르라는 건지 알 수 없다."""
        src = self.JS.read_text(encoding="utf-8")
        assert "모듈에 블로그가 연결돼 있지 않습니다" in src

    def test_tester_falls_back_for_ai(self):
        """블로그에 제목 AI 가 없으면 재조합기가 원본을 그대로 돌려준다."""
        src = self.TESTER.read_text(encoding="utf-8")
        assert "writing_ai.get(\"provider\")" in src
        assert "resolve_provider(self.db, self.user_id, None)" in src

    def test_provider_source_is_reported(self):
        """어디서 온 AI 인지 알아야 설정이 맞는지 확인할 수 있다."""
        src = self.TESTER.read_text(encoding="utf-8")
        for source in ("blog_title_ai", "blog_writing_ai", "active_key",
                       "none"):
            assert f'prov_src = "{source}"' in src, source
