"""공용 목록 표의 선택·일괄삭제 회귀 테스트.

선택 상태가 탭마다 분리되지 않으면 프롬프트 탭에서 전체선택했을 때
수집 탭 모듈까지 지워진다. 그 회귀를 막는 것이 이 파일의 목적이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "templates"
STATIC = Path(__file__).resolve().parents[2] / "app" / "static"


def _render_content(template_name: str) -> str:
    """상속 없이 {% block content %} 본문만 렌더한다."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    match = re.search(r"{% block content %}(.*?){% endblock %}", source, re.S)
    assert match, f"{template_name} 에 content 블록이 없다"
    return env.from_string(match.group(1)).render()


@pytest.fixture(scope="module")
def blogs_html() -> str:
    return _render_content("blogs/list.html")


@pytest.fixture(scope="module")
def modules_html() -> str:
    return _render_content("modules/list.html")


# ---------------------------------------------------------------- 체크박스

def test_blog_table_has_checkbox_column(blogs_html: str) -> None:
    """블로그 표 각 행 앞에 체크박스가 있어야 한다."""
    assert "listToggleOne('blogs-wordpress', blog.id)" in blogs_html
    assert "listToggleOne('blogs-blogger', blog.id)" in blogs_html


def test_module_table_has_checkbox_for_every_tab(modules_html: str) -> None:
    """살아 있는 타입 탭이 모두 체크박스를 가진다.

    collect·bulk_collect 는 제거됐다(alembic 073).
    """
    scopes = set(re.findall(r"listToggleOne\('(modules-[a-z_]+)'", modules_html))
    assert scopes == {
        "modules-prompt",
        "modules-data",
        "modules-growth_profile",
        "modules-contact_form",
        "modules-keyword",      # 키워드 모듈 추가(057)
        "modules-title_gen",    # 제목 생성/수집 모듈 추가(063)
    }


def test_select_all_targets_only_visible_rows(blogs_html: str, modules_html: str) -> None:
    """전체선택은 검색으로 걸러진 '보이는' 행만 대상으로 한다.

    안 보이는 항목이 함께 지워지면 사용자가 삭제 결과를 예측할 수 없다.
    """
    assert "listToggleAll('blogs-wordpress', visibleBlogs('wordpress'))" in blogs_html
    assert "listToggleAll('modules-prompt', visibleModules('prompt'))" in modules_html


# ---------------------------------------------------------------- 탭별 분리

def test_selection_scope_is_per_tab(modules_html: str) -> None:
    """각 탭의 삭제 버튼은 자기 탭 범위·자기 탭 행만 넘긴다."""
    calls = re.findall(
        r"deleteSelectedModules\('(modules-[a-z_]+)', visibleModules\('([a-z_]+)'\)\)",
        modules_html,
    )
    # 프롬프트·데이터·성장·문의폼·키워드·제목
    # (collect·bulk_collect 는 제거됨 — alembic 073)
    assert len(calls) == 6
    for scope, type_code in calls:
        assert scope == f"modules-{type_code}", (scope, type_code)


def test_blog_bulk_delete_scope_matches_platform(blogs_html: str) -> None:
    calls = re.findall(
        r"deleteSelectedBlogs\('(blogs-[a-z]+)', visibleBlogs\('([a-z]+)'\)\)",
        blogs_html,
    )
    assert sorted(calls) == [
        ("blogs-blogger", "blogger"),
        ("blogs-wordpress", "wordpress"),
    ]


def test_bulk_delete_bar_hidden_without_selection(blogs_html: str, modules_html: str) -> None:
    """선택이 없으면 삭제 바가 보이지 않는다."""
    assert "listSelectedCount('blogs-wordpress') > 0" in blogs_html
    assert "listSelectedCount('modules-prompt') > 0" in modules_html


# ---------------------------------------------------------------- 컴포넌트

def test_checkbox_is_opt_in() -> None:
    """selectable 을 넘기지 않은 화면(플로우 등)에는 체크박스가 생기지 않는다."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    template = env.get_template("components/list_table.html")
    common = {
        "table_id": "t",
        "rows_expr": "rows",
        "row_key": "row",
        "empty_text": "없음",
    }
    with_box = template.render(selectable=True, **common)
    without_box = template.render(**common)
    assert "listToggleAll(" in with_box
    assert "listToggleAll(" not in without_box


def test_selection_mixin_exposes_required_api() -> None:
    """화면들이 호출하는 mixin 함수가 모두 정의돼 있어야 한다."""
    source = (STATIC / "js" / "components" / "list_selection.js").read_text(encoding="utf-8")
    for name in (
        "listSelected",
        "listIsSelected",
        "listToggleOne",
        "listSelectedCount",
        "listAllChecked",
        "listToggleAll",
        "listClearSelection",
        "listSelectedRows",
    ):
        assert re.search(rf"\b{name}\s*\(", source), f"{name} 누락"


def test_screens_load_selection_mixin() -> None:
    """mixin 스크립트를 <script src> 로 실제 로드해야 한다.

    로드하지 않으면 listSelectionMixin 이 undefined 라 화면 앱 함수가
    예외로 죽고 표가 통째로 사라진다. 주석에 파일명만 적혀 있어도
    통과하던 검사를 태그 자체를 찾도록 좁혔다.
    """
    for name in ("blogs/list.html", "modules/list.html"):
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        assert re.search(
            r'<script\s+src="/static/js/components/list_selection\.js[^"]*"\s*>', html
        ), f"{name} 에 list_selection.js 스크립트 태그가 없다"


def test_mixin_loads_before_the_app_that_spreads_it() -> None:
    """mixin 태그가 앱 정의보다 뒤에 있으면 안 된다."""
    html = (TEMPLATES / "blogs/list.html").read_text(encoding="utf-8")
    tag = html.index('<script src="/static/js/components/list_selection.js')
    app = html.index("function blogListApp()")
    assert tag < app, "mixin 을 blogListApp 정의보다 먼저 로드해야 한다"


def test_module_app_spreads_mixin() -> None:
    source = (STATIC / "js" / "modules" / "list.js").read_text(encoding="utf-8")
    assert "...listSelectionMixin()" in source


# ---------------------------------------------------------------- 정렬

def test_connected_blogs_column_is_sortable() -> None:
    """연결 블로그 열도 오름/내림차순 정렬이 되어야 한다."""
    source = (STATIC / "js" / "modules" / "list.js").read_text(encoding="utf-8")
    column = re.search(r"\{ key: 'blogs',.*?\}", source)
    assert column and "sortable: true" in column.group(0)
    assert "case 'blogs':" in source, "정렬 비교값이 없으면 정렬해도 순서가 안 바뀐다"


# ---------------------------------------------------------------- 실동작

def _run_mixin(script: str) -> str:
    """mixin 을 실제로 실행해 결과를 돌려준다(Node)."""
    import subprocess
    source = (STATIC / "js" / "components" / "list_selection.js").read_text(encoding="utf-8")
    program = source + """
const s = listSelectionMixin();
const call = (name, ...a) => s[name].apply(s, a);
""" + script
    result = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_toggle_all_does_not_leak_across_tabs() -> None:
    """프롬프트 탭 전체선택이 다른 탭 선택에 영향을 주지 않는다."""
    out = _run_mixin("""
const prompt = [{id: 1}, {id: 2}];
const keyword = [{id: 7}];
call('listToggleAll', 'modules-prompt', prompt);
console.log(JSON.stringify({
  prompt: call('listSelectedCount', 'modules-prompt'),
  keyword: call('listSelectedCount', 'modules-keyword'),
  keywordRows: call('listSelectedRows', 'modules-keyword', keyword).length,
}));
""")
    assert out == '{"prompt":2,"keyword":0,"keywordRows":0}'


def test_toggle_all_twice_clears() -> None:
    out = _run_mixin("""
const rows = [{id: 1}, {id: 2}];
call('listToggleAll', 'x', rows);
call('listToggleAll', 'x', rows);
console.log(call('listSelectedCount', 'x'));
""")
    assert out == "0"


def test_selected_rows_returns_only_chosen() -> None:
    """일괄삭제 대상이 선택한 것만이어야 한다."""
    out = _run_mixin("""
const rows = [{id: 1, name: 'a'}, {id: 2, name: 'b'}, {id: 3, name: 'c'}];
call('listToggleOne', 'x', 2);
console.log(call('listSelectedRows', 'x', rows).map(r => r.name).join(','));
""")
    assert out == "b"


def test_toggle_one_is_reversible() -> None:
    out = _run_mixin("""
call('listToggleOne', 'x', 5);
call('listToggleOne', 'x', 5);
console.log(JSON.stringify([call('listSelectedCount', 'x'), call('listIsSelected', 'x', 5)]));
""")
    assert out == "[0,false]"


def test_all_checked_ignores_hidden_rows() -> None:
    """검색으로 3개 중 1개만 보일 때, 그 1개만 선택해도 머리글은 체크된다."""
    out = _run_mixin("""
const visible = [{id: 2}];
call('listToggleOne', 'x', 2);
console.log(call('listAllChecked', 'x', visible));
""")
    assert out == "true"


def test_connected_blogs_sort_actually_reorders() -> None:
    """연결 블로그 정렬이 순서를 실제로 바꾸는지 확인한다.

    sortable 플래그만 붙고 비교값이 없으면 화살표만 바뀌고 순서는 그대로다.
    """
    import subprocess

    program = """
global.document = {addEventListener(){}, querySelector(){return null}, getElementById(){return null}};
global.window = {addEventListener(){}};
const fs = require('fs');
eval(fs.readFileSync(SEL, 'utf8'));
// _blogsCache 는 파일 안에서 let 으로 선언돼 밖에서 못 넣는다. 같은 스코프에 붙인다.
eval(fs.readFileSync(LIST, 'utf8') + `
_blogsCache = [{id: 11, name: '인생꿀팁'}, {id: 12, name: '군타'}];
globalThis.__app = moduleListApp();
`);
const app = globalThis.__app;
window.moduleListAppInstance = app;
const mod = (id, name, blogIds) => ({
  id, name, module_type: {code: 'prompt'}, settings: {blogs: blogIds},
});
app.modules = [mod(1, '가', [11]), mod(2, '나', [12])];
const order = () => app.visibleModules('prompt').map(m => m.name).join('');
app.listSort('blogs');
const asc = order();
app.listSort('blogs');
console.log(JSON.stringify([asc, order(), app.listCell(app.modules[0], 'blogs')]));
"""
    program = (
        f"const SEL = {str(STATIC / 'js' / 'components' / 'list_selection.js')!r};\n"
        f"const LIST = {str(STATIC / 'js' / 'modules' / 'list.js')!r};\n"
        + program
    )
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    ascending, descending, cell = __import__("json").loads(result.stdout)
    assert cell == "인생꿀팁", "연결 블로그 셀이 비어 있으면 정렬해도 의미가 없다"
    assert ascending != descending, "오름/내림 결과가 같다 — 정렬이 동작하지 않는다"


def test_blog_app_constructs_with_page_script_order() -> None:
    """템플릿의 <script> 순서를 그대로 재현해 앱이 실제로 만들어지는지 본다.

    Jinja 렌더 결과만 보면 표 마크업은 멀쩡한데 브라우저에서 앱 함수가
    예외로 죽어 화면이 비는 경우를 놓친다(실제로 놓쳤다). 페이지가 싣는
    스크립트를 순서대로 실행한 뒤 앱을 만들어 본다.
    """
    import json
    import subprocess

    html = (TEMPLATES / "blogs/list.html").read_text(encoding="utf-8")

    # 페이지가 싣는 로컬 스크립트를 등장 순서대로 모은다
    srcs = [
        STATIC / m.group(1)
        for m in re.finditer(r'<script src="/static/([^"?]+)', html)
    ]
    existing = [str(p) for p in srcs if p.exists()]
    assert any("list_selection.js" in p for p in existing), "mixin 이 목록에 없다"

    inline = html[html.index("function blogListApp()"):html.index("// ========== 전역 참조 저장용")]
    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}}, getElementById(){{return null}}}};
global.window = {{addEventListener(){{}}}};
const fs = require('fs');
for (const f of {json.dumps(existing)}) {{
  try {{ eval(fs.readFileSync(f, 'utf8')); }} catch (e) {{ /* 무관한 화면 스크립트 */ }}
}}
{inline}
const app = blogListApp();
if (typeof app.listSelectedCount !== 'function') throw new Error('mixin 미적용');
app.blogs = [{{id: 1, name: 'a', platform: 'wordpress', url: 'https://a.com'}}];
console.log(JSON.stringify([app.visibleBlogs('wordpress').length, app.listSelectedCount('blogs-wordpress')]));
"""
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"블로그 앱 생성 실패 — 화면이 빈다:\n{result.stderr}"
    assert json.loads(result.stdout) == [1, 0]
