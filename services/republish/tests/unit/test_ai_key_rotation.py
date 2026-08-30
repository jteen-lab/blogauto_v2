"""AI 키를 2개 이상 등록해도 조회가 되는지 (2026-08-30).

get_available_key 가 order_by(priority) 로 정렬해 놓고 scalar_one_or_none()
으로 받고 있었다. 키를 하나 더 넣는 순간 MultipleResultsFound 가 나서 그
제공자를 아예 못 쓰게 된다. 구글 키가 2개 등록돼 있어 실제로 그 상태였다.

키를 여러 개 두는 것은 rate limit 대비 설계라 정상 상황이다.
"""
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.ai_api_key import AIApiKey
from app.schemas.ai_api_key import AIKeyStatus, AIProvider
from app.services.ai_key_manager import AIKeyManager


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


async def _add_key(db, provider, label, priority, status=AIKeyStatus.ACTIVE.value):
    key = AIApiKey(
        user_id=1, provider=provider.value, label=label,
        api_key="enc", priority=priority,
        is_active=True, status=status,
    )
    db.add(key)
    await db.flush()
    return key


@pytest.mark.asyncio
async def test_two_keys_do_not_break_lookup(db):
    """키가 2개여도 예외 없이 하나를 돌려준다."""
    await _add_key(db, AIProvider.GOOGLE, "제이틴", 0)
    await _add_key(db, AIProvider.GOOGLE, "제이틴2", 1)

    key = await AIKeyManager(db).get_available_key(AIProvider.GOOGLE)
    assert key is not None
    assert key.label == "제이틴", "우선순위가 낮은 번호가 먼저다"


@pytest.mark.asyncio
async def test_many_keys_still_work(db):
    """3개 이상도 마찬가지."""
    for i in range(4):
        await _add_key(db, AIProvider.OPENAI, f"키{i}", i)
    key = await AIKeyManager(db).get_available_key(AIProvider.OPENAI)
    assert key.label == "키0"


@pytest.mark.asyncio
async def test_rotation_skips_excluded_key(db):
    """rate limit 된 키를 빼고 다음 키로 넘어간다(키 순환의 핵심)."""
    first = await _add_key(db, AIProvider.OPENAI, "키A", 0)
    await _add_key(db, AIProvider.OPENAI, "키B", 1)

    nxt = await AIKeyManager(db).get_next_available_key(
        AIProvider.OPENAI, first.id)
    assert nxt is not None and nxt.label == "키B"


@pytest.mark.asyncio
async def test_inactive_and_errored_keys_skipped(db):
    """비활성·오류 키는 건너뛰고 살아 있는 키를 준다."""
    await _add_key(db, AIProvider.ANTHROPIC, "죽은키", 0,
                   status=AIKeyStatus.ERROR.value)
    await _add_key(db, AIProvider.ANTHROPIC, "산키", 1)
    key = await AIKeyManager(db).get_available_key(AIProvider.ANTHROPIC)
    assert key.label == "산키"


@pytest.mark.asyncio
async def test_no_key_returns_none(db):
    assert await AIKeyManager(db).get_available_key(AIProvider.DEEPSEEK) is None


@pytest.mark.asyncio
async def test_other_provider_keys_not_returned(db):
    """제공자가 다르면 섞이지 않는다."""
    await _add_key(db, AIProvider.OPENAI, "오픈AI", 0)
    assert await AIKeyManager(db).get_available_key(AIProvider.GOOGLE) is None
