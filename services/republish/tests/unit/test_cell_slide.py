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
class FakeEl {
  constructor(width, half) {
    this.clientWidth = width; this._half = half;
    this.classList = new ClassList();
    const self = this;
    this.track = {
      classList: new ClassList(['no-slide']),
      get scrollWidth() { return self._half * 2; },
    };
  }
  querySelector(sel) { return sel === '.cell-slide-track' ? this.track : null; }
}
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
