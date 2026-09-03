"""모듈 관리 표 전환 — 기능 보존 (2026-08-31).

**절대 규칙: 표시 방식만 바꾸고 기능은 하나도 잃지 않는다.**

모듈 32개 중 화면에 6개만 보였다(타입별 "더보기" 로 1개씩만 노출).
블로그 화면과 같은 공용 컴포넌트를 써서 전부 보이게 한다.

계획서: docs/plans/list_ui_redesign.md
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "app/templates/modules/list.html"
ACTIONS = ROOT / "app/templates/modules/_row_actions.html"
JS = ROOT / "app/static/js/modules/list.js"


@pytest.fixture(scope="module")
def page() -> str:
    return LIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def actions() -> str:
    return ACTIONS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js() -> str:
    return JS.read_text(encoding="utf-8")


# ── 동작 보존 ────────────────────────────────────────────
@pytest.mark.parametrize("call", [
    '@click="editModule(module.id)"',
    '@click="copyModule(module.id)"',
    '@click="deleteModule(module.id)"',
])
def test_card_actions_survive(actions, call):
    """카드에 있던 동작이 하나라도 빠지면 기능 손실이다."""
    assert call in actions, f"동작 누락: {call}"


def test_actions_use_direct_calls(actions):
    """컴포넌트가 액션을 대신 그리면 클릭이 끊긴다(블로그에서 겪은 사고)."""
    assert "listAction" not in actions
    assert "onClick" not in actions


def test_screen_supplies_actions_markup(page):
    assert "modules/_row_actions.html" in page


# ── 표시 보존 ────────────────────────────────────────────
def test_module_info_reused(js):
    """카드가 쓰던 정보 생성 함수를 그대로 재사용한다."""
    assert "getModuleInfoRows(module)" in js
    assert "moduleDetailText" in js
    assert "moduleBlogNames" in js


def test_connected_blogs_shown(js):
    """어떤 블로그에 연결됐는지가 모듈에서 가장 중요한 정보다."""
    block = js[js.index("moduleBlogNames(module) {"):]
    block = block[:block.index("formatModuleDate")]
    assert "r.type === 'blog'" in block
    assert "b.name" in block


def test_legacy_warning_badge_kept(js):
    """레거시 대량 수집 경고가 사라지면 마이그레이션 대상을 놓친다."""
    assert "module.legacy_bulk_warning" in js


def test_prompt_preset_badge_kept(js):
    """어떤 프롬프트로 생성되는지 표시는 앞서 추가한 기능이다."""
    assert "module.prompt_preset" in js
    assert "module.adsense_approval_preset_label" in js


# ── 화면 구조 ────────────────────────────────────────────
def test_all_types_have_tabs(page):
    """살아 있는 타입은 모두 탭으로 있어야 한다.

    collect·bulk_collect 는 제거됐다(alembic 073) — 제목 수집·생성은
    title_gen 이 맡는다.
    """
    for code in ("prompt", "data", "growth_profile", "contact_form",
                 "keyword", "title_gen"):
        assert f"'code': '{code}'" in page, f"탭 누락: {code}"
    for gone in ("collect", "bulk_collect"):
        assert f"'code': '{gone}'" not in page, f"제거된 타입이 남았다: {gone}"


def test_types_use_tabs_not_stacked(page):
    """세로로 쌓으면 타입이 늘수록 아래가 밀려난다."""
    assert "typeTab" in page
    assert "x-show=\"typeTab === '{{ t.code }}'\"" in page


def test_more_button_removed(page):
    """타입별 1개만 보이던 것이 문제의 핵심이었다."""
    # 주석에 경위가 적혀 있으므로 주석을 뺀 마크업만 본다
    markup = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    markup = re.sub(r"{#-?.*?-?#}", "", markup, flags=re.S)
    assert "sectionExpanded" not in markup
    assert "더보기" not in markup
    assert "idx < 1" not in markup
    assert "card-expand-btn" not in markup


def test_no_leftover_card_include(page):
    """카드가 남아 있으면 두 방식이 함께 그려진다."""
    assert 'include "modules/_card.html"' not in page


def test_search_present(page, js):
    assert 'x-model="moduleSearch"' in page
    assert "moduleSearch" in js
    # 모듈명뿐 아니라 연결 블로그로도 찾을 수 있어야 한다
    assert "moduleBlogNames(m).toLowerCase().includes(q)" in js


def test_sorting_present(js):
    assert "listSort(key)" in js
    assert "listSortIcon(key)" in js
    assert "this.listSortDir === 'asc' ? 'desc' : 'asc'" in js


def test_uses_shared_component(page):
    """화면마다 따로 만들면 동작이 갈라진다."""
    assert 'include "components/list_table.html"' in page


def test_adapter_contract(js):
    for fn in ("listColumns()", "listCell(module, key)", "listBadges(module)",
               "listTitle(module)", "listSub(module)", "visibleModules(typeCode)"):
        assert fn in js, f"어댑터 누락: {fn}"


def test_existing_sort_and_filter_kept(js):
    """기존 정렬 설정·타입 필터는 그대로 남는다."""
    assert "getModulesByType(typeCode)" in js
    assert "getSortedModules(filtered)" in js
    assert "loadSortPreference" in js
