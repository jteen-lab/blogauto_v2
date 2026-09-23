"""글 소스 네 갈래 — 순서 보존·서점 제외·임시제목 검색.

고친 것(2026-09-23):
  * 지식iN·카페를 최신순으로 부르고, 받은 뒤 다시 정렬하고, 질문이
    아닌 것을 버려서 네이버 화면과 순서가 달랐다.
  * 웹문서(webkr)에 서점·오픈마켓이 섞여 글감으로 쓸 수 없었다.
  * 지식iN·카페가 한 버튼이라 어느 쪽 몇 번째인지 알 수 없었다.
"""
import json
import pathlib
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.category import BlogCategory, Keyword, SubTopic, Topic
from app.models.title import TempTitle
from app.models.user import User
from app.services.keyword_lab.sources import community
from app.services.keyword_lab.sources.base import SRC_NAVER_CAFE, SRC_NAVER_KIN
from app.services.workbench import sources as source_svc
from app.services.workbench import web_sources
from app.services.workbench.temp_titles import search_temp_titles

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = (ROOT / "app/static/js/workbench-sources.js").read_text(encoding="utf-8")


class TestQuestionOrder:
    """네이버가 준 순서가 곧 화면 순서다."""

    ITEMS = [
        {"title": "포장이사 최저가 이벤트 문의", "description": "무료견적"},
        {"title": "15평 이사 견적 얼마나 나올까요", "description": "3층인데요"},
        {"title": "이사 비용 정리", "description": "그냥 글"},
    ]

    def test_keep_all_은_버리지_않고_표시만_한다(self):
        rows = community._to_questions(self.ITEMS, "이사", SRC_NAVER_KIN,
                                       keep_all=True)
        assert [r.title for r in rows] == [i["title"] for i in self.ITEMS]
        assert rows[0].extra["is_promo"] is True
        assert rows[2].extra["is_question"] is False

    def test_수집기는_그대로_걸러_쓴다(self):
        """화면 때문에 수집 품질을 낮추지 않는다."""
        rows = community._to_questions(self.ITEMS, "이사", SRC_NAVER_KIN)
        assert [r.title for r in rows] == [self.ITEMS[1]["title"]]

    @pytest.mark.asyncio
    async def test_화면은_받은_순서를_지키고_순위를_붙인다(self, monkeypatch):
        rows = community._to_questions(self.ITEMS, "이사", SRC_NAVER_KIN,
                                       keep_all=True)
        seen = {}

        async def fake_collect(settings, seeds, source, limit_per_seed=30,
                               start=1, sort="date", keep_all=False):
            seen.update({"sort": sort, "keep_all": keep_all,
                         "source": source})
            return rows

        monkeypatch.setattr(community, "collect_questions", fake_collect)
        monkeypatch.setattr(community, "is_configured", lambda s: True)
        got = await source_svc.search_questions(
            object(), "이사 견적", [SRC_NAVER_KIN], limit=10, start=1)

        assert [i["title"] for i in got["items"]] == [i["title"]
                                                     for i in self.ITEMS]
        assert [i["rank"] for i in got["items"]] == [1, 2, 3]
        assert got["items"][0]["is_promo"] is True
        # 네이버 화면 기본은 정확도순이고, 버리지 않고 받는다
        assert seen == {"sort": "sim", "keep_all": True,
                        "source": SRC_NAVER_KIN}

    @pytest.mark.asyncio
    async def test_한_소스만_부를_수_있다(self, monkeypatch):
        """지식iN 과 카페가 갈라져야 몇 번째인지 셀 수 있다."""
        called = []

        async def fake_collect(settings, seeds, source, **kw):
            called.append(source)
            return []

        monkeypatch.setattr(community, "collect_questions", fake_collect)
        monkeypatch.setattr(community, "is_configured", lambda s: True)
        await source_svc.search_questions(object(), "이사", [SRC_NAVER_CAFE])
        assert called == [SRC_NAVER_CAFE]


class TestWebSourceJunk:
    """웹문서는 웹사이트 색인이라 서점·오픈마켓이 위를 차지한다."""

    @pytest.mark.parametrize("link", [
        "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=1",
        "http://m.gmarket.co.kr/n/best",
        "https://smartstore.naver.com/abc/products/1",
        "https://prod.danawa.com/info/?pcode=1",
    ])
    def test_글감이_못_되는_곳은_뺀다(self, link):
        assert web_sources.is_junk(link) is True

    @pytest.mark.parametrize("link", [
        "https://blog.naver.com/abc/223",
        "https://miso.kr/guide/1",
        "https://namu.wiki/w/다이어트",
        "https://easylaw.go.kr/x",
    ])
    def test_읽을_수_있는_글은_남긴다(self, link):
        assert web_sources.is_junk(link) is False

    def test_도메인만_뽑는다(self):
        assert web_sources.host_of("https://www.Example.com/a?b=1") == "example.com"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[n] for n in (
        "users", "blogs", "topics", "subtopics", "keywords",
        "blog_categories", "temp_titles")]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def _seed(db: AsyncSession):
    me = User(email="me@x.com", hashed_password="x")
    db.add(me); await db.flush()
    blog = Blog(user_id=me.id, name="이사노트", url="https://a",
                platform=BlogPlatform.BLOGGER)
    other_blog = Blog(user_id=me.id, name="딴블로그", url="https://b",
                      platform=BlogPlatform.BLOGGER)
    db.add_all([blog, other_blog]); await db.flush()
    topic = Topic(user_id=me.id, name="이사")
    db.add(topic); await db.flush()
    mine = SubTopic(topic_id=topic.id, name="이사 견적·비용")
    theirs = SubTopic(topic_id=topic.id, name="남의 주제")
    db.add_all([mine, theirs]); await db.flush()
    kw = Keyword(subtopic_id=mine.id, name="포장+이사")
    db.add(kw); await db.flush()
    db.add_all([
        BlogCategory(blog_id=blog.id, topic_id=topic.id, subtopic_id=mine.id),
        BlogCategory(blog_id=other_blog.id, topic_id=topic.id,
                     subtopic_id=theirs.id),
    ])

    def temp(title, subtopic, status="new", kw_id=None, url="https://p/1"):
        return TempTitle(title=title, source_blog_url="https://src",
                         source_post_url=url, collection_stage="keyword_search",
                         status=status, subtopic_id=subtopic.id,
                         matched_keyword_id=kw_id)

    db.add_all([
        temp("포장이사 비용 총정리", mine),            # 띄어쓰기 없는 제목
        temp("이사 준비물 목록", mine, kw_id=kw.id),   # 제목은 안 맞고 키워드가 맞음
        temp("에어컨 청소 후기", mine),                # 안 맞음
        temp("포장이사 옮긴 제목", mine, status="moved"),  # 이미 정식제목
        temp("포장이사 남의 주제", theirs),            # 다른 블로그의 주제
    ])
    await db.commit()
    return me, blog


@pytest.mark.asyncio
class TestTempTitleSearch:
    async def test_하위주제_안에서_검색어와_맞는_것만(self, db):
        """'포장 이사'(칩) → '포장이사'(제목) · '포장+이사'(키워드) 다 맞다.

        옮긴 것과 남의 주제, 상관없는 제목은 빠진다.
        """
        me, blog = await _seed(db)
        got = await search_temp_titles(db, me.id, [blog.id], "포장 이사")
        titles = sorted(i["title"] for i in got["items"])
        assert titles == ["이사 준비물 목록", "포장이사 비용 총정리"]
        assert got["items"][0]["source"] == "temp_title"
        assert got["items"][0]["link"] == "https://p/1"

    async def test_풀에_적힌_형태로_찾아도_같다(self, db):
        me, blog = await _seed(db)
        got = await search_temp_titles(db, me.id, [blog.id], "포장+이사")
        titles = sorted(i["title"] for i in got["items"])
        assert titles == ["이사 준비물 목록", "포장이사 비용 총정리"]

    async def test_블로그를_안_담으면_찾지_않는다(self, db):
        me, _ = await _seed(db)
        got = await search_temp_titles(db, me.id, [], "포장 이사")
        assert got["items"] == [] and "블로그를 먼저" in got["error"]

    async def test_더_보기는_남았을_때만(self, db):
        me, blog = await _seed(db)
        first = await search_temp_titles(db, me.id, [blog.id], "포장 이사",
                                         limit=1)
        assert len(first["items"]) == 1 and first["next_start"] == 2
        second = await search_temp_titles(db, me.id, [blog.id], "포장 이사",
                                          limit=1, start=2)
        assert second["next_start"] is None   # 두 건이 끝이다
        assert (second["items"][0]["title"]
                != first["items"][0]["title"])


def _js(script: str) -> dict:
    program = JS + """
const self = sourcePart();
self.blogs = [{id: 3}, {id: 7}];
""" + script + """
console.log(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", program], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestModeRouting:
    def test_모드마다_다른_길로_부른다(self):
        out = _js("""
const out = {};
for (const m of ['kin', 'cafe', 'web', 'temp']) {
    self.sourceMode = m;
    out[m] = self._sourceUrl('이사 견적', 1);
}
""")
        assert "sources?" in out["kin"] and "naver_kin" in out["kin"]
        assert "naver_cafe" in out["cafe"]
        assert "web-sources?" in out["web"]
        assert "temp-titles?" in out["temp"] and "blog_ids=3,7" in out["temp"]

    def test_정확도순이_기본이다(self):
        out = _js("const out = {url: self._sourceUrl('이사', 1),"
                  " sort: self.sourceSort};")
        assert out["sort"] == "sim" and "sort=sim" in out["url"]

    def test_모드_이름이_시트_제목이_된다(self):
        out = _js("""
self.sourceMode = 'temp';
const out = {temp: self.sourceModeLabel(), kin: self.sourceModeLabel('kin')};
""")
        assert out == {"temp": "임시제목", "kin": "지식iN 질문"}
