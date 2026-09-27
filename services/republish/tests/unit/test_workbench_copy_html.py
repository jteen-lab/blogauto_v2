"""미리보기 HTML 복사 — http 접속에서도 되게.

`navigator.clipboard` 는 **보안 컨텍스트(https·localhost)에서만** 동작한다.
서버는 http://168.110.98.47 로 접속하니 이 API 가 막혀 "복사 권한이 없습니다"
만 떴다(2026-09-27 사용자 확인). 세 갈래로 시도한다.

    1) clipboard API        https 면 이걸로
    2) execCommand('copy')  http 에서도 되는 옛 방식
    3) HTML 칸을 열고 전체 선택 → Ctrl+C 안내
"""
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = (ROOT / "app/static/js/workbench.js").read_text(encoding="utf-8")

HARNESS = """
global.promoLinkPart = () => ({});
global.blogKeywordPart = () => ({});
global.sourcePart = () => ({});
"""

DRIVER = """
function harness(env) {
    global.navigator = env.clipboard
        ? { clipboard: { writeText: async (t) => { env.wrote = t; } } } : {};
    global.window = { isSecureContext: env.secure };
    global.document = {
        createElement: () => ({ style: {}, setAttribute() {},
                                select() { env.selected = true; },
                                setSelectionRange() {} }),
        body: { appendChild() {}, removeChild() {} },
        execCommand: () => env.execOk,
    };
    return Object.assign(moduleTester(), {
        preview: { html: env.html === undefined ? '<p>본문</p>' : env.html,
                   title: 't', imageUrl: null, raw: '' },
        $nextTick: f => f && f(),
        $refs: { htmlBox: { focus() {}, select() { env.boxSelected = true; } } },
    });
}
"""


def _run(env: dict) -> dict:
    program = HARNESS + JS + DRIVER + """
(async () => {
    const env = %s;
    const c = harness(env);
    await c.copyHtml();
    console.log(JSON.stringify({message: c.postMessage, editMode: !!c.editMode,
                                wrote: env.wrote || null,
                                execSelected: !!env.selected,
                                boxSelected: !!env.boxSelected}));
})().catch(e => { console.error(e); process.exit(1); });
""" % json.dumps(env)
    r = subprocess.run(["node", "-e", program], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestCopyHtml:
    def test_https_는_클립보드_API로(self):
        got = _run({"clipboard": True, "secure": True, "execOk": False})
        assert got["wrote"] == "<p>본문</p>"
        assert "복사했습니다" in got["message"]
        assert got["editMode"] is False

    def test_http_는_옛_방식으로라도_복사한다(self):
        """이 갈래가 없어서 서버(http)에서는 복사가 아예 안 됐다."""
        got = _run({"clipboard": False, "secure": False, "execOk": True})
        assert "복사했습니다" in got["message"]
        assert got["execSelected"] is True

    def test_클립보드가_막혀도_옛_방식으로_내려온다(self):
        """API 는 있지만 권한이 없는 경우(throw)."""
        got = _run({"clipboard": True, "secure": False, "execOk": True})
        assert "복사했습니다" in got["message"]

    def test_둘_다_막히면_칸을_열고_골라_준다(self):
        got = _run({"clipboard": False, "secure": False, "execOk": False})
        assert "Ctrl+C" in got["message"]
        assert got["editMode"] is True and got["boxSelected"] is True

    def test_본문이_없으면_그렇게_말한다(self):
        got = _run({"clipboard": True, "secure": True, "execOk": True,
                    "html": ""})
        assert "복사할 본문이 없습니다" in got["message"]


def test_html_칸에_ref가_붙어_있다():
    """마지막 갈래가 칸을 고르려면 x-ref 가 있어야 한다."""
    tmpl = (ROOT / "app/templates/workbench/index.html").read_text(
        encoding="utf-8")
    assert 'x-ref="htmlBox"' in tmpl
