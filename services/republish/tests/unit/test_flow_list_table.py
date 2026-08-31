"""플로우 목록 표 전환 — 기능 보존 (2026-08-31).

**절대 규칙: 표시 방식만 바꾸고 기능은 하나도 잃지 않는다.**

카드(flows/_card.html)가 하던 일이 표로 바꾼 뒤에도 남아 있는지 지킨다.
순서도: docs/flowcharts/flow_list_table.md
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
LIST = TEMPLATES / "flows" / "list.html"
ADAPTER = STATIC / "js" / "flows" / "list_table.js"


@pytest.fixture(scope="module")
def page() -> str:
    return LIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    body = re.search(r"{% block content %}(.*?){% endblock %}", page_source(), re.S)
    assert body, "content 블록이 없다"
    return env.from_string(body.group(1)).render()


def page_source() -> str:
    return LIST.read_text(encoding="utf-8")


# ── 동작 3가지 (카드 헤더 버튼) ──────────────────────────
@pytest.mark.parametrize("call", [
    "editFlow(flow.id)",
    "copyFlow(flow.id)",
    "deleteFlow(flow.id)",
])
def test_card_actions_survive(call: str) -> None:
    """카드가 하던 수정·복사·삭제가 행 액션에 그대로 있어야 한다."""
    actions = (TEMPLATES / "flows" / "_row_actions.html").read_text(encoding="utf-8")
    assert f'@click="{call}"' in actions


def test_every_tab_gets_actions(rendered: str) -> None:
    """탭 4개 × 표 2벌(데스크톱·모바일) = 8 — 어느 탭에서도 버튼이 있다."""
    for call in ("editFlow(flow.id)", "copyFlow(flow.id)", "deleteFlow(flow.id)"):
        assert rendered.count(call) == 8, call


# ── 탭 축 ────────────────────────────────────────────────
def test_four_tabs_cover_every_flow(rendered: str) -> None:
    """어느 탭에도 안 들어가는 플로우가 있으면 화면에서 사라진다."""
    scopes = set(re.findall(r"listToggleOne\('(flows-[a-z]+)'", rendered))
    assert scopes == {"flows-wordpress", "flows-blogger", "flows-mixed", "flows-none"}


def test_empty_tabs_are_hidden(rendered: str) -> None:
    """빈 탭까지 늘어놓으면 평소에 쓰지 않는 탭이 자리를 차지한다.

    탭이 {% for %} 로 묶여 원본에는 한 번만 나온다. 렌더 결과로 센다.
    """
    assert rendered.count("x-show=\"getFlowsByTab('") == 4


def test_tab_falls_back_when_current_is_empty(page: str) -> None:
    """워드프레스 플로우가 없을 때 빈 표만 남으면 안 된다.

    비동기 로드 뒤에도 반응해야 하므로 x-init 이 아니라 x-effect 여야 한다.
    """
    assert "x-effect" in page
    assert "getFlowsByTab(flowTabKey).length === 0" in page


# ── 정렬: 기존 기능 보존 ─────────────────────────────────
def test_existing_sort_dropdown_kept(page: str) -> None:
    """드롭다운 5종·방향 토글·저장은 그대로 있어야 한다."""
    for option in ("name", "created_at", "updated_at", "module_count", "blog_count"):
        assert f'value="{option}"' in page, option
    assert "toggleSortOrder()" in page
    assert "saveSortPreference()" in page


def test_column_sort_drives_the_same_state() -> None:
    """열 머리글이 별도 정렬 상태를 두면 드롭다운 표시와 순서가 어긋난다."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert "this.sortBy" in source and "this.sortOrder" in source
    # 상태 필드 선언(`listSortKey:` / `listSortDir:`)이 있으면 두 입구가
    # 서로 다른 순서를 낸다. 열↔드롭다운 대응표(listSortKeyFor)는 상태가 아니다.
    assert not re.search(r"\blistSort(Key|Dir)\s*:", source), "별도 정렬 상태를 만들면 안 된다"


def test_visible_flows_reuses_sorted_flows() -> None:
    """정렬 구현을 한 벌 더 만들면 두 입구가 다른 순서를 낸다."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert "this.sortedFlows.filter" in source


# ── 표시 정보 ────────────────────────────────────────────
def test_selectable_and_bulk_delete(page: str, rendered: str) -> None:
    assert rendered.count("deleteSelectedFlows(") == 4
    calls = re.findall(
        r"deleteSelectedFlows\('(flows-[a-z]+)', visibleFlows\('([a-z]+)'\)\)", rendered
    )
    assert len(calls) == 4
    for scope, tab in calls:
        assert scope == f"flows-{tab}"


def test_mixin_scripts_loaded_in_order(page: str) -> None:
    """mixin 을 안 실으면 앱이 예외로 죽어 표가 통째로 사라진다."""
    sel = page.index('<script src="/static/js/components/list_selection.js')
    adapter = page.index('<script src="/static/js/flows/list_table.js')
    app = page.index('<script src="/static/js/flows/list.js')
    assert sel < app and adapter < app


def test_card_template_is_kept() -> None:
    """카드 템플릿은 지우지 않는다 — 되돌릴 수 있어야 한다."""
    assert (TEMPLATES / "flows" / "_card.html").exists()


# ── 실동작 ───────────────────────────────────────────────
def _run(script: str) -> str:
    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}},
                    getElementById(){{return null}}, querySelectorAll(){{return []}}}};
global.window = {{addEventListener(){{}}}};
global.localStorage = {{getItem(){{return null}}, setItem(){{}}}};
const fs = require('fs');
eval(fs.readFileSync({str(STATIC / 'js' / 'components' / 'list_selection.js')!r}, 'utf8'));
eval(fs.readFileSync({str(ADAPTER)!r}, 'utf8'));
eval(fs.readFileSync({str(STATIC / 'js' / 'flows' / 'list.js')!r}, 'utf8'));
const app = flowListApp();
const mod = (id, name, code) => ({{id, module: {{id, name, module_type: {{code}}}}}});
const blg = (id, name, pf) => ({{id, blog: {{id, name, platform: pf}}}});
app.flows = [
  {{id: 1, name: '나_워프', updated_at: '2026-08-20T10:00:00',
    flow_modules: [mod(1, 'p', 'prompt')], flow_blogs: [blg(11, '인생꿀팁', 'wordpress')]}},
  {{id: 2, name: '가_워프', updated_at: '2026-08-22T10:00:00',
    flow_modules: [mod(2, 'p', 'prompt'), mod(3, 'g', 'growth_profile')],
    flow_blogs: [blg(12, '라이프인포', 'wordpress')]}},
  {{id: 3, name: '다_블로거', updated_at: '2026-08-21T10:00:00',
    flow_modules: [], flow_blogs: [blg(13, '군타', 'blogger')]}},
  {{id: 4, name: '수집', updated_at: '2026-08-19T10:00:00',
    flow_modules: [mod(4, 'c', 'collect')], flow_blogs: []}},
  {{id: 5, name: '혼합', updated_at: '2026-08-23T10:00:00', flow_modules: [],
    flow_blogs: [blg(11, '인생꿀팁', 'wordpress'), blg(13, '군타', 'blogger')]}},
];
const names = a => a.map(f => f.name).join(',');
{script}
"""
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_app_constructs_and_classifies_every_flow() -> None:
    """앱이 실제로 만들어지고, 플로우 5개가 모두 어떤 탭에 들어가야 한다."""
    out = _run("""
const tabs = ['wordpress', 'blogger', 'mixed', 'none'];
const total = tabs.reduce((n, t) => n + app.getFlowsByTab(t).length, 0);
console.log(JSON.stringify({
  total, all: app.flows.length,
  wp: names(app.getFlowsByTab('wordpress')),
  mixed: names(app.getFlowsByTab('mixed')),
  none: names(app.getFlowsByTab('none')),
}));
""")
    data = json.loads(out)
    assert data["total"] == data["all"], "어느 탭에도 안 들어간 플로우가 있다"
    assert data["mixed"] == "혼합"
    assert data["none"] == "수집"


def test_cells_carry_card_information() -> None:
    """카드가 보여주던 모듈 아이콘·이름과 블로그 플랫폼 배지가 남아야 한다."""
    out = _run("""
const f = app.flows.find(x => x.id === 1);
console.log(JSON.stringify({
  modules: app.listCell(f, 'modules'),
  blogs: app.listCell(f, 'blogs'),
  gp: app.listBadges(app.flows.find(x => x.id === 2)).map(b => b.label),
  noModule: app.listBadges(app.flows.find(x => x.id === 5)).map(b => b.label),
}));
""")
    data = json.loads(out)
    assert "인생꿀팁_프롬프트" not in data["modules"]  # 픽스처 이름은 p
    assert data["modules"].startswith("📝"), "모듈 아이콘이 빠졌다"
    assert data["blogs"] == "WP 인생꿀팁", "플랫폼 배지가 빠졌다"
    assert any("📈" in label for label in data["gp"]), "GP 배지가 빠졌다"
    assert "모듈 없음" in data["noModule"]


def test_column_sort_toggles_and_matches_dropdown() -> None:
    out = _run("""
app.listSort('modules');
const asc = names(app.visibleFlows('wordpress'));
const sortBy = app.sortBy;
app.listSort('modules');
console.log(JSON.stringify([asc, names(app.visibleFlows('wordpress')), sortBy,
                            app.listSortIcon('modules'), app.listSortIcon('name')]));
""")
    asc, desc, sort_by, icon, other = json.loads(out)
    assert sort_by == "module_count", "드롭다운과 같은 상태를 써야 한다"
    assert asc != desc, "정렬이 뒤집히지 않는다"
    assert icon in ("▲", "▼") and other == "↕"


def test_selection_is_isolated_per_tab() -> None:
    """워드프레스에서 전체선택해도 블로거 탭은 그대로여야 한다."""
    out = _run("""
app.listToggleAll('flows-wordpress', app.visibleFlows('wordpress'));
console.log(JSON.stringify({
  wp: app.listSelectedCount('flows-wordpress'),
  bl: app.listSelectedCount('flows-blogger'),
  blRows: names(app.listSelectedRows('flows-blogger', app.visibleFlows('blogger'))),
}));
""")
    data = json.loads(out)
    assert data["wp"] == 2 and data["bl"] == 0 and data["blRows"] == ""


def test_search_covers_modules_and_blogs() -> None:
    out = _run("""
app.flowSearch = '라이프인포';
console.log(names(app.visibleFlows('wordpress')));
""")
    assert out == "가_워프"


def test_select_all_only_targets_visible_rows() -> None:
    """검색으로 걸러진 뒤 전체선택하면 보이는 것만 선택돼야 한다."""
    out = _run("""
app.flowSearch = '라이프인포';
app.listToggleAll('flows-wordpress', app.visibleFlows('wordpress'));
app.flowSearch = '';
console.log(names(app.listSelectedRows('flows-wordpress', app.visibleFlows('wordpress'))));
""")
    assert out == "가_워프"


def test_flow_app_constructs_with_page_script_order() -> None:
    """템플릿의 <script> 순서를 그대로 재현해 앱이 실제로 만들어지는지 본다.

    렌더 결과만 보면 마크업은 멀쩡한데 브라우저에서 앱 함수가 예외로 죽어
    화면이 비는 경우를 놓친다 — 블로그 화면에서 실제로 겪었다.
    """
    html = LIST.read_text(encoding="utf-8")
    srcs = [STATIC / m.group(1) for m in re.finditer(r'<script src="/static/([^"?]+)', html)]
    existing = [str(p) for p in srcs if p.exists()]
    assert any("list_selection.js" in p for p in existing), "mixin 이 목록에 없다"
    assert any("list_table.js" in p for p in existing), "표 어댑터가 목록에 없다"

    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}},
                    getElementById(){{return null}}, querySelectorAll(){{return []}}}};
global.window = {{addEventListener(){{}}}};
global.localStorage = {{getItem(){{return null}}, setItem(){{}}}};
const fs = require('fs');
for (const f of {json.dumps(existing)}) {{
  try {{ eval(fs.readFileSync(f, 'utf8')); }} catch (e) {{ /* 무관한 화면 스크립트 */ }}
}}
const app = flowListApp();
for (const fn of ['listColumns', 'listCell', 'listBadges', 'visibleFlows',
                  'getFlowsByTab', 'listSelectedCount', 'deleteSelectedFlows']) {{
  if (typeof app[fn] !== 'function') throw new Error(fn + ' 없음');
}}
app.flows = [{{id: 1, name: 'a', flow_modules: [], flow_blogs: []}}];
console.log(JSON.stringify([app.visibleFlows('none').length,
                            app.listSelectedCount('flows-none')]));
"""
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"플로우 앱 생성 실패 — 화면이 빈다:\n{result.stderr}"
    assert json.loads(result.stdout) == [1, 0]
