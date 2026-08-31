"""표 셀 슬라이드 (2026-08-31).

카드는 좁은 폭에 모듈 설정을 담으려고 가로 슬라이드를 썼다. 표로 바꾸면서
그 정보가 통째로 빠졌다. 되살린 뒤, 특히 **탭 뒤에 숨은 셀**이 나중에
열렸을 때도 제대로 흐르는지 지킨다.

순서도: docs/flowcharts/list_table_cell_slide.md
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
SLIDE_JS = STATIC / "js" / "components" / "cell_slide.js"

# (화면, 흐를 열)
SLIDE_SCREENS = [
    ("modules/list.html", "detail"),
    ("flows/list.html", "modules"),
    ("autorun/index.html", "modules"),
]


def render(name: str) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    source = (TEMPLATES / name).read_text(encoding="utf-8")
    body = re.search(r"{% block content %}(.*?){% endblock %}", source, re.S)
    assert body, f"{name} 에 content 블록이 없다"
    return env.from_string(body.group(1)).render()


# ── 마크업 ───────────────────────────────────────────────
def test_component_renders_slide_only_for_slide_columns() -> None:
    """slide 를 안 준 열까지 흐르면 훑기가 나빠진다."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    html = env.get_template("components/list_table.html").render(
        table_id="t", rows_expr="rows", row_key="row", empty_text="없음", selectable=True,
    )
    assert "col.slide" in html
    assert "!col.slide" in html, "슬라이드가 아닌 열의 렌더가 없다"


def test_duplicate_is_hidden_from_screen_readers() -> None:
    """복제본을 그대로 읽으면 같은 내용을 두 번 듣게 된다."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    html = env.get_template("components/list_table.html").render(
        table_id="t", rows_expr="rows", row_key="row", empty_text="없음",
    )
    # 데스크톱·모바일 두 벌 모두 복제본이 있고 둘 다 aria-hidden
    assert html.count('aria-hidden="true"') == 2
    assert html.count("slide-cycle-separator") == 2


@pytest.mark.parametrize("screen,_col", SLIDE_SCREENS)
def test_both_desktop_and_mobile_slide(screen: str, _col: str) -> None:
    """데스크톱에만 넣으면 두 화면이 다른 정보를 보여준다."""
    html = render(screen)
    # 탭 수만큼 표가 그려지므로 배수로 나온다 — 데스크톱/모바일 각 1벌씩
    tables = html.count('class="list-table"')
    assert tables > 0
    assert html.count("cell-slide--mobile") == tables, "모바일 슬라이드가 빠졌다"
    assert html.count("initCellSlide(") == tables * 2, "데스크톱·모바일 초기화가 각각 있어야 한다"


@pytest.mark.parametrize("screen,_col", SLIDE_SCREENS)
def test_slide_assets_loaded(screen: str, _col: str) -> None:
    """CSS·JS 를 안 실으면 흐르지 않거나 함수가 없어 예외가 난다."""
    page = (TEMPLATES / screen).read_text(encoding="utf-8")
    assert "list-table-slide.css" in page, screen
    assert re.search(r'<script src="/static/js/components/cell_slide\.js', page), screen


@pytest.mark.parametrize("screen,col", SLIDE_SCREENS)
def test_screen_marks_the_column_as_slide(screen: str, col: str) -> None:
    """열에 slide 를 안 주면 마크업이 아예 안 나온다."""
    adapter = {
        "modules/list.html": STATIC / "js" / "modules" / "list.js",
        "flows/list.html": STATIC / "js" / "flows" / "list_table.js",
        "autorun/index.html": STATIC / "js" / "autorun" / "list_table.js",
    }[screen].read_text(encoding="utf-8")
    column = re.search(rf"\{{ key: '{col}',[^}}]*\}}", adapter)
    assert column and "slide: true" in column.group(0), f"{screen} {col}"


# ── 셀 값에 설정이 담기는가 ──────────────────────────────
def _run(script: str, scripts: list[str]) -> str:
    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}},
                    getElementById(){{return null}}, querySelectorAll(){{return []}}}};
global.window = {{addEventListener(){{}}}};
global.localStorage = {{getItem(){{return null}}, setItem(){{}}}};
global.showErrorMessage = () => {{}};
global.showSuccessMessage = () => {{}};
const fs = require('fs');
for (const f of {json.dumps(scripts)}) {{
  try {{ eval(fs.readFileSync(f, 'utf8')); }} catch (e) {{ }}
}}
{script}
"""
    r = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


COLLECT_MODULE = {
    "id": 1, "name": "키워드 수집",
    "module_type": {"code": "collect"},
    "settings": {
        "collect_type": "both", "schedule_mode": "fixed_time",
        "fixed_times": ["06:00", "18:00"],
        "source_naver_ads": True, "source_naver_datalab": True,
    },
}


def test_flow_module_cell_carries_settings() -> None:
    """이름만 남기면 카드가 전달하던 정보가 사라진다."""
    out = _run(f"""
const app = flowListApp();
window.flowListApp = app;
app.flows = [{{id: 1, name: 't',
  flow_modules: [{{id: 1, module: {json.dumps(COLLECT_MODULE, ensure_ascii=False)}}}],
  flow_blogs: []}}];
console.log(app.listCell(app.flows[0], 'modules'));
""", [
        str(STATIC / "js" / "components" / "platform_tabs.js"),
        str(STATIC / "js" / "components" / "list_selection.js"),
        str(STATIC / "js" / "flows" / "list_table.js"),
        str(STATIC / "js" / "flows" / "list.js"),
    ])
    assert "키워드 수집" in out
    assert "06:00" in out, "설정값이 셀에 없다 — 슬라이드를 붙여도 전달할 정보가 없다"
    assert "수집" in out


def test_autorun_module_cell_carries_settings() -> None:
    out = _run(f"""
const app = autorunApp();
app.autorunFlows = [{{id: 1, name: 't', status: 'active',
  module_links: [{{id: 1, module: {json.dumps(COLLECT_MODULE, ensure_ascii=False)}}}],
  blog_links: []}}];
console.log(app.listCell(app.autorunFlows[0], 'modules'));
""", [
        str(STATIC / "js" / "components" / "platform_tabs.js"),
        str(STATIC / "js" / "autorun" / "list_table.js"),
        str(STATIC / "js" / "autorun" / "main.js"),
    ])
    assert "키워드 수집" in out and "06:00" in out


# ── 흐를지 판정 ──────────────────────────────────────────
SLIDE_HARNESS = """
class ClassList {
  constructor(init) { this.s = new Set(init); }
  contains(c) { return this.s.has(c); }
  add(c) { this.s.add(c); }
  remove(c) { this.s.delete(c); }
  toggle(c) { this.s.has(c) ? this.s.delete(c) : this.s.add(c); }
}
let LAYOUT_READS = [];
class FakeEl {
  // width: 셀에 주어진 폭, content: 내용 한 벌의 폭
  constructor(width, content) {
    this.clientWidth = width; this._content = content;
    this.classList = new ClassList();
    const self = this;
    this.track = { classList: new ClassList(['no-slide']) };
    this.first = {
      get scrollWidth() { LAYOUT_READS.push(self.track.classList.contains('no-slide')); return self._content; },
    };
  }
  querySelector(sel) {
    if (sel === '.cell-slide-track') return this.track;
    if (sel === '.cell-slide-item') return this.first;
    return null;
  }
}
global.requestAnimationFrame = fn => fn();
let OBSERVERS = [];
global.ResizeObserver = class {
  constructor(cb) { this.cb = cb; OBSERVERS.push(this); }
  observe() {}
};
const flows = el => !el.track.classList.contains('no-slide');
"""


def _slide(script: str) -> str:
    return _run(SLIDE_HARNESS + script, [str(SLIDE_JS)])


def test_overflowing_cell_slides_and_short_one_does_not() -> None:
    out = _slide("""
const wide = new FakeEl(200, 500);   // 내용이 넘친다
const narrow = new FakeEl(500, 200); // 다 들어간다
initCellSlide(wide); initCellSlide(narrow);
console.log(JSON.stringify([flows(wide), flows(narrow)]));
""")
    assert json.loads(out) == [True, False]


def test_hidden_tab_starts_sliding_when_opened() -> None:
    """탭 뒤에 숨은 셀은 폭이 0이라 잴 수 없다.

    그때 한 번 재고 끝내면 탭을 열어도 영영 흐르지 않는다.
    """
    out = _slide("""
const el = new FakeEl(0, 500);       // 숨은 탭
initCellSlide(el);
const beforeOpen = flows(el);
const observed = OBSERVERS.length;
el.clientWidth = 200;                 // 탭이 열려 폭이 생김
OBSERVERS[0].cb();
console.log(JSON.stringify([beforeOpen, observed, flows(el)]));
""")
    before, observed, after = json.loads(out)
    assert before is False, "숨은 동안에는 흐르면 안 된다"
    assert observed == 1, "폭이 생기기를 기다리는 관찰자가 없다"
    assert after is True, "탭을 열어도 흐르지 않는다"


def test_widening_window_stops_the_slide() -> None:
    """창을 넓혀 다 들어가면 흐를 이유가 없다."""
    out = _slide("""
const el = new FakeEl(200, 500);
initCellSlide(el);
const narrowState = flows(el);
el.clientWidth = 900;
OBSERVERS[0].cb();
console.log(JSON.stringify([narrowState, flows(el)]));
""")
    assert json.loads(out) == [True, False]


def test_touch_pauses_only_sliding_cells() -> None:
    """모바일은 hover 가 없어 탭이 유일한 정지 수단이다."""
    out = _slide("""
const moving = new FakeEl(200, 500);
const still = new FakeEl(500, 200);
initCellSlide(moving); initCellSlide(still);
toggleCellSlideTouch({}, moving);
const paused = moving.track.classList.contains('paused');
toggleCellSlideTouch({}, moving);
const resumed = !moving.track.classList.contains('paused');
toggleCellSlideTouch({}, still);
console.log(JSON.stringify([paused, resumed, still.track.classList.contains('paused')]));
""")
    paused, resumed, still_paused = json.loads(out)
    assert paused and resumed
    assert still_paused is False, "안 흐르는 셀까지 상태를 바꾸면 안 된다"


def test_duration_scales_with_length() -> None:
    out = _slide("""
console.log(JSON.stringify([cellSlideDuration('짧다'),
                            cellSlideDuration('x'.repeat(1000)),
                            cellSlideDuration('x'.repeat(100))]));
""")
    short, very_long, medium = json.loads(out)
    assert short == 14, "짧아도 너무 빠르면 읽을 수 없다"
    assert very_long == 48, "길어도 한없이 느려지면 안 된다"
    assert short < medium < very_long


def test_reduced_motion_is_respected() -> None:
    css = (STATIC / "css" / "list-table-slide.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


# ── 폭이 늘어나 스크롤이 깜빡이던 문제 ───────────────────
def test_measure_never_expands_the_track() -> None:
    """복제본을 펼쳐 재면 트랙이 두 배가 되고 열이 넓어진다.

    넓어진 것을 ResizeObserver 가 다시 잡아 재고… 스크롤바가 깜빡이는
    고리가 된다. 항상 보이는 첫 항목만 재야 한다.
    """
    out = _slide("""
LAYOUT_READS = [];
const el = new FakeEl(200, 500);
initCellSlide(el);
// 측정 중 단 한 번이라도 no-slide 를 떼고 읽었다면 트랙이 넓어졌다는 뜻
console.log(JSON.stringify({expanded: LAYOUT_READS.some(noSlide => noSlide === false),
                            reads: LAYOUT_READS.length, flows: flows(el)}));
""")
    d = json.loads(out)
    assert d["reads"] > 0, "측정을 아예 안 했다"
    assert d["expanded"] is False, "복제본을 펼쳐 재고 있다 — 열이 넓어진다"
    assert d["flows"] is True


def test_repeated_observer_calls_settle() -> None:
    """같은 폭으로 여러 번 불려도 상태가 계속 바뀌면 안 된다."""
    out = _slide("""
const el = new FakeEl(200, 500);
initCellSlide(el);
const states = [flows(el)];
for (let i = 0; i < 5; i++) { OBSERVERS[0].cb(); states.push(flows(el)); }
console.log(JSON.stringify(states));
""")
    states = json.loads(out)
    assert len(set(states)) == 1, f"상태가 계속 흔들린다: {states}"
    assert states[0] is True


def test_table_is_fixed_layout_when_a_column_slides() -> None:
    """자동 레이아웃에서는 nowrap 셀이 글자 길이만큼 열을 늘린다."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    html = env.get_template("components/list_table.html").render(
        table_id="t", rows_expr="rows", row_key="row", empty_text="없음",
    )
    assert "list-table--fixed" in html
    assert "listColumns().some(c => c.slide)" in html
    css = (STATIC / "css" / "list-table-slide.css").read_text(encoding="utf-8")
    assert "table-layout: fixed" in css


@pytest.mark.parametrize("screen,_col", SLIDE_SCREENS)
def test_every_column_has_a_width(screen: str, _col: str) -> None:
    """고정 레이아웃에서 폭 없는 열은 남는 공간을 임의로 나눠 갖는다."""
    adapter = {
        "modules/list.html": STATIC / "js" / "modules" / "list.js",
        "flows/list.html": STATIC / "js" / "flows" / "list_table.js",
        "autorun/index.html": STATIC / "js" / "autorun" / "list_table.js",
    }[screen].read_text(encoding="utf-8")
    block = re.search(r"listColumns\(\) \{\s*return \[(.*?)\];", adapter, re.S)
    assert block
    for line in block.group(1).strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        assert "width:" in line, f"{screen} 폭 없는 열: {line}"


def test_cache_version_bumped_for_changed_assets() -> None:
    """내용이 바뀐 파일의 ?v= 를 그대로 두면 브라우저가 옛 것을 쓴다.

    실제로 모듈·플로우에서 슬라이드가 적용되지 않은 원인이었다.
    """
    for screen, _ in SLIDE_SCREENS:
        page = (TEMPLATES / screen).read_text(encoding="utf-8")
        for asset in ("cell_slide.js", "list-table-slide.css"):
            m = re.search(rf'{re.escape(asset)}\?v=([^"]+)"', page)
            assert m, f"{screen} 의 {asset} 에 ?v= 가 없다"
            assert m.group(1) == "20260831sub", f"{screen} {asset} 버전이 낡았다"


# ── 모바일 2줄째와 슬라이드 줄의 중복 ────────────────────
MOBILE_CASES = [
    (
        "modules",
        [
            str(STATIC / "js" / "components" / "list_selection.js"),
            str(STATIC / "js" / "modules" / "list.js"),
        ],
        """
const app = moduleListApp();
window.moduleListAppInstance = app;
const row = {id: 1, name: '군타_프로파일', module_type: {code: 'growth_profile'},
             settings: {stages: [{}, {}], warmup: {days: 7}}};
""",
    ),
    (
        "flows",
        [
            str(STATIC / "js" / "components" / "platform_tabs.js"),
            str(STATIC / "js" / "components" / "list_selection.js"),
            str(STATIC / "js" / "flows" / "list_table.js"),
            str(STATIC / "js" / "flows" / "list.js"),
        ],
        """
const app = flowListApp();
window.flowListApp = app;
const row = {id: 1, name: 't', description: '설명',
             flow_modules: [{id: 1, module: MODULE}], flow_blogs: []};
""",
    ),
    (
        "autorun",
        [
            str(STATIC / "js" / "components" / "platform_tabs.js"),
            str(STATIC / "js" / "autorun" / "list_table.js"),
            str(STATIC / "js" / "autorun" / "main.js"),
        ],
        """
const app = autorunApp();
const row = {id: 1, name: 't', status: 'active',
             module_links: [{id: 1, module: MODULE}], blog_links: []};
""",
    ),
]


@pytest.mark.parametrize("name,scripts,setup", MOBILE_CASES)
def test_mobile_sub_line_does_not_repeat_the_sliding_text(
    name: str, scripts: list[str], setup: str,
) -> None:
    """모바일 2줄째가 슬라이드 줄과 같은 내용을 담으면 두 번 나온다.

    게다가 2줄째는 흐르지도 않아 잘린 채 중복만 된다.
    """
    slide_col = "detail" if name == "modules" else "modules"
    out = _run(
        f"const MODULE = {json.dumps(COLLECT_MODULE, ensure_ascii=False)};\n"
        + setup
        + f"""
const sub = app.listSub(row);
const slid = app.listCell(row, '{slide_col}');
console.log(JSON.stringify({{sub, slid}}));
""",
        scripts,
    )
    data = json.loads(out)
    slid = data["slid"]
    sub = data["sub"]
    assert slid and slid != "-", "슬라이드 값이 비어 검사가 무의미하다"
    head = slid[:20]
    assert head not in sub, f"{name}: 2줄째가 슬라이드 내용을 되풀이한다\n  2줄: {sub}\n  슬라이드: {slid}"


def test_module_type_name_uses_the_app_method() -> None:
    """getModuleTypeName·getModuleIcon 은 전역이 아니라 앱 메서드다.

    전역으로 검사하면 조건이 늘 거짓이라 종류가 코드 원문으로 나오거나
    배지가 통째로 사라진다.
    """
    out = _run("""
const app = moduleListApp();
window.moduleListAppInstance = app;
const row = {id: 1, name: 'x', module_type: {code: 'growth_profile'}, settings: {}};
console.log(JSON.stringify({type: app.listCell(row, 'type'),
                            badges: app.listBadges(row).map(b => b.label)}));
""", [
        str(STATIC / "js" / "components" / "list_selection.js"),
        str(STATIC / "js" / "modules" / "list.js"),
    ])
    d = json.loads(out)
    assert d["type"] == "성장 프로파일", f"코드 원문이 그대로 나온다: {d['type']}"
    assert d["badges"], "종류 배지가 사라졌다"
    assert "성장 프로파일" in d["badges"][0]
