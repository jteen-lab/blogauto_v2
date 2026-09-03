"""임시제목 정리 회귀 테스트(계획서 §5 B안).

배경: temp_titles 105,004건 중 정식 통과율이 2% 였다. 사이트맵을 통째로
    긁어 니치 무관 제목까지 재고에 넣은 결과다.

삭제는 되돌릴 수 없으므로 **판정 기준**을 고정한다. 특히 카테고리가
비었을 때 전량 삭제되는 사고를 막는 가드가 핵심이다.
"""
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.title import TempTitle
from app.services import title_cleanup as tc


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103 — 테스트 전용 shim
    return "JSON"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession,
                               expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()

BASE = Path(__file__).resolve().parents[2]


class TestConditionGuards:
    def test_unclassified_condition_exists(self):
        assert tc._condition(tc.REASON_UNCLASSIFIED, set()) is not None

    def test_off_niche_needs_topics(self):
        """활성 카테고리가 없으면 '무관' 을 정의할 수 없다 — 아무것도 안 지운다.

        이 가드가 없으면 카테고리를 아직 안 붙인 사용자의 재고가 통째로
        날아간다.
        """
        assert tc._condition(tc.REASON_OFF_NICHE, set()) is None

    def test_off_niche_with_topics(self):
        assert tc._condition(tc.REASON_OFF_NICHE, {1, 2}) is not None

    def test_unknown_reason_is_ignored(self):
        assert tc._condition("아무거나", {1}) is None

    def test_reasons_are_labelled(self):
        for reason in tc.REASONS:
            assert tc.REASON_LABEL.get(reason), reason


class TestCleanupSelection:
    @pytest.mark.asyncio
    async def test_empty_reasons_is_rejected(self):
        out = await tc.cleanup(None, reasons=["없는사유"])
        assert out["success"] is False and out["deleted"] == 0

    @pytest.mark.asyncio
    async def test_empty_list_is_not_treated_as_all(self):
        """빈 목록을 '둘 다' 로 해석하면 되돌릴 수 없는 사고가 난다.

        화면에서 체크를 모두 끈 채 호출되는 경로가 실제로 있다.
        """
        out = await tc.cleanup(None, reasons=[])
        assert out["success"] is False and out["deleted"] == 0


@pytest.mark.asyncio
async def test_preview_and_cleanup_on_real_rows(db_session):
    """미분류는 지우고 니치 안쪽은 남긴다."""
    rows = [
        TempTitle(title="미분류 제목 하나", source_blog_url="u",
                  source_post_url="p", collection_stage="blog_crawl"),
        TempTitle(title="니치 안쪽 제목", source_blog_url="u",
                  source_post_url="p", collection_stage="blog_crawl",
                  topic_id=1),
        TempTitle(title="니치 바깥 제목", source_blog_url="u",
                  source_post_url="p", collection_stage="blog_crawl",
                  topic_id=999),
    ]
    for row in rows:
        db_session.add(row)
    await db_session.commit()

    # 활성 주제가 없는 상태 — 니치 판정은 건너뛴다
    view = await tc.preview(db_session)
    assert view["counts"][tc.REASON_UNCLASSIFIED] == 1
    assert view["counts"][tc.REASON_OFF_NICHE] == 0
    assert view["niche_check_skipped"] is True

    out = await tc.cleanup(db_session, [tc.REASON_UNCLASSIFIED])
    assert out["deleted"] == 1

    left = (await db_session.execute(select(TempTitle))).scalars().all()
    assert len(left) == 2, "니치 판정 불가일 때 분류된 제목을 지우면 안 된다"


class TestWiring:
    def test_router_paths(self):
        from app.main import app

        paths = {r.path for r in app.routes}
        assert "/api/v1/data/titles/cleanup/preview" in paths
        assert "/api/v1/data/titles/cleanup" in paths

    def test_panel_included_and_menu_opens_it(self):
        index = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        titles = (BASE / "app/templates/collection/_titles.html").read_text(
            encoding="utf-8")
        assert "_title_cleanup.html" in index
        assert "open-title-cleanup" in titles

    def test_panel_warns_to_reclassify_first(self):
        """재분류 먼저 돌리라는 안내가 사라지면 살릴 제목을 버린다."""
        panel = (BASE / "app/templates/collection/_title_cleanup.html").read_text(
            encoding="utf-8")
        assert "재분류" in panel
        assert "되돌릴 수 없" in panel

    def test_refresh_after_delete(self):
        index = (BASE / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "@titles-changed.window" in index
