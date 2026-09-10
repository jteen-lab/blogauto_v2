"""재고를 세는 기준과 발행이 꺼내는 기준이 어긋나면 교착이 난다.

수작남 실측: 재고 3건이 전부 블로그 카테고리 밖 하위주제(문화 정보 2 ·
월급 관리 1)였다.

    생성 → "재고 충분 (3/3)" 으로 건너뜀
    발행 → "발행할 글 없음" 으로 다음 생성을 기다림

둘 다 상대를 기다려 8/31 발행을 끝으로 열흘간 아무것도 하지 않았다.
발행할 수 없는 글은 재고가 아니다.
"""
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, SubTopic, Topic
from app.models.crawled_post import CrawledPost
from app.models.title import MainTitle
from app.models.user import User
from app.services.generation.inventory_manager import InventoryManager
from app.services.generation.inventory_trigger import InventoryTrigger


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103
    return "JSON"


@pytest_asyncio.fixture
async def ctx():
    """블로그 하나 + 담당 하위주제(가격 비교) + 담당 밖 하위주제(문화 정보)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession,
                               expire_on_commit=False)
    async with maker() as db:
        user = User(email="s@example.com", full_name="t", hashed_password="x")
        db.add(user)
        await db.flush()
        blog = Blog(user_id=user.id, name="수작남", url="https://x.com",
                    platform=BlogPlatform.BLOGGER)
        topic = Topic(name="생활", user_id=user.id)
        db.add_all([blog, topic])
        await db.flush()
        mine = SubTopic(topic_id=topic.id, name="가격 비교")
        outside = SubTopic(topic_id=topic.id, name="문화 정보")
        db.add_all([mine, outside])
        await db.flush()
        yield db, blog, topic, mine, outside
    await engine.dispose()


async def _stock(db, blog, subtopic, count, matched=True):
    """재고 글을 만든다. matched=False 면 매칭 정보가 없는 옛 글."""
    title_id = None
    if matched:
        title = MainTitle(title=f"{subtopic.name} 글", subtopic_id=subtopic.id)
        db.add(title)
        await db.flush()
        title_id = title.id
    for i in range(count):
        db.add(CrawledPost(
            blog_id=blog.id, title=f"{subtopic.name}{i}", source="generated",
            matched_main_title_id=title_id,
        ))
    await db.flush()


async def _assign(db, blog, subtopic):
    db.add(BlogCategory(blog_id=blog.id, topic_id=subtopic.topic_id,
                        subtopic_id=subtopic.id, is_active=True))
    await db.flush()


class TestDeadlock:
    """수작남이 겪은 그대로를 재현한다."""

    @pytest.mark.asyncio
    async def test_outside_category_stock_is_not_inventory(self, ctx):
        """카테고리 밖 글 3건은 재고 0 이어야 생성이 다시 돈다."""
        db, blog, _, mine, outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, outside, 3)

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        assert count == 0, "발행할 수 없는 글을 재고로 세면 생성이 굶는다"

    @pytest.mark.asyncio
    async def test_counting_matches_publishing(self, ctx):
        """세는 쪽과 꺼내는 쪽이 같은 답을 내야 한다."""
        db, blog, _, mine, outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, outside, 3)

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        post = await InventoryManager(db).get_post_for_publish(blog.id)
        assert (count > 0) == (post is not None)

    @pytest.mark.asyncio
    async def test_generation_needed_when_stock_is_unpublishable(self, ctx):
        """재고 3/3 으로 건너뛰던 자리에서 생성이 필요하다고 나와야 한다."""
        db, blog, _, mine, outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, outside, 3)

        result = await InventoryTrigger(db).check_inventory(
            blog.id, min_inventory=3)
        assert result.current_inventory == 0


class TestNoOverGeneration:
    """반대로 과잉 생성이 되면 안 된다."""

    @pytest.mark.asyncio
    async def test_category_stock_is_counted(self, ctx):
        """담당 카테고리 글은 그대로 재고다."""
        db, blog, _, mine, _outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, mine, 3)

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_no_blog_category_counts_everything(self, ctx):
        """카테고리를 안 정한 블로그는 전부 발행 대상이다.

        여기서 0 을 돌려주면 무한 생성이 된다.
        """
        db, blog, _, _mine, outside = ctx
        await _stock(db, blog, outside, 3)

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_unmatched_posts_still_count(self, ctx):
        """매칭 정보가 없는 옛 글은 발행 대상이므로 재고로 센다."""
        db, blog, _, mine, outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, outside, 2, matched=False)

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_published_posts_are_excluded(self, ctx):
        """이미 발행된 글은 재고가 아니다."""
        from datetime import datetime, timezone

        db, blog, _, mine, _outside = ctx
        await _assign(db, blog, mine)
        title = MainTitle(title="발행됨", subtopic_id=mine.id)
        db.add(title)
        await db.flush()
        db.add(CrawledPost(
            blog_id=blog.id, title="이미 발행", source="generated",
            matched_main_title_id=title.id,
            published_at=datetime.now(timezone.utc),
        ))
        await db.flush()

        count = await InventoryTrigger(db)._get_inventory_count(blog.id)
        assert count == 0


class TestMixed:
    @pytest.mark.asyncio
    async def test_only_publishable_part_is_counted(self, ctx):
        """담당 2건 + 담당 밖 3건 → 재고는 2건."""
        db, blog, _, mine, outside = ctx
        await _assign(db, blog, mine)
        await _stock(db, blog, mine, 2)
        await _stock(db, blog, outside, 3)

        publishable, total = await InventoryTrigger(db)._publishable_inventory(
            blog.id)
        assert (publishable, total) == (2, 5)
