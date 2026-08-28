"""발행 보류 사유 진단 테스트 (2026-08-28 회귀).

수작남이 사흘간 "보류 (발행 가능 글 없음)" 만 반복했는데, 실제로는 재고가 3건
있었고 블로그 카테고리에 없는 하위주제라 걸러지고 있었다. 두 상황은 조치가
완전히 다른데 로그가 같아 원인을 알 수 없었다.
"""
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import SubTopic, Topic
from app.models.crawled_post import CrawledPost
from app.models.title import MainTitle
from app.models.user import User
from app.services.generation.inventory_manager import InventoryManager


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103
    return "JSON"


@pytest_asyncio.fixture
async def ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        user = User(email="b@example.com", full_name="t", hashed_password="x")
        db.add(user)
        await db.flush()
        blog = Blog(
            user_id=user.id, name="수작남", url="https://x.com",
            platform=BlogPlatform.BLOGGER,
        )
        topic = Topic(name="쇼핑/리뷰", user_id=user.id)
        db.add_all([blog, topic])
        await db.flush()
        sub = SubTopic(topic_id=topic.id, name="가격 비교")
        db.add(sub)
        await db.flush()
        yield db, blog, sub
    await engine.dispose()


@pytest.mark.asyncio
async def test_no_inventory_returns_none(ctx):
    """재고가 아예 없으면 사유가 없다 — 기존 메시지를 그대로 쓴다."""
    db, blog, _ = ctx
    assert await InventoryManager(db).describe_publish_block(blog.id) is None


@pytest.mark.asyncio
async def test_blocked_inventory_names_the_subtopic(ctx):
    """재고가 있는데 막혔으면 어떤 하위주제 때문인지 알려준다."""
    db, blog, sub = ctx
    title = MainTitle(title="냄비밥", subtopic_id=sub.id)
    db.add(title)
    await db.flush()
    for i in range(3):
        db.add(CrawledPost(
            blog_id=blog.id, title=f"글{i}", source="generated",
            matched_main_title_id=title.id,
        ))
    await db.flush()

    reason = await InventoryManager(db).describe_publish_block(blog.id)
    assert reason is not None
    assert "가격 비교(3)" in reason
    assert "재고 3건" in reason
    assert "블로그 설정" in reason  # 조치 방법까지 안내


@pytest.mark.asyncio
async def test_published_posts_are_not_counted(ctx):
    """이미 발행된 글은 막힌 재고가 아니다."""
    from datetime import datetime, timezone

    db, blog, sub = ctx
    title = MainTitle(title="발행됨", subtopic_id=sub.id)
    db.add(title)
    await db.flush()
    db.add(CrawledPost(
        blog_id=blog.id, title="이미 발행", source="generated",
        matched_main_title_id=title.id,
        published_at=datetime.now(timezone.utc),
    ))
    await db.flush()

    assert await InventoryManager(db).describe_publish_block(blog.id) is None
