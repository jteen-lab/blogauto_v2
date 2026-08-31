"""문의 수신함 읽음 처리 (2026-08-31).

문의를 다 읽었는데도 "2 미읽음" 이 남았다. 버그가 아니라 앱과 사용자의
'읽음' 정의가 달랐다 — 앱은 「읽음」 버튼을 눌러야만 읽음으로 쳤고,
사용자는 펼쳐서 내용을 본 것을 읽었다고 여겼다.

펼쳐서 본 문의는 읽은 것으로 치고, 일괄 처리 수단도 둔다.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "app/routers/contact_submissions.py"
JS = ROOT / "app/static/js/dashboard/kpi_spark.js"
HTML = ROOT / "app/templates/dashboard/dashboard_v2.html"


@pytest.fixture(scope="module")
def router() -> str:
    return ROUTER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js() -> str:
    return JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html() -> str:
    return HTML.read_text(encoding="utf-8")


# ── API ─────────────────────────────────────────────────
def test_bulk_read_endpoint_exists(router):
    """건별 호출만 있으면 문의가 쌓일수록 그 수만큼 요청이 나간다."""
    assert '@router.post("/read-all")' in router
    assert "mark_all_read" in router


def test_bulk_read_only_touches_unread(router):
    """이미 읽은 것까지 건드리면 갱신 건수가 부풀려진다."""
    block = router[router.index("async def mark_all_read"):]
    block = block[:block.index("@router.post(\"/{submission_id}/read\")")]
    assert "is_read.is_(False)" in block
    assert "values(is_read=True)" in block


def test_bulk_read_can_scope_to_blog(router):
    """블로그별로 정리할 수 있어야 한다."""
    block = router[router.index("async def mark_all_read"):]
    block = block[:block.index("@router.post(\"/{submission_id}/read\")")]
    assert "blog_id is not None" in block


def test_bulk_read_returns_count(router):
    """몇 건이 처리됐는지 알려야 화면이 안내할 수 있다."""
    assert '"updated": changed' in router


def test_single_read_endpoint_kept(router):
    """개별 토글은 그대로 남는다 — 안읽음으로 되돌릴 수단이 필요하다."""
    assert '@router.post("/{submission_id}/read")' in router
    assert "sub.is_read = is_read" in router


# ── 화면 ────────────────────────────────────────────────
def test_expanding_marks_visible_read(js, html):
    """펼쳐서 내용을 본 문의는 읽은 것으로 친다."""
    assert "autoMarkVisibleRead" in js
    assert "autoMarkVisibleRead()" in html
    # 목록을 받은 뒤에 처리해야 대상이 잡힌다
    assert "loadInbox().then(() => autoMarkVisibleRead())" in html


def test_auto_read_skipped_when_filtering_unread(js):
    """'미읽음만' 을 보고 있는데 눈앞에서 사라지면 곤란하다."""
    block = js[js.index("async autoMarkVisibleRead()"):]
    block = block[:block.index("async markAllInboxRead()")]
    assert "if (this.inboxUnreadOnly) return;" in block


def test_auto_read_skips_when_nothing_unread(js):
    """읽을 게 없으면 요청을 보내지 않는다."""
    block = js[js.index("async autoMarkVisibleRead()"):]
    block = block[:block.index("async markAllInboxRead()")]
    assert "if (!unread.length) return;" in block


def test_badge_cleared_after_auto_read(js):
    """DB 는 바뀌었는데 뱃지가 남으면 같은 혼란이 반복된다."""
    block = js[js.index("async autoMarkVisibleRead()"):]
    block = block[:block.index("async markAllInboxRead()")]
    assert "this.stats.unread_contacts = 0" in block


def test_mark_all_button_present(html, js):
    assert "markAllInboxRead()" in html and "markAllInboxRead" in js
    # 읽을 게 없으면 버튼을 보이지 않는다
    assert 'x-show="(stats.unread_contacts || 0) > 0"' in html


def test_cache_token_bumped(html):
    m = re.search(r"kpi_spark\.js\?v=(\w+)", html)
    assert m and m.group(1) >= "20260831"
