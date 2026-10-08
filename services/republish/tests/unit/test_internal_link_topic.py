"""내부 링크 주제 찾기(원래 제목 번호) · 실패 보호 — 취업인포마스터 10/8."""
import asyncio

from app.services.generation.internal_linker import InternalLinker


class _Row:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DB:
    """execute 로 받은 조건을 기록하고 정해진 행을 돌려주는 가짜 세션."""

    def __init__(self, row=None, boom=False):
        self.row, self.boom, self.queries = row, boom, []

    async def execute(self, q):
        self.queries.append(str(q))
        return _Row(self.row)

    async def get(self, *_):
        if self.boom:
            raise RuntimeError("db down")
        return None


def test_category_given_is_used_without_query():
    db = _DB(row=(1, 2))
    cat = asyncio.run(InternalLinker(db)._load_current_category("t", 5, (13, 169)))
    assert cat == (13, 169) and db.queries == []


def test_source_title_id_is_looked_up_by_id():
    db = _DB(row=(13, 56))
    cat = asyncio.run(InternalLinker(db)._load_current_category("재조합 제목", 4321))
    assert cat == (13, 56)
    assert "main_titles.id" in db.queries[0]


def test_title_fallback_when_no_id():
    db = _DB(row=None)
    cat = asyncio.run(InternalLinker(db)._load_current_category("재조합 제목"))
    assert cat == (None, None)
    assert "main_titles.title" in db.queries[0]


def test_failure_returns_content_unchanged():
    """링크 만들기가 실패해도 글은 그대로 나간다(링크 0개)."""
    out = asyncio.run(InternalLinker(_DB(boom=True)).insert_links("# 글\n본문", 17, "글", {}))
    assert out == "# 글\n본문"


class _AllDB(_DB):
    """execute 결과에 .all() 을 주는 가짜 세션(후보 로드용)."""

    async def execute(self, q):
        self.queries.append(str(q))
        return type("R", (), {"all": lambda self: []})()


def test_candidate_query_excludes_unpublished_without_model_attr():
    """status 는 모델에 없는 DB 컬럼 — 속성으로 쓰면 예외로 모든 링크가 0개가 된다."""
    db = _AllDB()
    asyncio.run(InternalLinker(db)._load_blog_posts(17, "글"))
    assert "unpublished" in db.queries[0]
