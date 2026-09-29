"""자동 생성 블로그 카테고리 관문 (2026-09-29).

수작남(blog 13)에 카테고리 밖 제목(부가가치세·누수 등)이 발행대기로
쌓였다. 자동 생성도 정식제목 목록과 같은 규칙으로 한 번 더 거른다.
순서도: docs/flowcharts/blog_category_scope.md (자동 생성 관문)
"""
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, SubTopic, Topic
from app.models.title import MainTitle
from app.models.user import User
from app.services.generation.flow_generate_executor import (
    FlowGenerateExecutor,
)
from app.services.titles.blog_scope import title_inside


class TestTitleInside:
    def test_카테고리_없으면_제한_없음(self):
        assert title_inside(set(), set(), None, None) is True
        assert title_inside(set(), set(), 9, 99) is True

    def test_하위주제_일치(self):
        assert title_inside({44}, set(), 8, 44) is True

    def test_다른_하위주제는_밖(self):
        assert title_inside({44, 50}, set(), 18, 91) is False

    def test_미분류는_밖(self):
        assert title_inside({44}, set(), None, None) is False

    def test_주제만_지정(self):
        assert title_inside(set(), {5}, 5, 777) is True
        assert title_inside(set(), {5}, 6, None) is False

    def test_같은_주제라도_걸지_않은_하위주제는_밖(self):
        """topic 폴백으로 뽑힌 제목도 블로그 규칙으로는 밖이다."""
        assert title_inside({44}, set(), 8, 50) is False


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[n] for n in (
        "users", "blogs", "topics", "subtopics", "blog_categories",
        "main_titles")]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def _seed(db):
    me = User(email="me@x.com", hashed_password="x")
    db.add(me); await db.flush()
    blog = Blog(user_id=me.id, name="수작남", url="https://a",
                platform=BlogPlatform.BLOGGER)
    bare = Blog(user_id=me.id, name="맨블로그", url="https://b",
                platform=BlogPlatform.BLOGGER)
    db.add_all([blog, bare]); await db.flush()
    life = Topic(user_id=me.id, name="생활 정보", order=0)
    tax = Topic(user_id=me.id, name="세금/절세", order=1)
    db.add_all([life, tax]); await db.flush()
    info = SubTopic(topic_id=life.id, name="생활 정보", order=0)
    vat = SubTopic(topic_id=tax.id, name="부가가치세", order=0)
    db.add_all([info, vat]); await db.flush()
    db.add(BlogCategory(blog_id=blog.id, topic_id=life.id,
                        subtopic_id=info.id))
    t_in = MainTitle(title="안-생활 팁", topic_id=life.id,
                     subtopic_id=info.id, status="available")
    t_out = MainTitle(title="밖-폐업 후 부가가치세", topic_id=tax.id,
                      subtopic_id=vat.id, status="available")
    t_none = MainTitle(title="밖-윗집 누수 배상", status="available")
    db.add_all([t_in, t_out, t_none])
    await db.commit()
    return blog, bare, t_in, t_out, t_none


@pytest.mark.asyncio
class TestExecutorGate:
    async def test_카테고리_안만_통과(self, db):
        blog, _, t_in, t_out, t_none = await _seed(db)
        ex = FlowGenerateExecutor(db, 1)
        assert await ex._in_blog_scope(blog, t_in) is True
        assert await ex._in_blog_scope(blog, t_out) is False
        assert await ex._in_blog_scope(blog, t_none) is False

    async def test_카테고리_없는_블로그는_그대로(self, db):
        _, bare, _, t_out, t_none = await _seed(db)
        ex = FlowGenerateExecutor(db, 1)
        assert await ex._in_blog_scope(bare, t_out) is True
        assert await ex._in_blog_scope(bare, t_none) is True

    async def test_자동경로는_id로_제목을_읽는다(self, db):
        """자동 경로는 제목 객체가 없어 변형이 주제를 못 봤다 — 읽어 넘긴다."""
        _, _, t_in, _, _ = await _seed(db)
        ex = FlowGenerateExecutor(db, 1)
        got = await ex._load_title(None, t_in.id)
        assert got is not None and got.topic_id == t_in.topic_id
        same = SimpleNamespace(topic_id=1)
        assert await ex._load_title(same, t_in.id) is same
        assert await ex._load_title(None, 0) is None


def test_작업대는_관문을_건너뛴다():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[2]
           / "app/services/workbench/runner.py").read_text(encoding="utf-8")
    assert "scope_gate=False" in src
