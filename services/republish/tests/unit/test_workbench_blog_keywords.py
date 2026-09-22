"""모듈 테스터 — 담은 블로그의 하위 주제·키워드 트리."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, Keyword, SubTopic, Topic
from app.models.user import User
from app.services.workbench.blog_keywords import keywords_for_blogs


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[n] for n in (
        "users", "blogs", "topics", "subtopics", "keywords", "blog_categories")]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def _seed(db: AsyncSession):
    """사용자 둘, 블로그 셋, 주제 하나에 하위 주제 둘(한쪽엔 키워드 없음)."""
    me = User(email="me@x.com", hashed_password="x")
    other = User(email="o@x.com", hashed_password="x")
    db.add_all([me, other]); await db.flush()

    b1 = Blog(user_id=me.id, name="이사노트", url="https://a", platform=BlogPlatform.BLOGGER)
    b2 = Blog(user_id=me.id, name="둘째", url="https://b", platform=BlogPlatform.BLOGGER)
    b_other = Blog(user_id=other.id, name="남의것", url="https://c", platform=BlogPlatform.BLOGGER)
    db.add_all([b1, b2, b_other]); await db.flush()

    t = Topic(user_id=me.id, name="이사", order=0)
    db.add(t); await db.flush()
    s_cost = SubTopic(topic_id=t.id, name="이사 비용", order=0)
    s_empty = SubTopic(topic_id=t.id, name="키워드 없음", order=1)
    s_del = SubTopic(topic_id=t.id, name="지운 주제", order=2, is_deleted=True)
    db.add_all([s_cost, s_empty, s_del]); await db.flush()
    db.add_all([
        Keyword(subtopic_id=s_cost.id, name="포장이사 비용", order=1),
        Keyword(subtopic_id=s_cost.id, name="이사 견적", order=0),
        Keyword(subtopic_id=s_cost.id, name=" 이사 견적 ", order=5),   # 중복
        Keyword(subtopic_id=s_cost.id, name="지운 키워드", is_deleted=True),
        Keyword(subtopic_id=s_del.id, name="숨은 키워드"),
    ])
    db.add_all([
        BlogCategory(blog_id=b1.id, topic_id=t.id, subtopic_id=s_cost.id),
        BlogCategory(blog_id=b1.id, topic_id=t.id, subtopic_id=s_empty.id),
        BlogCategory(blog_id=b1.id, topic_id=t.id, subtopic_id=s_del.id),
        BlogCategory(blog_id=b1.id, topic_id=t.id, subtopic_id=s_cost.id,
                     is_active=False),
        BlogCategory(blog_id=b2.id, topic_id=t.id, subtopic_id=s_cost.id),
        BlogCategory(blog_id=b_other.id, topic_id=t.id, subtopic_id=s_cost.id),
    ])
    await db.commit()
    return me, other, b1, b2, b_other


@pytest.mark.asyncio
class TestKeywordsForBlogs:
    async def test_하위주제와_키워드가_정렬되어_온다(self, db):
        me, _, b1, _, _ = await _seed(db)
        got = await keywords_for_blogs(db, me.id, [b1.id])
        assert len(got) == 1 and got[0]["blog_name"] == "이사노트"
        subs = got[0]["subtopics"]
        assert [s["subtopic_name"] for s in subs] == ["이사 비용", "키워드 없음"]
        assert subs[0]["topic_name"] == "이사"
        # order 순, 공백·중복·삭제는 뺀다
        assert subs[0]["keywords"] == ["이사 견적", "포장이사 비용"]
        assert subs[1]["keywords"] == []

    async def test_담은_순서를_지키고_남의_블로그는_뺀다(self, db):
        me, _, b1, b2, b_other = await _seed(db)
        got = await keywords_for_blogs(db, me.id, [b2.id, b_other.id, b1.id])
        assert [g["blog_id"] for g in got] == [b2.id, b1.id]

    async def test_빈_요청은_빈_결과(self, db):
        me, *_ = await _seed(db)
        assert await keywords_for_blogs(db, me.id, []) == []
