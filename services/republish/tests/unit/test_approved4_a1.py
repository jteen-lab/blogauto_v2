"""승인 4곳 A1(2026-11-02) — 되먹임 빼기 · 검색량 제목 먼저 · 보류 많은 제목 빼기 · 다음 제목 10개.

꿀팁대백과 10/30~: 관문 다음 제목이 매번 1937(산초 효능, 보류 13회)로 가서 0편.
4곳 모두 10/25~: 성장 프로파일 2 를 색인 되먹임이 min(2,1)=1 로 덮어씀.
순서도: docs/flowcharts/approved4_a1_volume.md
"""
import asyncio
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, SubTopic, Topic
from app.models.title import MainTitle
from app.models.user import User
from app.services.generation import gate_retry as gr
from app.services.generation import title_pick_order as pick
from app.services.generation.index_feedback import exempt
from app.services.generation.inventory_trigger import InventoryTrigger

ROOT = pathlib.Path(__file__).resolve().parents[2]
A1 = {"title_pick": {"prefer_source": ["keyword_module"], "skip_held_count": 3}}


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103
    return "JSON"


@pytest_asyncio.fixture
async def ctx():
    """블로그 하나 + 맡은 하위주제 하나 + 제목 넷(옛 수집 2·보류 13회 1·검색량 1)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        user = User(email="a@example.com", full_name="t", hashed_password="x")
        db.add(user)
        await db.flush()
        blog = Blog(user_id=user.id, name="꿀팁대백과", url="https://x.com",
                    platform=BlogPlatform.WORDPRESS)
        topic = Topic(name="음식", user_id=user.id)
        db.add_all([blog, topic])
        await db.flush()
        sub = SubTopic(topic_id=topic.id, name="레시피")
        db.add(sub)
        await db.flush()
        db.add(BlogCategory(blog_id=blog.id, topic_id=topic.id, subtopic_id=sub.id, is_active=True))
        old = datetime.now(timezone.utc) - timedelta(days=200)
        rows = [("옛 수집 1", "transfer", 0, old), ("옛 수집 2", "transfer", 0, old),
                ("산초 효능", "transfer", 13, old - timedelta(days=1)),
                ("검색량 제목", "keyword_module", 0, datetime.now(timezone.utc))]
        for title, src, held, at in rows:
            db.add(MainTitle(title=title, subtopic_id=sub.id, topic_id=topic.id, source=src,
                             hold_count=held, status="available", created_at=at))
        await db.flush()
        yield db, blog


class TestPickOpts:
    def test_off_without_switch(self):
        assert pick.pick_opts({}).active is False
        assert pick.pick_opts({"title_pick": "x"}).active is False

    def test_reads_switch(self):
        o = pick.pick_opts(A1)
        assert o.prefer_sources == ("keyword_module",) and o.skip_held_count == 3


class TestInventoryOrder:
    @pytest.mark.asyncio
    async def test_old_order_without_switch(self, ctx):
        """나머지 10곳 — 예전 그대로 오래된 순(보류 13회 제목이 맨 앞)."""
        db, blog = ctx
        ts = await InventoryTrigger(db).find_available_titles(blog.id, limit=10, module_settings={})
        assert ts[0].title == "산초 효능" and len(ts) == 4

    @pytest.mark.asyncio
    async def test_keyword_first_and_held_out(self, ctx):
        db, blog = ctx
        ts = await InventoryTrigger(db).find_available_titles(blog.id, limit=10, module_settings=A1)
        assert ts[0].title == "검색량 제목"
        assert "산초 효능" not in [t.title for t in ts]

    @pytest.mark.asyncio
    async def test_dispatch_pick_prefers_keyword(self, ctx):
        db, blog = ctx
        t = await InventoryTrigger(db)._find_available_title(blog.id, A1)
        assert t.title == "검색량 제목"

    @pytest.mark.asyncio
    async def test_count_excludes_held(self, ctx):
        db, blog = ctx
        tr = InventoryTrigger(db)
        assert await tr.count_available_titles(blog.id, {}) == 4
        assert await tr.count_available_titles(blog.id, A1) == 3


class TestGateRetryMax:
    def test_default_three_and_module_override(self):
        assert gr.max_tries({}) == 3
        assert gr.max_tries({"gate_retry_max": 10}) == 10
        assert gr.max_tries({"gate_retry_max": 99}) == gr.MAX_CAP
        assert gr.max_tries({"gate_retry_max": "x"}) == 3

    def test_tenth_try_allowed_eleventh_not(self):
        class Tr:
            async def find_available_titles(self, blog_id, limit=5, module_settings=None):
                return [SimpleNamespace(id=i, search_volume=None, search_volume_at=None) for i in range(1, 30)]

        class Ex:
            inventory_trigger = Tr()
            calls = []

            async def execute_for_blog(self, module, blog, stage_params=None, force_title_id=None,
                                       scope_gate=True, _tried=()):
                self.calls.append(force_title_id)
                return {"success": True, "skipped": False}

        blog = SimpleNamespace(id=8, name="꿀팁대백과")
        s = {"gate_retry_max": 10}
        ex = Ex()
        asyncio.run(gr.next_title(ex, None, blog, None, False, s, tuple(range(1, 10)), "관문"))
        assert ex.calls == [10]
        res = asyncio.run(gr.next_title(ex, None, blog, None, False, s, tuple(range(1, 11)), "관문"))
        assert res["skipped"] is True and ex.calls == [10]


class TestIndexFeedbackExempt:
    def test_exempt_only_when_true(self):
        assert exempt({"index_feedback_exempt": True}) is True
        assert exempt({"index_feedback_exempt": "true"}) is False
        assert exempt({}) is False and exempt(None) is False

    def test_publish_uses_exempt(self):
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
        assert "not _idx_exempt(gp_settings)" in src


class TestMatchedDoesNotCrowdOut:
    @pytest.mark.asyncio
    async def test_keyword_first_even_when_matched_fill_limit(self, ctx):
        """굿팁꿀팁·꿀팁대백과 — 손으로 넣은 매칭 제목 31개가 칸을 다 채워 검색량 제목이 안 보였다."""
        db, blog = ctx
        sub_id = (await db.execute(__import__("sqlalchemy").select(MainTitle.subtopic_id))).scalars().first()
        for i in range(5):
            db.add(MainTitle(title=f"매칭 {i}", subtopic_id=sub_id, source="manual",
                             matched_blog_ids=str(blog.id), status="available"))
        await db.flush()
        ts = await InventoryTrigger(db).find_available_titles(blog.id, limit=3, module_settings=A1)
        assert ts[0].title == "검색량 제목" and len(ts) == 3
        ts = await InventoryTrigger(db).find_available_titles(blog.id, limit=3, module_settings={})
        assert all(t.title.startswith("매칭") for t in ts)
