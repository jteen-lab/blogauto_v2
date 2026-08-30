"""같은 제목 글이 둘 있어도 크롤링이 죽지 않는지 (2026-08-30).

운영에서 인생꿀팁·꿀팁대백과사전·라이프인포 3개 블로그가 연결 테스트마다
"크롤링 실패: Multiple rows were found when one or none was required" 로
막혔다. 중복 확인이 scalar_one_or_none() 이라 같은 (blog_id, title) 이
둘이면 예외가 났다.

제목이 같고 URL이 다른 글은 실제로 존재한다 — 같은 레시피를 두 번 발행한
블로그가 그렇다. 데이터가 잘못된 게 아니므로 코드가 견뎌야 한다.
"""
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.crawled_post import CrawledPost
from app.models.user import User
from app.services.crawl_service import CrawledPostData, CrawlService


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103 — 테스트 전용 shim
    return "JSON"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def blog(db):
    user = User(email="t@example.com", full_name="테스터", hashed_password="x")
    db.add(user)
    await db.flush()
    item = Blog(
        user_id=user.id, name="꿀팁대백과사전",
        url="https://fund.example.com", platform=BlogPlatform.WORDPRESS,
    )
    db.add(item)
    await db.flush()
    return item


def _data(title: str, url: str) -> CrawledPostData:
    return CrawledPostData(title=title, url=url, published_at=None)


async def _seed_duplicate(db, blog) -> None:
    """운영과 같은 상태 — 제목이 같고 URL이 다른 글 두 개."""
    for n in (1, 2):
        db.add(CrawledPost(
            blog_id=blog.id, title="소고기 미역국 레시피",
            url=f"https://fund.example.com/{n}/",
            match_status="matched", source="crawled",
        ))
    await db.flush()


@pytest.mark.asyncio
async def test_duplicate_title_does_not_break_crawl(db, blog):
    """중복이 있어도 예외 없이 넘어가고, 다시 저장하지도 않는다."""
    await _seed_duplicate(db, blog)
    svc = CrawlService(db)

    saved = await svc._save_crawled_posts(
        blog.id, [_data("소고기 미역국 레시피", "https://fund.example.com/1/")]
    )

    assert saved == 0
    total = await db.scalar(
        select(func.count(CrawledPost.id)).where(CrawledPost.blog_id == blog.id)
    )
    assert total == 2, "이미 있는 제목을 또 넣으면 안 된다"


@pytest.mark.asyncio
async def test_new_titles_still_saved_alongside_duplicates(db, blog):
    """중복 제목을 건너뛰면서 새 글은 정상 저장된다."""
    await _seed_duplicate(db, blog)
    svc = CrawlService(db)

    saved = await svc._save_crawled_posts(blog.id, [
        _data("소고기 미역국 레시피", "https://fund.example.com/1/"),
        _data("칡즙 효능과 복용법", "https://fund.example.com/9/"),
    ])

    assert saved == 1
    titles = (await db.execute(
        select(CrawledPost.title).where(CrawledPost.blog_id == blog.id)
    )).scalars().all()
    assert titles.count("소고기 미역국 레시피") == 2
    assert "칡즙 효능과 복용법" in titles


@pytest.mark.asyncio
async def test_single_existing_title_still_skipped(db, blog):
    """중복이 없을 때의 기존 동작(한 건이면 건너뛴다)도 그대로다."""
    db.add(CrawledPost(
        blog_id=blog.id, title="칡즙 효능과 복용법",
        url="https://fund.example.com/3/", match_status="matched",
        source="crawled",
    ))
    await db.flush()

    saved = await CrawlService(db)._save_crawled_posts(
        blog.id, [_data("칡즙 효능과 복용법", "https://fund.example.com/3/")]
    )
    assert saved == 0


@pytest.mark.asyncio
async def test_other_blog_same_title_is_not_treated_as_duplicate(db, blog):
    """다른 블로그의 같은 제목은 중복이 아니다(blog_id 조건이 살아 있는지)."""
    other = Blog(
        user_id=blog.user_id, name="인생꿀팁",
        url="https://life.example.com", platform=BlogPlatform.WORDPRESS,
    )
    db.add(other)
    await db.flush()
    await _seed_duplicate(db, blog)

    saved = await CrawlService(db)._save_crawled_posts(
        other.id, [_data("소고기 미역국 레시피", "https://life.example.com/1/")]
    )
    assert saved == 1
