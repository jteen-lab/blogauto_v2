"""관문에 걸려도 같은 회차에서 다음 제목 — gate_retry (2026-10-25)."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.generation import gate_retry as gr

NOW = datetime.now(timezone.utc)
ON = {"title_lead_keyword": True}


def _t(i, vol=None):
    return SimpleNamespace(id=i, search_volume=vol, search_volume_at=NOW if vol is not None else None)


class Trigger:
    def __init__(self, titles):
        self.titles = titles

    async def find_available_titles(self, blog_id, limit=5, module_settings=None):
        return self.titles


class Executor:
    """execute_for_blog 를 부른 기록만 남기는 가짜 실행기."""

    def __init__(self, titles):
        self.inventory_trigger = Trigger(titles)
        self.calls = []

    async def execute_for_blog(self, module, blog, stage_params=None, force_title_id=None,
                               scope_gate=True, _tried=()):
        self.calls.append((force_title_id, _tried))
        return {"success": True, "skipped": False, "title": force_title_id}


BLOG = SimpleNamespace(id=7, name="인생꿀팁")


def _run(ex, tried, settings=ON):
    return asyncio.run(gr.next_title(ex, None, BLOG, None, True, settings, tried, "제목 관문(타블로그중복)"))


def test_blocked_title_moves_to_next_untried():
    ex = Executor([_t(1), _t(2), _t(3)])
    res = _run(ex, (1,))
    assert res["title"] == 2 and ex.calls == [(2, (1,))]


def test_skips_titles_remembered_low_only_when_switch_on():
    ex = Executor([_t(1), _t(2, vol=5), _t(3)])
    assert _run(ex, (1,))["title"] == 3
    ex = Executor([_t(1), _t(2, vol=5), _t(3)])
    assert _run(ex, (1,), settings={})["title"] == 2


def test_stops_after_three_titles():
    ex = Executor([_t(9)])
    res = _run(ex, (1, 2, 3))
    assert res["skipped"] is True and "생성 건너뜀" in res["message"] and ex.calls == []


def test_no_more_titles_keeps_old_skip_message():
    ex = Executor([_t(1)])
    res = _run(ex, (1,))
    assert res == {"success": True, "skipped": True, "message": "제목 관문(타블로그중복) - 생성 건너뜀"}


def test_executor_routes_gate_block_through_retry():
    from pathlib import Path
    src = Path("app/services/generation/flow_generate_executor.py").read_text()
    assert "if blocked or low:" in src and "gate_retry.next_title(" in src


def test_next_title_skips_titles_outside_blog_category(monkeypatch):
    """10/26 수작남 — 다음 후보로 카테고리 밖 제목(급체 증상)을 집어 회차를 날리던 것."""
    from app.services.titles import blog_scope

    async def _sets(db, blog_id):
        return {50}, set()
    monkeypatch.setattr(blog_scope, "category_sets", _sets)
    ex = Executor([SimpleNamespace(id=2, topic_id=1, subtopic_id=99, search_volume=None, search_volume_at=None),
                   SimpleNamespace(id=3, topic_id=1, subtopic_id=50, search_volume=None, search_volume_at=None)])
    ex.db = object()
    assert _run(ex, (1,))["title"] == 3
    ex2 = Executor([SimpleNamespace(id=2, topic_id=1, subtopic_id=99, search_volume=None, search_volume_at=None)])
    ex2.db = object()
    assert _run(ex2, (1,))["skipped"] is True
