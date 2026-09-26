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


def _js(script: str, extra: str = "") -> dict:
    """화면 조각을 node 에서 그대로 돌려 본다. script 안에서 await 를 쓸 수 있다."""
    program = JS + extra + """
const self = Object.assign(sourcePart(),
    typeof blogKeywordPart === 'function' ? blogKeywordPart() : {});
self.blogs = [{id: 3}, {id: 7}];
self.$nextTick = (f) => { if (typeof f === 'function') f(); };
self.$refs = {};
(async () => {
""" + script + """
console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
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


class TestDedup:
    """네이버는 같은 글을 두 모양으로 겹쳐 준다(2026-09-26 실측).

        지식iN '이사 견적'  한 페이지 30건 안에서 제목이 같은 것 8건
                           (링크는 서로 달라 링크만으로는 못 걸러진다)
        카페  start=61     앞 페이지와 링크까지 같은 것 20건
    """

    def test_링크가_같으면_한_번만(self):
        from app.services.workbench import dedup

        rows = [{"title": "가", "link": "https://kin.naver.com/a",
                 "source": "naver_kin"},
                {"title": "나", "link": "http://www.kin.naver.com/a/",
                 "source": "naver_kin"}]
        assert [r["title"] for r in dedup.unique(rows)] == ["가"]

    def test_제목이_같으면_링크가_달라도_한_번만(self):
        from app.services.workbench import dedup

        rows = [{"title": "이사 견적 얼마", "link": "https://kin.naver.com/1",
                 "source": "naver_kin"},
                {"title": "이사  견적   얼마", "link": "https://kin.naver.com/2",
                 "source": "naver_kin"}]
        assert len(dedup.unique(rows)) == 1

    def test_출처가_다르면_남긴다(self):
        """제목만 같고 실제로는 다른 글이다."""
        from app.services.workbench import dedup

        rows = [{"title": "이사 견적", "link": "https://kin.naver.com/1",
                 "source": "naver_kin"},
                {"title": "이사 견적", "link": "https://blog.naver.com/1",
                 "source": "naver_blog"}]
        assert len(dedup.unique(rows)) == 2

    def test_앞_페이지에서_본_것도_걸러진다(self):
        from app.services.workbench import dedup

        links, titles = set(), set()
        first = [{"title": "가", "link": "https://a/1", "source": "s"}]
        dedup.unique(first, links, titles)
        again = [{"title": "가", "link": "https://a/9", "source": "s"},
                 {"title": "나", "link": "https://a/2", "source": "s"}]
        assert [r["title"] for r in dedup.unique(again, links, titles)] == ["나"]

    def test_순서는_건드리지_않는다(self):
        from app.services.workbench import dedup

        rows = [{"title": str(i), "link": f"https://a/{i}", "source": "s"}
                for i in range(5)]
        assert [r["title"] for r in dedup.unique(rows)] == list("01234")

    @pytest.mark.asyncio
    async def test_질문_검색이_겹친_것을_걸러_낸다(self, monkeypatch):
        dupes = community._to_questions([
            {"title": "이사 견적 얼마", "description": "3층인데요"},
            {"title": "이사 견적 얼마", "description": "다른 사람 글"},
            {"title": "보관이사 비용", "description": "얼마인가요"},
        ], "이사", SRC_NAVER_KIN, keep_all=True)

        async def fake_collect(settings, seeds, source, **kw):
            return dupes

        monkeypatch.setattr(community, "collect_questions", fake_collect)
        monkeypatch.setattr(community, "is_configured", lambda s: True)
        got = await source_svc.search_questions(
            object(), "이사 견적", [SRC_NAVER_KIN])
        assert [i["title"] for i in got["items"]] == ["이사 견적 얼마",
                                                     "보관이사 비용"]


class TestKeywordChipReplaces:
    """칩을 두 개 누르면 '포장 이사 보관 이사' 가 되어 결과가 사라졌다."""

    def test_마지막에_누른_키워드만_남는다(self):
        out = _js("""
self.pickBlogKeyword('포장+이사');
const first = self.sourceQuery;
self.pickBlogKeyword('보관+이사');
const out = {first, second: self.sourceQuery,
             pickedNew: self.blogKeywordPicked('보관+이사'),
             pickedOld: self.blogKeywordPicked('포장+이사')};
""", extra=(ROOT / "app/static/js/workbench-blog-keywords.js")
            .read_text(encoding="utf-8"))
        assert out == {"first": "포장 이사", "second": "보관 이사",
                       "pickedNew": True, "pickedOld": False}

    def test_손으로_적은_말도_치운다(self):
        out = _js("""
self.sourceQuery = '아무렇게나 적은 말';
self.pickBlogKeyword('포장+이사');
const out = {q: self.sourceQuery};
""", extra=(ROOT / "app/static/js/workbench-blog-keywords.js")
            .read_text(encoding="utf-8"))
        assert out == {"q": "포장 이사"}


class TestMoreButtonSkipsRepeats:
    """더 보기가 앞 결과를 또 쌓거나, 겹치기만 하고 멈추던 문제."""

    PAGES = """
self._pages = {
    1: {items: [
          {title: '가', link: 'https://a/1', source: 'naver_kin'},
          {title: '가', link: 'https://a/2', source: 'naver_kin'},
          {title: '나', link: 'https://a/3', source: 'naver_kin'}],
        next_start: 31},
    31: {items: [
          {title: '가', link: 'https://a/1', source: 'naver_kin'},
          {title: '나', link: 'https://a/9', source: 'naver_kin'}],
         next_start: 61},
    61: {items: [
          {title: '다', link: 'https://a/4', source: 'naver_kin'}],
         next_start: null},
};
self._calls = [];
self._json = async (url) => {
    const m = url.match(/start=(\\d+)/);
    const start = m ? Number(m[1]) : 1;
    self._calls.push(start);
    return self._pages[start] || {items: [], next_start: null};
};
self.$nextTick = () => {};
self.$refs = {};
self.sourceMode = 'kin';
self.sourceQuery = '이사 견적';
"""

    def test_한_페이지_안의_같은_제목은_한_번만(self):
        out = _js(self.PAGES + """
await self.searchSources();
const out = {titles: self.sourceItems.map(i => i.title)};
""")
        assert out["titles"] == ["가", "나"]

    def test_더_보기가_앞_결과를_또_쌓지_않는다(self):
        out = _js(self.PAGES + """
await self.searchSources();
await self.searchSources(true);
const out = {titles: self.sourceItems.map(i => i.title), calls: self._calls};
""")
        # 31 쪽은 전부 겹쳐서 새 글이 없다 → 61 까지 이어서 본다
        assert out["titles"] == ["가", "나", "다"]
        assert out["calls"] == [1, 31, 61]

    def test_더_볼_것이_없으면_그렇게_말한다(self):
        out = _js(self.PAGES + """
await self.searchSources();
await self.searchSources(true);
await self.searchSources(true);
const out = {error: self.sourceError,
             titles: self.sourceItems.map(i => i.title)};
""")
        assert out["titles"] == ["가", "나", "다"]
        assert "더 볼 새 글감이 없습니다" in out["error"]
