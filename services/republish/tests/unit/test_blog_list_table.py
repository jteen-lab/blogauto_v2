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
    assert call in page, f"동작 누락: {call}"


def test_busy_state_kept_for_long_actions(page):
    """동기화·테스트는 진행 중 표시가 있었다. 없으면 두 번 누르게 된다."""
    assert "busy: this.syncing === blog.id" in page
    assert "busy: this.testing === blog.id" in page


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


def test_adapter_implements_full_contract(page):
    """블로그 화면이 규약 6개를 모두 구현했는지."""
    for fn in ("listColumns()", "listCell(blog, key)", "listBadges(blog)",
               "listActions(blog)", "listTitle(blog)", "listSub(blog)"):
        assert fn in page, f"어댑터 누락: {fn}"


def test_actions_have_distinct_keys(page):
    """키가 겹치면 Alpine x-for 가 버튼을 잘못 그린다."""
    block = page[page.index("listActions(blog) {"):]
    block = block[:block.index("listTitle")]
    keys = re.findall(r"key:\s*'([^']+)'", block)
    assert len(keys) == 5 and len(set(keys)) == 5, keys
