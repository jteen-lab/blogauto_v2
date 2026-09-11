"""blogs.style_config → 글에 붙일 CSS.

발행 HTML 은 클래스만 담고 CSS 는 블로그 테마에 있다. 그런데 수작업으로 올리는
글은 테마 CSS 가 아직 없을 수 있어, 글 안에 <style> 로 함께 넣을 CSS 가 필요하다.

단위 규칙(px 를 붙일 속성)은 `static/js/blogs/style-tab-css-utils.js` 의
CSS_PIXEL_PROPERTIES 와 같게 맞춘다. 어긋나면 미리보기와 실제가 달라진다.

    python style_config_to_css.py style.json [스코프클래스]
"""
import json
import sys

PX = {
    "font-size", "border-width", "border-radius",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border-top-width", "border-right-width",
    "border-bottom-width", "border-left-width",
}
SCOPE = sys.argv[2] if len(sys.argv) > 2 else ".isanote-post"

cfg = json.load(open(sys.argv[1]))
out = []
for selector, props in cfg.items():
    if not props:
        continue
    decls = "; ".join(
        f"{k}: {v}px" if k in PX else f"{k}: {v}" for k, v in props.items())
    out.append(f"{SCOPE} {selector} {{ {decls}; }}")
print("\n".join(out))
