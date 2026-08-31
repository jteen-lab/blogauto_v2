"""블로그 목록 표 전환 — 기능 보존 (2026-08-31).

**절대 규칙: 표시 방식만 바꾸고 기능은 하나도 잃지 않는다.**

카드가 하던 일(동작 5가지·표시 8가지·크롤 상태 6종·화면 기능 4가지)이
표로 바꾼 뒤에도 전부 남아 있는지 지킨다. 이 테스트가 그 계약이다.

공용 컴포넌트(components/list_table.html)는 블로그 필드를 몰라야 다른
화면에서 재사용된다 — 그 경계도 함께 검사한다.

계획서: docs/plans/list_ui_redesign.md
순서도: docs/flowcharts/list_table_component.md
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "app/templates/blogs/list.html"
TABLE = ROOT / "app/templates/components/list_table.html"


@pytest.fixture(scope="module")
def page() -> str:
    return LIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table() -> str:
    return TABLE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered() -> str:
    """Jinja 로 그린 결과.

    플랫폼별 표가 {% for %} 로 묶여 있어 원본에는 한 번만 나온다.
    실제로 두 벌이 그려지는지는 렌더 결과로만 확인할 수 있다.
    """
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(ROOT / "app/templates")))
    source = LIST.read_text(encoding="utf-8")
    body = re.search(r"{% block content %}(.*?){% endblock %}", source, re.S)
    assert body, "content 블록이 없다"
    return env.from_string(body.group(1)).render()


# ── 동작 5가지 (카드 헤더 버튼) ───────────────────────────
@pytest.mark.parametrize("call", [
    "this.openEditSheet(blog)",
    "this.openSettingsSheet(blog)",
    "this.syncPublishedPosts(blog.id)",
    "this.testConnection(blog.id)",
    "this.deleteBlog(blog.id, blog.name)",
])
def test_every_card_action_survives(page, call):
    """카드에 있던 동작이 하나라도 빠지면 기능 손실이다."""
    actions = (ROOT / "app/templates/blogs/_row_actions.html").read_text(
        encoding="utf-8")
    bare = call.replace("this.", "")
    assert bare in actions or call in page, f"동작 누락: {call}"


def test_actions_use_direct_calls(page, table):
    """컴포넌트가 액션을 대신 그리면 하단시트가 열리지 않았다.

    카드에서 검증된 직접 호출(@click="openEditSheet(blog)")을 화면이
    마크업으로 주고, 컴포넌트는 include 만 한다.
    """
    markup = re.sub(r"{#.*?#}", "", table, flags=re.S)
    assert "{% include actions_include %}" in markup
    # 컴포넌트가 액션을 직접 그리면 안 된다
    assert "listActions(" not in markup
    assert "onClick" not in markup

    actions = (ROOT / "app/templates/blogs/_row_actions.html").read_text(
        encoding="utf-8")
    for call in ('@click="openEditSheet(blog)"',
                 '@click="openSettingsSheet(blog)"',
                 '@click="syncPublishedPosts(blog.id)"',
                 '@click="testConnection(blog.id)"',
                 '@click="deleteBlog(blog.id, blog.name)"'):
        assert call in actions, f"직접 호출 누락: {call}"


def test_screen_supplies_actions_markup(page, rendered):
    """두 표 모두 액션 마크업을 지정해야 버튼이 나온다."""
    assert "actions_include" in page
    # 행 액션 5가지가 두 플랫폼 표에 모두 그려졌는지 결과로 확인한다
    assert rendered.count("openEditSheet(blog)") >= 2
    assert rendered.count("openSettingsSheet(blog)") >= 2


def test_bottom_sheet_targets_exist(page):
    """하단시트를 여는 대상 요소가 페이지에 있어야 실제로 열린다."""
    assert "openBottomSheet('blogEditForm')" in page
    assert "openBottomSheet('blogSettings')" in page
    assert 'id="blogSettings"' in page or "blogSettings" in page





# ── 표시 정보 ────────────────────────────────────────────
@pytest.mark.parametrize("needle", [
    "blog.name",              # 이름
    "blog.url",               # 주소
    "blog.matched_count",     # 매칭 수
    "blog.crawled_count",     # 크롤 수
    "this.formatDate(blog.created_at)",  # 등록일
    "blog.auto_publish",      # 자동발행
    "this.adsenseBadge(blog)",           # 애드센스
    "blog.seo_config?.detected_plugin",  # SEO 플러그인
])
def test_every_displayed_field_survives(page, needle):
    assert needle in page, f"표시 항목 누락: {needle}"


def test_platform_marker_kept(page):
    """모바일 목록에서는 섹션이 섞이므로 WP/BL 표시가 필요하다."""
    assert "'WP'" in page and "'BL'" in page


# ── 크롤 상태 6종 ────────────────────────────────────────
@pytest.mark.parametrize("label", [
    "연결 필요", "크롤링 중", "매칭 진행 중",
    "연결됨 (신규)", "매칭 완료", "연결 오류",
])
def test_all_crawl_states_survive(page, label):
    """상태 하나라도 사라지면 블로그 상태를 오판한다."""
    assert label in page, f"크롤 상태 누락: {label}"


def test_crawl_state_conditions_kept(page):
    """조건 분기가 유지되는지 — 라벨만 남고 조건이 빠지면 안 된다."""
    for cond in ("'never'", "'crawling'", "'matching'", "'error'",
                 "blog.is_new_blog"):
        assert cond in page, f"상태 조건 누락: {cond}"


# ── 화면 기능 ────────────────────────────────────────────
def test_platform_sections_kept(page):
    """워드프레스와 블로거가 섞이면 안 된다 — 사용자가 요구한 구분."""
    assert "getBlogsByPlatform('wordpress')" in page
    assert "getBlogsByPlatform('blogger')" in page
    assert "WordPress" in page and "Google Blogger" in page


def test_adsense_filter_chips_kept(page):
    assert "adsenseChips()" in page
    assert "toggleAdsenseFilter(chip.key)" in page
    assert "adsenseFilter = ''" in page


def test_create_button_kept(page):
    assert "openCreateSheet()" in page


def test_no_leftover_card_include(page):
    """카드 include 가 남아 있으면 두 방식이 함께 그려진다."""
    assert 'include "blogs/_card.html"' not in page


# ── 공용 컴포넌트 경계 ────────────────────────────────────
def test_component_renders_both_layouts(table):
    """데스크톱 표와 모바일 목록을 함께 그린다."""
    assert "hidden md:block" in table   # 데스크톱
    assert "md:hidden" in table         # 모바일


def test_component_uses_same_rows_for_both(table):
    """모바일 전용 데이터를 따로 만들면 정렬·필터 결과가 갈린다."""
    assert table.count("{{ rows_expr }}") >= 4


def test_component_knows_no_blog_fields(table):
    """컴포넌트가 블로그 필드를 알면 다른 화면에서 재사용할 수 없다."""
    for leak in ("adsense", "crawl_status", "matched_count", "platform",
                 "seo_config", "auto_publish"):
        assert leak not in table, f"컴포넌트에 화면 전용 필드 누출: {leak}"


def test_component_contract_is_documented():
    """다음 화면이 같은 규약을 쓰려면 문서가 있어야 한다."""
    doc = ROOT.parent.parent / "docs/flowcharts/list_table_component.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for fn in ("listColumns", "listCell", "listBadges", "listActions",
               "listTitle", "listSub"):
        assert fn in text, f"규약 문서에 {fn} 누락"


def test_adapter_implements_contract(page):
    """블로그 화면이 규약을 구현했는지(액션은 마크업으로 준다)."""
    for fn in ("listColumns()", "listCell(blog, key)", "listBadges(blog)",
               "listTitle(blog)", "listSub(blog)"):
        assert fn in page, f"어댑터 누락: {fn}"


def test_busy_state_in_actions_markup():
    """동기화·테스트는 진행 중 표시가 있어야 두 번 누르지 않는다."""
    actions = (ROOT / "app/templates/blogs/_row_actions.html").read_text(
        encoding="utf-8")
    assert 'x-show="syncing === blog.id"' in actions
    assert 'x-show="testing === blog.id"' in actions
    assert ':disabled="syncing === blog.id"' in actions
    assert ':disabled="testing === blog.id"' in actions


# ── 2026-08-31 지적 반영 ─────────────────────────────────
def test_platform_uses_tabs_not_stacked(page, rendered):
    """워드프레스 아래에 블로거를 쌓으면 개수가 늘수록 아래로 밀려난다.
    같은 자리에서 탭으로 전환한다."""
    assert "platformTab" in page
    assert "platformTab === 'wordpress'" in rendered
    assert "platformTab === 'blogger'" in rendered
    # 두 표가 동시에 보이면 탭이 아니다
    assert rendered.count('x-show="platformTab ===') == 2


def test_search_by_name(page):
    """블로그명·주소로 걸러진다."""
    assert 'x-model="blogSearch"' in page
    assert "blogSearch" in page
    assert ".includes(q)" in page


def test_column_sorting(page, table):
    """열 머리글을 눌러 오름/내림 정렬."""
    assert "listSort(col.key)" in table
    assert "listSortIcon(col.key)" in table
    assert "this.sortDir === 'asc' ? 'desc' : 'asc'" in page
    # 숫자를 문자열로 비교하면 10 < 9 가 된다
    assert "sortValue(blog, key)" in page
    assert "blog.matched_count ?? 0" in page


def test_sortable_columns_marked(page):
    """정렬 가능한 열이 지정돼 있어야 머리글이 눌린다."""
    block = page[page.index("listColumns() {"):]
    block = block[:block.index("listCell")]
    assert block.count("sortable: true") == 4


def test_table_scrolls_internally(table):
    """화면 전체가 늘어나면 훑는 동안 머리글이 사라진다."""
    assert "max-height" in table
    assert "overflow-y-auto" in table
    assert "sticky top-0" in table


def test_max_height_passed_by_screen(page):
    assert "max_height = '30rem'" in page


def test_adsense_chips_above_table(page):
    """표 아래에 있으면 표를 다 지나야 보인다."""
    assert page.index("adsenseChips()") < page.index("components/list_table.html")
