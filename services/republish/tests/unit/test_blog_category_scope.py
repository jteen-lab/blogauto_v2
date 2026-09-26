"""블로그가 쓰는 카테고리 + 카테고리 열 정렬.

고친 것(2026-09-26):
  * 정식제목 탭에 블로그의 카테고리가 적혀 있지 않아, 왜 어떤 제목이
    보이고 어떤 제목이 빠지는지 알 수 없었다.
  * 카테고리 열을 눌러도 가나다 순으로 서지 않았다 — 화면은
    sort_field=category 를 보내는데 서버가 그 이름을 몰라 생성일
    정렬로 되돌아갔다.

'카테고리 밖' 목록은 만들었다가 되돌렸다(2026-09-26). 독립포스트는
카테고리가 바뀌면 다시 불러오므로 분류가 틀린 제목이 남지 않는다.
정리가 필요한 자리는 **발행대기 글**이고, 그건 따로 검토한다.
"""
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, SubTopic, Topic
from app.models.title import MainTitle
from app.models.user import User
from app.services.titles import blog_scope

ROOT = pathlib.Path(__file__).resolve().parents[2]


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


async def _seed(db: AsyncSession):
    """블로그는 '이사 비용' 하나만 쓴다. 나머지는 카테고리 밖이다."""
    me = User(email="me@x.com", hashed_password="x")
    db.add(me); await db.flush()
    blog = Blog(user_id=me.id, name="이사노트", url="https://a",
                platform=BlogPlatform.BLOGGER)
    db.add(blog); await db.flush()

    moving = Topic(user_id=me.id, name="이사/청소", order=1)
    health = Topic(user_id=me.id, name="건강/의학", order=0)
    db.add_all([moving, health]); await db.flush()
    cost = SubTopic(topic_id=moving.id, name="이사 비용", order=0)
    clean = SubTopic(topic_id=moving.id, name="청소", order=1)
    diet = SubTopic(topic_id=health.id, name="다이어트", order=0)
    db.add_all([cost, clean, diet]); await db.flush()

    db.add(BlogCategory(blog_id=blog.id, topic_id=moving.id,
                        subtopic_id=cost.id))
    db.add_all([
        MainTitle(title="안-이사 견적", topic_id=moving.id,
                  subtopic_id=cost.id, status="available"),
        MainTitle(title="밖-청소 요령", topic_id=moving.id,
                  subtopic_id=clean.id, status="available"),
        MainTitle(title="밖-다이어트 식단", topic_id=health.id,
                  subtopic_id=diet.id, status="available"),
        MainTitle(title="밖-분류 없는 제목", status="available"),
    ])
    await db.commit()
    return blog, {"moving": moving, "health": health,
                  "cost": cost, "clean": clean, "diet": diet}


async def _titles(db, condition):
    rows = (await db.execute(
        select(MainTitle.title).where(condition).order_by(MainTitle.id)
    )).all()
    return [r[0] for r in rows]


@pytest.mark.asyncio
class TestScope:
    async def test_안쪽은_블로그가_쓰는_카테고리뿐(self, db):
        blog, _ = await _seed(db)
        inside = await blog_scope.inside_filter(db, blog.id)
        assert await _titles(db, inside) == ["안-이사 견적"]

    async def test_카테고리를_안_걸면_제한도_없다(self, db):
        """카테고리 미설정 블로그는 예전처럼 전체가 보인다."""
        me = User(email="o@x.com", hashed_password="x")
        db.add(me); await db.flush()
        bare = Blog(user_id=me.id, name="맨블로그", url="https://b",
                    platform=BlogPlatform.BLOGGER)
        db.add(bare); await db.commit()
        assert await blog_scope.inside_filter(db, bare.id) is None

    async def test_주제만_걸어도_동작한다(self, db):
        """하위주제 없이 주제만 지정한 카테고리."""
        blog, cats = await _seed(db)
        db.add(BlogCategory(blog_id=blog.id, topic_id=cats["health"].id,
                            subtopic_id=None))
        await db.commit()
        inside = await blog_scope.inside_filter(db, blog.id)
        got = await _titles(db, inside)
        # 주제만 걸어 두면 그 주제의 제목은 하위주제와 상관없이 안쪽이다
        assert "밖-다이어트 식단" in got and "안-이사 견적" in got
        # 같은 주제라도 걸지 않은 하위주제는 안쪽이 아니다
        assert "밖-청소 요령" not in got and "밖-분류 없는 제목" not in got


class TestCategorySortContract:
    """화면이 보내는 이름과 서버가 아는 이름이 같아야 한다."""

    def test_화면은_category_를_보낸다(self):
        tmpl = (ROOT / "app/templates/collection/_titles_main.html"
                ).read_text(encoding="utf-8")
        assert "sortMainTitles('category')" in tmpl

    def test_정식제목_목록이_그_이름을_안다(self):
        src = (ROOT / "app/routers/titles.py").read_text(encoding="utf-8")
        assert '"category"' in src and "CATEGORY_SORT_FIELDS" in src
        # 이름으로 세운다(번호가 아니라)
        assert "Topic.name" in src and "SubTopic.name" in src

    def test_임시제목_목록도_이름으로_센다(self):
        src = (ROOT / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert "TempTitle.topic_id,  # 카테고리 정렬" not in src, \
            "번호로 정렬하면 가나다 순이 되지 않는다"
        assert 'sort_field in ("category", "category_path"' in src

    def test_블로그_선택_화면도_카테고리로_센다(self):
        src = (ROOT / "app/routers/titles.py").read_text(encoding="utf-8")
        merged = src[src.index("def sort_key"):src.index("combined = [")]
        assert "CATEGORY_SORT_FIELDS" in merged
        assert "category_path" in merged


class TestBlogCategoryDisplay:
    def test_화면에_카테고리_목록이_있다(self):
        tmpl = (ROOT / "app/templates/collection/_titles_main.html"
                ).read_text(encoding="utf-8")
        assert "이 블로그의 카테고리" in tmpl
        idx = (ROOT / "app/templates/collection/index.html"
               ).read_text(encoding="utf-8")
        assert "loadBlogCategories()" in idx

    def test_카테고리_밖_목록은_되돌렸다(self):
        """되돌린 기능이 슬그머니 되살아나지 않게 못 박는다."""
        for rel in ("app/routers/titles.py", "app/routers/blogs.py",
                    "app/templates/collection/_titles_main.html",
                    "app/templates/collection/index.html",
                    "app/services/titles/blog_scope.py"):
            assert "off_category" not in (ROOT / rel).read_text(
                encoding="utf-8"), rel


class TestEmptyCategoryGoesLast:
    """오름차순 첫 화면이 '(없음)' 수천 건으로 차면 정렬이 안 된 것처럼 보인다.

    실측(2026-09-26 서버): 분류 없는 정식제목이 수천 건 있어, 이름 정렬만
    하면 오름차순에서 그것들이 전부 앞을 차지했다.
    """

    def test_정식제목은_방향과_무관하게_뒤로_보낸다(self):
        src = (ROOT / "app/routers/titles.py").read_text(encoding="utf-8")
        assert "empty_last" in src
        assert "empty_last.asc()" in src, "방향을 따라가면 안 된다"

    def test_통합_목록도_분류_없는_행을_뒤로(self):
        src = (ROOT / "app/routers/titles.py").read_text(encoding="utf-8")
        block = src[src.index("# 9) 통합 정렬"):src.index("# 10)")]
        assert "named + bare" in block

    def test_임시제목도_같게(self):
        src = (ROOT / "app/routers/data_titles.py").read_text(encoding="utf-8")
        assert "empty_last" in src
