"""사라진 모델 경고 + 동기화 주기 설정 (3~5단계, 2026-08-30).

자동으로 모델을 바꾸지 않는 것이 핵심이다. gpt-4o-mini → gpt-4.1-mini
전환에서 같은 프롬프트로 분량이 1,618자 → 3,542자로 달라졌다. 대체 선택은
사람이 해야 하므로 알리기만 한다.
"""
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.ai_model import AIModel
from app.models.blog import Blog, BlogPlatform
from app.models.user import User
from app.services.ai.model_warnings import collect_warnings, message_for

ROOT = Path(__file__).resolve().parents[2]


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


async def _blog(db, cfg, name="테스트블로그"):
    user = User(email="t@example.com", full_name="t", hashed_password="x")
    db.add(user)
    await db.flush()
    blog = Blog(user_id=user.id, name=name, url="https://x.com",
                platform=BlogPlatform.WORDPRESS, ai_config=cfg)
    db.add(blog)
    await db.flush()
    return blog


async def _catalog(db, *rows):
    for provider, model_id, available, shutdown in rows:
        db.add(AIModel(provider=provider, model_id=model_id, capability="text",
                       is_available=available, shutdown_date=shutdown))
    await db.flush()


@pytest.mark.asyncio
async def test_gone_model_is_reported(db):
    await _catalog(db, ("google", "gemini-1.5-pro", False, None))
    await _blog(db, {"writing_ai": {"provider": "google",
                                    "model": "gemini-1.5-pro"}})
    out = await collect_warnings(db)
    assert len(out) == 1
    assert out[0]["reason"] == "gone"
    assert "더 이상 제공되지 않습니다" in message_for(out[0])


@pytest.mark.asyncio
async def test_scheduled_shutdown_is_reported_early(db):
    """사라진 뒤가 아니라 종료 예정일 때 미리 알린다."""
    await _catalog(db, ("openai", "gpt-4o-mini", True, "2026-11-01"))
    await _blog(db, {"title_ai": {"provider": "openai",
                                  "model": "gpt-4o-mini"}})
    out = await collect_warnings(db)
    assert out[0]["reason"] == "shutdown_scheduled"
    assert "2026-11-01" in message_for(out[0])


@pytest.mark.asyncio
async def test_healthy_model_is_silent(db):
    await _catalog(db, ("openai", "gpt-4.1-mini", True, None))
    await _blog(db, {"writing_ai": {"provider": "openai",
                                    "model": "gpt-4.1-mini"}})
    assert await collect_warnings(db) == []


@pytest.mark.asyncio
async def test_empty_catalog_does_not_cry_wolf(db):
    """동기화 전에는 판단 근거가 없다 — 전부 경고하면 오탐이 쏟아진다."""
    await _blog(db, {"writing_ai": {"provider": "openai", "model": "무엇이든"}})
    assert await collect_warnings(db) == []


@pytest.mark.asyncio
async def test_unsynced_provider_is_not_flagged(db):
    """한 제공자만 동기화된 상태에서 다른 제공자 설정을 죽었다고 하면 안 된다."""
    await _catalog(db, ("openai", "gpt-4.1-mini", True, None))
    await _blog(db, {"writing_ai": {"provider": "anthropic",
                                    "model": "claude-haiku-4-5-20251001"}})
    assert await collect_warnings(db) == []


@pytest.mark.asyncio
async def test_all_slots_checked(db):
    """글쓰기만이 아니라 제목·참고자료·이미지도 본다."""
    await _catalog(db,
                   ("openai", "죽음1", False, None),
                   ("openai", "죽음2", False, None),
                   ("openai", "죽음3", False, None))
    await _blog(db, {
        "writing_ai": {"provider": "openai", "model": "죽음1"},
        "title_ai": {"provider": "openai", "model": "죽음2"},
        "reference_ai": {"provider": "openai", "model": "죽음3"},
    })
    out = await collect_warnings(db)
    assert {w["slot"] for w in out} == {"writing_ai", "title_ai", "reference_ai"}


@pytest.mark.asyncio
async def test_filter_by_blog(db):
    await _catalog(db, ("openai", "죽음", False, None))
    b1 = await _blog(db, {"writing_ai": {"provider": "openai", "model": "죽음"}},
                     name="A")
    db.add(Blog(user_id=b1.user_id, name="B", url="https://y.com",
                platform=BlogPlatform.WORDPRESS,
                ai_config={"writing_ai": {"provider": "openai",
                                          "model": "죽음"}}))
    await db.flush()

    assert len(await collect_warnings(db)) == 2
    only = await collect_warnings(db, blog_id=b1.id)
    assert len(only) == 1 and only[0]["blog_name"] == "A"


# ── 화면·스케줄러 규칙 ───────────────────────────────────
def test_screen_loads_catalog_before_config():
    """설정을 먼저 읽으면 select 옵션이 없어 저장값이 빈칸으로 보인다.

    이 프로젝트에서 두 번 겪은 함정이라 순서를 테스트로 고정한다.
    """
    tab = (ROOT / "app/templates/blogs/settings/_tab_ai.html").read_text(
        encoding="utf-8")
    init_at = tab.index("async init()")
    body = tab[init_at:init_at + 700]
    assert body.index("loadCatalog()") < body.index("loadConfig(")


def test_screen_keeps_saved_model_when_missing():
    """목록에서 사라졌다고 선택을 비우면 모르는 사이 다른 모델로 나간다."""
    tab = (ROOT / "app/templates/blogs/settings/_tab_ai.html").read_text(
        encoding="utf-8")
    assert "m.is_available || m.model_id === saved" in tab
    assert "list.unshift(" in tab


def test_screen_shows_price_and_badges():
    tab = (ROOT / "app/templates/blogs/settings/_tab_ai.html").read_text(
        encoding="utf-8")
    assert "최고 성능" in tab and "가성비" in tab
    assert "per_post_estimate" in tab
    assert "지원 종료" in tab


def test_screen_has_sync_button_and_warning_banner():
    tab = (ROOT / "app/templates/blogs/settings/_tab_ai.html").read_text(
        encoding="utf-8")
    assert "syncCatalog()" in tab
    assert "modelWarnings" in tab


def test_scheduler_registers_model_sync():
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert "_register_model_catalog_sync" in src
    assert "DEFAULT_MODEL_SYNC_HOURS = 24" in src


def test_sync_interval_zero_disables_job():
    """0 을 고르면 자동 동기화를 끄고 버튼으로만 돌린다."""
    from app.scheduler.flow_scheduler import _model_sync_hours

    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert "if hours <= 0:" in src
    assert callable(_model_sync_hours)


def test_interval_api_exists():
    src = (ROOT / "app/routers/settings.py").read_text(encoding="utf-8")
    assert "ai-model-sync-interval" in src
    assert "0 = 자동 동기화 안 함" in src
