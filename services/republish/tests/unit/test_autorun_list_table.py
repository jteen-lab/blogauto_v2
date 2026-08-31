"""오토런 목록 표 전환 — 기능 보존 (2026-08-31).

**절대 규칙: 표시 방식만 바꾸고 기능은 하나도 잃지 않는다.**

오토런은 다른 화면과 달리 **이미 선택 기능이 있다**. 상단 바의 전체·
일시정지·재개·제외가 모두 selectedIds 를 읽는다. 선택 저장소가 둘이
되면 표에서 고른 것과 버튼이 동작하는 대상이 갈라진다.

순서도: docs/flowcharts/autorun_list_table.md
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "templates"
STATIC = ROOT / "app" / "static"
INDEX = TEMPLATES / "autorun" / "index.html"
MAIN = STATIC / "js" / "autorun" / "main.js"


@pytest.fixture(scope="module")
def page() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    body = re.search(
        r"{% block content %}(.*?){% endblock %}",
        INDEX.read_text(encoding="utf-8"), re.S,
    )
    assert body, "content 블록이 없다"
    return env.from_string(body.group(1)).render()


def page_scripts() -> list[str]:
    """템플릿이 싣는 로컬 스크립트를 등장 순서대로."""
    html = INDEX.read_text(encoding="utf-8")
    srcs = [STATIC / m.group(1) for m in re.finditer(r'<script src="/static/([^"?]+)', html)]
    return [str(p) for p in srcs if p.exists()]


# ── 카드 동작 보존 ───────────────────────────────────────
@pytest.mark.parametrize("call", [
    "pauseFlow(flow.id)",
    "resumeFlow(flow.id)",
    "removeFlow(flow.id)",
])
def test_card_actions_survive(call: str) -> None:
    actions = (TEMPLATES / "autorun" / "_row_actions.html").read_text(encoding="utf-8")
    assert f'@click="{call}"' in actions


def test_pause_resume_stay_state_conditional() -> None:
    """상태와 맞지 않는 버튼을 누르면 API 가 거절하고 사용자는 이유를 모른다."""
    actions = (TEMPLATES / "autorun" / "_row_actions.html").read_text(encoding="utf-8")
    assert "x-if=\"flow.status === 'active'\"" in actions
    assert "x-if=\"flow.status === 'paused'\"" in actions


def test_top_bar_bulk_buttons_kept(page: str) -> None:
    """상단 바의 기존 일괄 버튼과 카운트를 지우지 않는다."""
    for call in ("selectAll()", "bulkPause()", "bulkResume()", "bulkRemove()"):
        assert call in page, call
    assert "activeCount" in page and "pausedCount" in page
    assert "openAddSheet()" in page


def test_card_template_is_kept() -> None:
    assert (TEMPLATES / "autorun" / "_card.html").exists()


# ── 선택 저장소는 하나 ───────────────────────────────────
def test_no_second_selection_store() -> None:
    """listSelectionMixin 을 쓰면 selectedIds 와 저장소가 둘이 된다."""
    adapter = (STATIC / "js" / "autorun" / "list_table.js").read_text(encoding="utf-8")
    # 주석에서 "쓰지 않는다" 고 설명하는 것은 괜찮다. 전개해서 쓰면 안 된다.
    assert "...listSelectionMixin()" not in adapter
    assert "this.selectedIds" in adapter
    page = INDEX.read_text(encoding="utf-8")
    assert "list_selection.js" not in page


def test_mixin_has_no_getters() -> None:
    """전개(spread)되는 객체에 getter 를 두면 그 시점 값으로 굳는다."""
    adapter = (STATIC / "js" / "autorun" / "list_table.js").read_text(encoding="utf-8")
    assert not re.search(r"^\s{8}get\s+\w+\(\)", adapter, re.M)


# ── 탭 ───────────────────────────────────────────────────
def test_four_tabs_cover_every_flow(rendered: str) -> None:
    scopes = set(re.findall(r"listToggleOne\('(autorun-[a-z]+)'", rendered))
    assert scopes == {
        "autorun-wordpress", "autorun-blogger", "autorun-mixed", "autorun-none",
    }


def test_shared_platform_rule(page: str) -> None:
    """플로우와 판정이 갈리면 같은 플로우가 화면마다 다른 탭에 들어간다."""
    assert "platform_tabs.js" in page
    adapter = (STATIC / "js" / "autorun" / "list_table.js").read_text(encoding="utf-8")
    assert "platformTabOf(" in adapter


def test_tab_falls_back_when_current_is_empty(page: str) -> None:
    assert "x-effect" in page
    assert "getAutorunByTab(autorunTab).length === 0" in page


def test_scripts_loaded_before_app(page: str) -> None:
    """어댑터를 안 실으면 앱이 예외로 죽어 화면이 통째로 빈다."""
    tabs = page.index('<script src="/static/js/components/platform_tabs.js')
    adapter = page.index('<script src="/static/js/autorun/list_table.js')
    main = page.index('<script src="/static/js/autorun/main.js')
    assert tabs < main and adapter < main


# ── 실동작 ───────────────────────────────────────────────
FIXTURE = """
const bl = (id, name, pf) => ({id, blog: {id, name, platform: pf}});
const ml = (id, name, code) => ({id, module: {id, name, module_type: {code}}});
app.autorunFlows = [
  {id: 1, name: 'wp활성', status: 'active', next_execution: '2026-08-31T15:30:00',
   module_links: [ml(1, 'p', 'prompt')], blog_links: [bl(11, '인생꿀팁', 'wordpress')],
   module_count: 1, blog_count: 1},
  {id: 2, name: 'wp자동정지', status: 'paused', auto_paused: true, consecutive_failures: 3,
   paused_actions: ['generate'], generation_blocked: [{module_name: 'p'}],
   module_links: [ml(2, 'p', 'prompt')], blog_links: [bl(12, '라이프인포', 'wordpress')],
   module_count: 1, blog_count: 1},
  {id: 3, name: 'bl활성', status: 'active',
   module_links: [], blog_links: [bl(13, '군타', 'blogger')], module_count: 0, blog_count: 1},
  {id: 4, name: '수집', status: 'active',
   module_links: [ml(4, 'c', 'collect')], blog_links: [], module_count: 1, blog_count: 0},
];
app.loadAutorunFlows = async () => {};
const names = ids => ids.map(i => app.autorunFlows.find(f => f.id === i).name).join(',');
"""


def _run(script: str, *, capture_fetch: bool = False) -> str:
    fetch_stub = """
let POSTED = [];
global.fetch = async (url, opt) => {
  POSTED.push({url, body: opt && opt.body});
  return {ok: true, json: async () => ({})};
};
global.confirm = () => true;
""" if capture_fetch else ""
    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}},
                    getElementById(){{return null}}, querySelectorAll(){{return []}}}};
global.window = {{addEventListener(){{}}}};
global.showErrorMessage = () => {{}};
global.showSuccessMessage = () => {{}};
{fetch_stub}
const fs = require('fs');
for (const f of {json.dumps(page_scripts())}) {{
  try {{ eval(fs.readFileSync(f, 'utf8')); }} catch (e) {{ /* 무관한 화면 스크립트 */ }}
}}
const app = autorunApp();
{FIXTURE}
{script}
"""
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_app_constructs_and_classifies_every_flow() -> None:
    out = _run("""
const tabs = ['wordpress', 'blogger', 'mixed', 'none'];
const total = tabs.reduce((n, t) => n + app.getAutorunByTab(t).length, 0);
console.log(JSON.stringify({total, all: app.autorunFlows.length,
                            none: names(app.getAutorunByTab('none').map(f => f.id))}));
""")
    data = json.loads(out)
    assert data["total"] == data["all"], "어느 탭에도 안 들어간 항목이 있다"
    assert data["none"] == "수집"


def test_cells_carry_card_information() -> None:
    """상태·다음 실행·경고 배지가 카드에서 그대로 넘어와야 한다."""
    out = _run("""
const f = id => app.autorunFlows.find(x => x.id === id);
console.log(JSON.stringify({
  active: app.listCell(f(1), 'status'),
  auto: app.listCell(f(2), 'status'),
  manual: app.listCell({status: 'paused', auto_paused: false}, 'status'),
  next: app.listCell(f(1), 'next'),
  noNext: app.listCell(f(2), 'next'),
  badges: app.listBadges(f(2)).map(b => b.label),
  tips: app.listBadges(f(2)).map(b => b.tip),
  blogs: app.listCell(f(1), 'blogs'),
}));
""")
    d = json.loads(out)
    assert d["active"] == "🟢 실행중"
    assert d["auto"] == "🔴 자동정지"
    assert d["manual"] == "🟡 일시정지"
    assert d["next"] != "-" and d["noNext"] == "-"
    assert "생성 정지" in d["badges"] and "연속 실패 3회" in d["badges"]
    assert any("승인용 프리셋" in t for t in d["tips"])
    assert d["blogs"] == "WP 인생꿀팁"


def test_inactive_is_not_shown_as_paused() -> None:
    """오토런 목록에는 inactive 플로우도 섞여 있다.

    상단 바의 🟢+🟡 합이 총 개수보다 작은 이유가 이것이다. 상태가 정렬
    가능한 열이 된 이상 일시정지와 뭉뚱그리면 오해를 키운다.
    """
    out = _run("""
console.log(JSON.stringify({
  inactive: app.listCell({status: 'inactive'}, 'status'),
  paused: app.listCell({status: 'paused', auto_paused: false}, 'status'),
  title: app.listTitle({status: 'inactive', name: 'x'}),
}));
""")
    d = json.loads(out)
    assert d["inactive"] == "⚪ 비활성"
    assert d["paused"] == "🟡 일시정지"
    assert d["inactive"] != d["paused"]
    assert d["title"].startswith("⚪")


def test_status_sort_orders_by_urgency() -> None:
    """오름차순 한 번으로 손봐야 할 것이 뒤에 모여야 한다."""
    out = _run("""
app.autorunFlows = [
  {id: 9, name: '자동정지', status: 'paused', auto_paused: true, module_links: [], blog_links: [bl(1, 'b', 'wordpress')]},
  {id: 8, name: '실행중', status: 'active', module_links: [], blog_links: [bl(2, 'b', 'wordpress')]},
  {id: 7, name: '비활성', status: 'inactive', module_links: [], blog_links: [bl(3, 'b', 'wordpress')]},
  {id: 6, name: '일시정지', status: 'paused', module_links: [], blog_links: [bl(4, 'b', 'wordpress')]},
];
app.listSort('status');
console.log(app.visibleAutorun('wordpress').map(f => f.name).join(','));
""")
    assert out == "실행중,비활성,일시정지,자동정지"


def test_status_sort_puts_problems_last() -> None:
    out = _run("""
app.listSort('status');
console.log(names(app.visibleAutorun('wordpress').map(f => f.id)));
""")
    assert out == "wp활성,wp자동정지"


def test_select_all_is_scoped_to_current_tab() -> None:
    """탭으로 나뉜 뒤 전체 기준으로 두면 안 보이는 항목이 선택된다."""
    out = _run("""
app.autorunTab = 'wordpress';
app.selectAll();
const afterWp = names(app.selectedIds);
app.autorunTab = 'blogger';
console.log(JSON.stringify([afterWp, app.listSelectedCount('autorun-blogger'),
                            app.isAllSelected]));
""")
    picked, blogger_count, all_selected = json.loads(out)
    assert set(picked.split(",")) == {"wp활성", "wp자동정지"}
    assert blogger_count == 0
    assert all_selected is False


def test_bulk_action_only_touches_current_tab() -> None:
    """블로거 탭에서 제외를 눌러도 워드프레스 선택은 그대로여야 한다."""
    out = _run("""
(async () => {
  app.autorunTab = 'wordpress';
  app.selectAll();
  app.autorunTab = 'blogger';
  await app.bulkRemove();
  console.log(JSON.stringify({
    deletes: POSTED.filter(p => p.url.includes('/autorun/flows/')).length,
    left: names(app.selectedIds),
  }));
})();
""", capture_fetch=True)
    d = json.loads(out)
    assert d["deletes"] == 0, "안 보이는 탭의 항목이 제외됐다"
    assert set(d["left"].split(",")) == {"wp활성", "wp자동정지"}


def test_bulk_pause_sends_only_active_in_tab() -> None:
    out = _run("""
(async () => {
  app.autorunTab = 'wordpress';
  app.selectAll();
  await app.bulkPause();
  const body = POSTED.find(p => p.url.includes('bulk-action'));
  console.log(JSON.stringify({
    ids: body ? JSON.parse(body.body).flow_ids : [],
    left: app.selectedIds,
  }));
})();
""", capture_fetch=True)
    d = json.loads(out)
    assert d["ids"] == [1], "활성인 것만 일시정지해야 한다"
    assert d["left"] == [], "처리한 범위는 해제돼야 한다"


def test_other_tab_selection_survives_bulk_action() -> None:
    """동작 뒤 전체를 해제하면 다른 탭 선택을 말없이 버리게 된다."""
    out = _run("""
(async () => {
  app.autorunTab = 'blogger';
  app.selectAll();                 // bl활성 선택
  app.autorunTab = 'wordpress';
  app.selectAll();                 // wp 2개 추가 선택
  await app.bulkPause();           // wp 탭에서만 동작
  console.log(names(app.selectedIds));
})();
""", capture_fetch=True)
    assert out == "bl활성"


def test_search_covers_modules_and_blogs() -> None:
    out = _run("""
app.autorunSearch = '라이프인포';
console.log(names(app.visibleAutorun('wordpress').map(f => f.id)));
""")
    assert out == "wp자동정지"


def test_select_all_only_targets_visible_rows() -> None:
    out = _run("""
app.autorunTab = 'wordpress';
app.autorunSearch = '라이프인포';
app.selectAll();
app.autorunSearch = '';
console.log(names(app.selectedIds));
""")
    assert out == "wp자동정지"
