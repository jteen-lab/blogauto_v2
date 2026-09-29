"""블로거 카테고리 라벨 — 관계를 미리 불러와 라벨이 실제로 붙는지.

순서도: docs/flowcharts/blogger_category_labels.md
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.publishing.blogger_publisher import BloggerPublisher


def _post(with_relations=True):
    mt = SimpleNamespace(
        id=7,
        topic=SimpleNamespace(name="생활 정보") if with_relations else None,
        subtopic=SimpleNamespace(name="노하우/꿀팁") if with_relations else None,
    )
    return SimpleNamespace(id=1, matched_main_title_id=7, matched_main_title=mt)


@pytest.mark.asyncio
async def test_관계를_세션으로_불러온다():
    post = _post()
    session = SimpleNamespace(refresh=AsyncMock())
    with patch("sqlalchemy.ext.asyncio.async_object_session", return_value=session):
        await BloggerPublisher._load_category_relations(post)
    calls = [c.kwargs.get("attribute_names") for c in session.refresh.await_args_list]
    assert calls == [["matched_main_title"], ["topic", "subtopic"]]


@pytest.mark.asyncio
async def test_세션이_없으면_조용히_넘기지_않고_경고만():
    post = _post()
    with patch("sqlalchemy.ext.asyncio.async_object_session", return_value=None), \
         patch("app.services.publishing.blogger_publisher.logger") as log:
        await BloggerPublisher._load_category_relations(post)
    assert log.warning.called


@pytest.mark.asyncio
async def test_불러오기_실패해도_발행은_계속():
    post = _post()
    session = SimpleNamespace(refresh=AsyncMock(side_effect=RuntimeError("x")))
    with patch("sqlalchemy.ext.asyncio.async_object_session", return_value=session), \
         patch("app.services.publishing.blogger_publisher.logger") as log:
        await BloggerPublisher._load_category_relations(post)  # 예외가 새지 않는다
    assert log.warning.called


@pytest.mark.asyncio
async def test_매칭_제목이_없으면_아무것도_안_한다():
    post = SimpleNamespace(id=1, matched_main_title_id=None)
    with patch("sqlalchemy.ext.asyncio.async_object_session") as aos:
        await BloggerPublisher._load_category_relations(post)
    aos.assert_not_called()


def test_불러온_관계로_대주제_소주제_라벨이_나온다():
    blog = SimpleNamespace(name="수작남", placeholders={})
    labels = BloggerPublisher()._get_labels(blog, post=_post())
    assert labels == ["생활 정보", "노하우/꿀팁"]


def test_정적_라벨과_합치고_중복은_뺀다():
    blog = SimpleNamespace(name="수작남", placeholders={"blogger_labels": ["생활 정보", "수작남"]})
    labels = BloggerPublisher()._get_labels(blog, post=_post())
    assert labels == ["생활 정보", "수작남", "노하우/꿀팁"]
