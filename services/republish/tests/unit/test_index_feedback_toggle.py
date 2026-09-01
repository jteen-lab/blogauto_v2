"""색인 되먹임 끄기 (2026-09-01).

성장 프로파일에 하루 2개로 적어놨는데 실제로는 1개만 만들었다. 색인 되먹임이
상한을 덮어쓰고 있었지만, 화면 어디에도 그 사실이 없었고 끌 방법도 없었다.
`index_feedback_enabled` 는 코드에만 있었다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "app/static/js/settings.js"
HTML = ROOT / "app/templates/settings/modal.html"


def test_setting_key_matches_the_backend() -> None:
    """키가 어긋나면 토글이 아무 일도 하지 않는다."""
    from app.services.generation.index_feedback import SETTING_KEY

    assert SETTING_KEY in JS.read_text(encoding="utf-8")


def test_unset_shows_as_on() -> None:
    """DB 에 값이 없으면 서버는 켜진 것으로 본다.

    화면이 그걸 모르면 꺼짐으로 그려, 사용자가 켜려고 눌러서 오히려 끈다.
    """
    js = JS.read_text(encoding="utf-8")
    assert "defaultOn" in js
    m = re.search(r"systemQualityItems\.forEach\((.*?)\}\);", js, re.S)
    assert m, "로드 시 기본값을 채우지 않는다"
    assert "flat[it.key] = 'true'" in m.group(1)


def test_backend_treats_unset_as_on() -> None:
    """위 화면 동작의 근거."""
    src = (ROOT / "app/services/generation/index_feedback.py").read_text(
        encoding="utf-8")
    body = src[src.index("async def is_enabled"):]
    assert "return True" in body
    assert '"false"' in body or "'false'" in body


def test_toggle_is_rendered() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'x-for="item in systemQualityItems"' in html
    assert "toggleSystemSetting(item.key)" in html


def test_copy_explains_the_gp_override() -> None:
    """'왜 2개로 해놨는데 1개지' 가 이 기능의 첫 질문이었다."""
    html = HTML.read_text(encoding="utf-8")
    section = html[html.index("발행량 자동 조절"):]
    section = section[:section.index("AI Rate Limit")]
    assert "성장 프로파일" in section


def test_cache_version_bumped() -> None:
    """?v= 를 안 올리면 브라우저가 옛 JS 를 쓴다 — 이미 한 번 겪었다."""
    html = HTML.read_text(encoding="utf-8")
    assert "js/settings.js?v=20260901_indexfb" in html
