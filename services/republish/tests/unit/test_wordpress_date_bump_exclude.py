"""재발행 날짜 옮기기 제외 목록 시험 (2026-11-07 제목 재조합 시범)."""
from types import SimpleNamespace

from app.services.wordpress_service import date_bump_exclude_query


def test_목록이_없으면_조건을_붙이지_않는다() -> None:
    assert date_bump_exclude_query(SimpleNamespace(renewal_config=None)) == ""
    assert date_bump_exclude_query(SimpleNamespace(renewal_config={})) == ""


def test_글_번호만_조건으로_만든다() -> None:
    blog = SimpleNamespace(renewal_config={"date_bump_exclude_ids": [1576, "1546", "x/1"]})
    assert date_bump_exclude_query(blog) == "&exclude=1576,1546"
