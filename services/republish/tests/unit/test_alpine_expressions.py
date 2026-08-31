"""Alpine 표현식이 실제로 컴파일되는지 검사한다 (2026-08-31).

표 전환 화면들에서 두 가지를 놓쳤다.

1. 공용 표가 `listSelection[...]` 를 직접 읽었다. 오토런은 선택을
   selectedIds 로 들고 있어 그 이름이 없다 → 매 갱신마다 예외.
2. `x-effect` 를 주석으로 시작했다. Alpine 3.13.3 은
   /^[\\n\\s]*if.*\\(.*\\)/ 에 걸릴 때만 `(async()=>{...})()` 로 감싸므로,
   주석으로 시작하면 `return //주석\\nif(...)` 가 되어 SyntaxError 다.

둘 다 "속성이 있는지" 만 보던 기존 검사로는 잡히지 않았다. 여기서는
Alpine 과 같은 규칙으로 감싼 뒤 실제로 함수를 만들어 본다.
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

SCREENS = [
    "blogs/list.html",
    "modules/list.html",
    "flows/list.html",
    "autorun/index.html",
]

# Alpine 속성 전체를 잡은 뒤 표현식이 아닌 것을 걸러낸다.
ALPINE_ATTR = re.compile(
    r'(?<![\w:.\-])((?:x-[\w:.\-]+)|@[\w.\-]+|:[\w.\-]+)\s*=\s*"([^"]*)"'
)

# 값이 JS 표현식이 아닌 속성들
NOT_EXPRESSIONS = (
    "x-transition",   # CSS 클래스 이름 목록
    "x-for",          # `a in b` 전용 문법
    "x-cloak",
    "x-ref",
    "x-id",
)

# 화면이 제공해야 하는 함수·상태 (공용 표가 부르는 것)
REQUIRED_NAMES = [
    "listColumns", "listCell", "listBadges", "listTitle", "listSub",
    "listSort", "listSortIcon",
]
REQUIRED_SELECTABLE = [
    "listIsSelected", "listToggleOne", "listAllChecked", "listToggleAll",
    "listSelectedCount", "listClearSelection", "listSelectedRows",
]


def render(name: str) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    source = (TEMPLATES / name).read_text(encoding="utf-8")
    body = re.search(r"{% block content %}(.*?){% endblock %}", source, re.S)
    assert body, f"{name} 에 content 블록이 없다"
    return env.from_string(body.group(1)).render()


def expressions(html: str) -> list[tuple[str, str]]:
    out = []
    for attr, value in ALPINE_ATTR.findall(html):
        value = value.strip()
        if not value or attr.startswith(NOT_EXPRESSIONS):
            continue
        out.append((attr, value))
    return out


@pytest.mark.parametrize("screen", SCREENS)
def test_every_alpine_expression_compiles(screen: str) -> None:
    """Alpine 과 같은 방식으로 감싼 뒤 함수를 만들어 본다."""
    exprs = expressions(render(screen))
    assert exprs, f"{screen} 에서 표현식을 찾지 못했다"

    program = """
const items = JSON.parse(process.argv[1]);
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const bad = [];
for (const [attr, expr] of items) {
  // Alpine 3.13.3 의 판정 규칙 그대로
  const wrapped = /^[\\n\\s]*if.*\\(.*\\)/.test(expr.trim()) || /^(let|const)\\s/.test(expr.trim())
    ? `(async()=>{ ${expr} })()` : expr;
  try {
    new AsyncFunction(['__self', 'scope'],
      `with (scope) { __self.result = ${wrapped} }; return __self.result;`);
  } catch (e) {
    bad.push({attr, expr: expr.slice(0, 90), error: e.message});
  }
}
console.log(JSON.stringify(bad));
"""
    result = subprocess.run(
        ["node", "-e", program, json.dumps(exprs)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    bad = json.loads(result.stdout)
    assert not bad, "컴파일되지 않는 표현식:\n" + "\n".join(
        f"  {b['attr']}=\"{b['expr']}\" → {b['error']}" for b in bad
    )


@pytest.mark.parametrize("screen", SCREENS)
def test_no_leading_comment_in_alpine_expression(screen: str) -> None:
    """주석으로 시작하면 Alpine 의 문장 감싸기 판정이 빗나간다."""
    for attr, expr in expressions(render(screen)):
        assert not expr.lstrip().startswith("//"), f"{screen} {attr}"


def test_shared_table_uses_only_contract_functions() -> None:
    """공용 표가 특정 화면의 상태 이름을 직접 읽으면 다른 화면에서 깨진다.

    오토런은 선택을 selectedIds 로 들고 있어 listSelection 이 없다.
    """
    table = (TEMPLATES / "components" / "list_table.html").read_text(encoding="utf-8")
    body = table.split("#}", 1)[1]  # 머리말 주석의 규약 설명은 제외
    assert "listSelection[" not in body, "화면 상태를 직접 읽고 있다"


@pytest.mark.parametrize("screen", SCREENS)
def test_screens_provide_every_function_the_table_calls(screen: str) -> None:
    """공용 표가 부르는 함수를 화면이 하나라도 빠뜨리면 매 갱신마다 예외."""
    html = render(screen)
    if "list-table" not in html:
        pytest.skip("표를 쓰지 않는 화면")
    for name in REQUIRED_NAMES:
        assert f"{name}(" in html, f"{screen} 에 {name} 호출이 없다"
    if "listToggleAll(" in html:  # selectable 인 화면
        for name in REQUIRED_SELECTABLE:
            assert f"{name}(" in html or name in ("listIsSelected", "listToggleOne"), name
