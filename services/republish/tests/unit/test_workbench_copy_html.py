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
JS = "\n".join((ROOT / f"app/static/js/{name}").read_text(encoding="utf-8")
                for name in ("workbench-preview.js", "workbench.js"))
LOCAL_IMG = '<div><img src="/static/generated/images/a.png"></div>'

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
    const c = Object.assign(moduleTester(), {
        preview: { html: env.html === undefined ? '<p>본문</p>' : env.html,
                   title: 't', imageUrl: null, raw: '' },
        blogs: env.noBlog ? [] : [{id: 3}],
        $nextTick: f => f && f(),
        $refs: { htmlBox: { focus() {}, select() { env.boxSelected = true; } } },
    });
    c._json = async (url, opts) => {
        env.called = url;
        env.sent = JSON.parse(opts.body);
        if (env.uploadThrows) throw new Error('네트워크 끊김');
        return env.upload || {success: true, uploaded: 1, total: 1,
                              html: env.uploadedHtml
                                  || '<div><img src="https://i.ibb.co/x.webp"></div>'};
    };
    return c;
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
                                called: env.called || null,
                                sent: env.sent || null,
                                boxHtml: c.preview.html,
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


class TestCopyUploadsImages:
    """붙여넣을 곳에서도 보이게, 복사할 때 이미지를 올려 절대주소로 바꾼다.

    미리보기 HTML 의 이미지는 로컬 경로다. 그대로 붙이면 그 블로그 도메인으로
    해석되어 깨진다(초기 손글 붙여넣기 글들이 멀쩡했던 이유는 그 파일들이
    이미 imgbb 주소를 갖고 있었기 때문 — 2026-09-27 확인).
    """

    def test_로컬_이미지가_있으면_올린_뒤_복사한다(self):
        got = _run({"clipboard": True, "secure": True, "execOk": True,
                    "html": LOCAL_IMG})
        assert got["called"].endswith("/workbench/copy-html")
        assert got["sent"]["blog_id"] == 3
        assert "i.ibb.co" in got["wrote"] and "/static/" not in got["wrote"]
        assert "이미지 1개" in got["message"]

    def test_로컬_이미지가_없으면_부르지_않는다(self):
        got = _run({"clipboard": True, "secure": True, "execOk": True})
        assert got["called"] is None
        assert got["wrote"] == "<p>본문</p>"

    def test_올리기_실패하면_복사하지_않는다(self):
        """반쪽만 바뀐 본문을 붙이면 어느 이미지가 깨졌는지 알기 어렵다."""
        got = _run({"clipboard": True, "secure": True, "execOk": True,
                    "html": LOCAL_IMG,
                    "upload": {"success": False, "error": "imgbb 키가 없습니다"}})
        assert got["wrote"] is None
        assert "복사하지 않았습니다" in got["message"]
        assert "imgbb 키가 없습니다" in got["message"]

    def test_요청이_끊기면_그대로_알린다(self):
        got = _run({"clipboard": True, "secure": True, "execOk": True,
                    "html": LOCAL_IMG, "uploadThrows": True})
        assert got["wrote"] is None
        assert "네트워크 끊김" in got["message"]

    def test_자동복사가_막히면_바뀐_본문을_칸에_넣는다(self):
        """손으로 복사할 때도 절대주소가 든 본문이어야 한다."""
        got = _run({"clipboard": False, "secure": False, "execOk": False,
                    "html": LOCAL_IMG})
        assert got["editMode"] is True and got["boxSelected"] is True
        assert "i.ibb.co" in got["boxHtml"]


class TestKeepStoredBodyLocal:
    """저장분까지 원격 주소로 바꾸면 표지 중복 문제가 되살아난다."""

    def test_복사_경로는_저장분을_건드리지_않는다(self):
        src = (ROOT / "app/services/workbench/copy_html.py").read_text(
            encoding="utf-8")
        assert "저장된 본문은 건드리지 않는다" in src
        # 조립·저장 경로에서는 부르지 않는다
        apply_src = (ROOT / "app/services/workbench/apply.py").read_text(
            encoding="utf-8")
        assert "copy_html" not in apply_src
