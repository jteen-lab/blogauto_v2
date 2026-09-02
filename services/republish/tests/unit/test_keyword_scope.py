"""니치가 블로그 배정에 쓰이는지 회귀 테스트.

사용자 질문: "키워드 단위 니치 분류가 의미가 있나?"

확인 결과 **의미가 있어야 하는데 안 쓰이고 있었다.** 제목 생성 대상이
`blog_id == 이 블로그` 로만 좁혀져, 전역 풀에 쌓인 채택 키워드 469건을
어느 블로그도 쓰지 못했다. 니치 분류의 값이 바로 여기다 —
"이 키워드를 어느 블로그가 쓸 것인가".
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.keyword_candidate import KeywordCandidate
from app.services.keyword_lab.scope import blog_categories, usable_by

BASE = Path(__file__).resolve().parents[2]


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def execute(self, *a, **k):
        return _Rows(self.rows)


class TestBlogCategories:
    @pytest.mark.asyncio
    async def test_splits_topics_and_subtopics(self):
        db = _Db([(1, 11), (1, 12), (2, None)])
        topics, subs = await blog_categories(db, SimpleNamespace(id=9))
        assert topics == {1, 2} and subs == {11, 12}

    @pytest.mark.asyncio
    async def test_no_blog(self):
        assert await blog_categories(_Db(), None) == (set(), set())

    @pytest.mark.asyncio
    async def test_empty(self):
        assert await blog_categories(_Db([]), SimpleNamespace(id=9)) == (
            set(), set())


class TestUsableBy:
    @pytest.mark.asyncio
    async def test_no_blog_means_no_limit(self):
        assert await usable_by(_Db(), None, KeywordCandidate) is None

    @pytest.mark.asyncio
    async def test_without_categories_only_direct(self):
        """니치를 안 정한 블로그에 전역 풀을 열면 아무 키워드나 들어온다."""
        cond = await usable_by(_Db([]), SimpleNamespace(id=9),
                               KeywordCandidate)
        text = str(cond.compile(compile_kwargs={"literal_binds": True}))
        assert "blog_id = 9" in text
        assert "IS NULL" not in text

    @pytest.mark.asyncio
    async def test_opens_global_pool_by_niche(self):
        db = _Db([(1, 11), (1, 12)])
        cond = await usable_by(db, SimpleNamespace(id=9), KeywordCandidate)
        text = str(cond.compile(compile_kwargs={"literal_binds": True}))
        # 직접 배정 OR (전역 풀 AND 니치 일치)
        assert "blog_id = 9" in text
        assert "blog_id IS NULL" in text
        assert "subtopic_id IN (11, 12)" in text or \
               "subtopic_id IN (12, 11)" in text

    @pytest.mark.asyncio
    async def test_topic_only_category(self):
        db = _Db([(3, None)])
        cond = await usable_by(db, SimpleNamespace(id=9), KeywordCandidate)
        text = str(cond.compile(compile_kwargs={"literal_binds": True}))
        assert "topic_id IN (3)" in text


class TestWiring:
    def _src(self, path):
        return (BASE / path).read_text(encoding="utf-8")

    def test_single_keyword_path_uses_scope(self):
        src = self._src("app/services/keyword_lab/title_maker.py")
        assert "usable_by(self.db, blog, KeywordCandidate)" in src
        # 옛 조건이 남아 있으면 전역 풀이 다시 막힌다
        assert "q.where(KeywordCandidate.blog_id == blog.id)" not in src

    def test_cluster_path_uses_scope(self):
        src = self._src("app/services/keyword_lab/title_maker.py")
        assert "usable_by(self.db, blog, KeywordCluster)" in src
        assert "q.where(KeywordCluster.blog_id == blog.id)" not in src

    def test_cluster_builder_uses_scope(self):
        src = self._src("app/services/keyword_lab/cluster_builder.py")
        assert "usable_by(self.db, blog, KeywordCandidate)" in src
        assert "q.where(KeywordCandidate.blog_id == blog.id)" not in src

    def test_reason_documented(self):
        src = self._src("app/services/keyword_lab/scope.py")
        assert "어느 블로그가 쓸 것인가" in src


class TestRejectedCleanup:
    """제외는 기본으로 남긴다 — 기준을 바꾸면 되살아난다."""

    def test_purge_button_present(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        assert "purgeRejected()" in tpl

    def test_keeps_by_default_explained(self):
        tpl = (BASE / "app/templates/collection/_keyword_pool.html").read_text(
            encoding="utf-8")
        assert "지우지 않고 남겨 둡니다" in tpl

    def test_confirms_before_delete(self):
        js = (BASE / "app/static/js/collection/keyword_pool.js").read_text(
            encoding="utf-8")
        assert "confirm(" in js

    def test_api_supports_verdict_delete(self):
        src = (BASE / "app/routers/data_keyword_pool.py").read_text(
            encoding="utf-8")
        assert "verdict: Optional[str] = Body(None)" in src
