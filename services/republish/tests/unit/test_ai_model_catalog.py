"""AI 모델 카탈로그 — 동기화·조회 (2026-08-30).

모델 목록이 11개 파일에 하드코딩돼 있어 구글 선택지 10개 중 5개가 이미
없는 모델이었다(그중 하나는 '추천' 배지까지 붙어 있었다). 목록을 DB 한 곳
으로 모으고 제공자 API 로 갱신한다.

계획서: docs/plans/ai_model_catalog_sync.md
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.ai_api_key import AIApiKey
from app.models.ai_model import AIModel, AIModelPrice
from app.schemas.ai_api_key import AIKeyStatus, AIProvider
from app.services.ai.model_catalog import ModelCatalogService, classify_by_name
from app.services.ai.model_prices import SEED, estimate_per_post


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


async def _key(db, provider=AIProvider.OPENAI):
    db.add(AIApiKey(user_id=1, provider=provider.value, label="k",
                    api_key="enc", priority=0, is_active=True,
                    status=AIKeyStatus.ACTIVE.value))
    await db.flush()


def _fetched(*ids):
    return [{"model_id": i, "display_name": i, "capability": "text",
             "shutdown_date": None} for i in ids]


# ── 용도 분류 ────────────────────────────────────────────
@pytest.mark.parametrize("model_id,expected", [
    ("gpt-4o-mini", "text"),
    ("gpt-5", "text"),
    ("deepseek-v4-flash", "text"),
    ("text-embedding-3-small", "embedding"),
    ("dall-e-3", "image"),
    ("gemini-2.5-flash-image", "image"),
    ("gpt-4o-mini-tts", "other"),
    ("whisper-1", "other"),
    ("gpt-4o-realtime-preview", "other"),
])
def test_capability_classification(model_id, expected):
    """글쓰기 목록에 임베딩·TTS·이미지가 섞이면 선택지가 쓸모없어진다."""
    assert classify_by_name(model_id) == expected


# ── 동기화 ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_first_sync_adds_models(db):
    await _key(db)
    svc = ModelCatalogService(db)
    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("gpt-5", "gpt-4.1-mini"))):
        out = await svc.sync_provider(AIProvider.OPENAI)
    assert out["added"] == 2 and out["gone"] == 0
    rows = (await db.execute(select(AIModel))).scalars().all()
    assert {r.model_id for r in rows} == {"gpt-5", "gpt-4.1-mini"}
    assert all(r.is_available for r in rows)


@pytest.mark.asyncio
async def test_missing_model_is_marked_not_deleted(db):
    """사라진 모델의 행을 지우면 '지원 종료' 표시와 경고를 할 수 없다."""
    await _key(db)
    svc = ModelCatalogService(db)
    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("a", "b"))):
        await svc.sync_provider(AIProvider.OPENAI)
    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("a"))):
        out = await svc.sync_provider(AIProvider.OPENAI)

    assert out["gone"] == 1 and out["kept"] == 1
    rows = {r.model_id: r for r in
            (await db.execute(select(AIModel))).scalars().all()}
    assert set(rows) == {"a", "b"}, "행은 남아야 한다"
    assert rows["a"].is_available is True
    assert rows["b"].is_available is False


@pytest.mark.asyncio
async def test_badge_removed_when_model_disappears(db):
    """없어진 모델에 추천 배지가 남으면 추천대로 골라 실패한다.

    실제로 gemini-3-pro-preview 가 '추천' 인데 목록에 없는 상태였다.
    """
    await _key(db)
    svc = ModelCatalogService(db)
    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("old-pro"))):
        await svc.sync_provider(AIProvider.OPENAI)
    row = (await db.execute(select(AIModel))).scalars().one()
    row.tier = "flagship"
    await db.commit()

    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("new-pro"))):
        await svc.sync_provider(AIProvider.OPENAI)

    gone = (await db.execute(
        select(AIModel).where(AIModel.model_id == "old-pro")
    )).scalars().one()
    assert gone.is_available is False
    assert gone.tier is None, "사라진 모델의 배지는 내려가야 한다"


@pytest.mark.asyncio
async def test_returning_model_is_reactivated(db):
    """다시 나타나면 되살아난다(일시적 누락에 대비)."""
    await _key(db)
    svc = ModelCatalogService(db)
    for fetched in (_fetched("a"), [], _fetched("a")):
        with patch.object(svc, "fetch_provider",
                          new=AsyncMock(return_value=fetched)):
            await svc.sync_provider(AIProvider.OPENAI)
    row = (await db.execute(select(AIModel))).scalars().one()
    assert row.is_available is True


@pytest.mark.asyncio
async def test_provider_without_key_is_skipped_not_failed(db):
    """키가 없는 제공자는 에러가 아니라 건너뛰기다."""
    out = await ModelCatalogService(db).sync_provider(AIProvider.ANTHROPIC)
    assert out["ok"] is True and out.get("skipped") is True


@pytest.mark.asyncio
async def test_one_provider_failure_does_not_stop_others(db):
    """한 제공자가 죽어도 나머지는 갱신돼야 한다."""
    await _key(db, AIProvider.OPENAI)
    await _key(db, AIProvider.DEEPSEEK)
    svc = ModelCatalogService(db)

    async def _fetch(provider):
        if provider == AIProvider.OPENAI:
            raise RuntimeError("서버 오류")
        if provider == AIProvider.DEEPSEEK:
            return _fetched("deepseek-v4-flash")
        return []

    with patch.object(svc, "fetch_provider", new=AsyncMock(side_effect=_fetch)):
        out = await svc.sync_all()

    by = {r["provider"]: r for r in out["results"]}
    assert by["openai"]["ok"] is False
    assert by["deepseek"]["added"] == 1
    assert out["total"]["added"] == 1


@pytest.mark.asyncio
async def test_empty_fetch_does_not_wipe_catalog(db):
    """조회가 빈 값을 주면 기존 목록을 지우지 않는다(장애 시 전멸 방지)."""
    await _key(db)
    svc = ModelCatalogService(db)
    with patch.object(svc, "fetch_provider",
                      new=AsyncMock(return_value=_fetched("a", "b"))):
        await svc.sync_provider(AIProvider.OPENAI)
    with patch.object(svc, "fetch_provider", new=AsyncMock(return_value=[])):
        out = await svc.sync_provider(AIProvider.OPENAI)

    assert out.get("skipped") is True
    rows = (await db.execute(select(AIModel))).scalars().all()
    assert all(r.is_available for r in rows), "빈 응답으로 전부 죽이면 안 된다"


@pytest.mark.asyncio
async def test_shutdown_date_is_kept(db):
    """OpenAI 가 알려주는 종료일을 보관해 사전 경고에 쓴다."""
    await _key(db)
    svc = ModelCatalogService(db)
    data = [{"model_id": "gpt-x", "display_name": "gpt-x",
             "capability": "text", "shutdown_date": "2026-11-01"}]
    with patch.object(svc, "fetch_provider", new=AsyncMock(return_value=data)):
        await svc.sync_provider(AIProvider.OPENAI)
    row = (await db.execute(select(AIModel))).scalars().one()
    assert row.shutdown_date == "2026-11-01"


# ── 요금 ────────────────────────────────────────────────
def test_price_seed_has_both_badges_per_provider():
    """제공자마다 최고성능·가성비가 하나씩 있어야 배지가 의미를 갖는다."""
    for provider in ("openai", "deepseek", "google", "anthropic"):
        tiers = [s.get("tier") for s in SEED if s["provider"] == provider]
        assert tiers.count("flagship") == 1, f"{provider} flagship"
        assert tiers.count("value") == 1, f"{provider} value"


def test_price_seed_values_are_sane():
    """출력이 입력보다 싼 요금은 없다 — 오타를 잡는다."""
    for s in SEED:
        i, o = s.get("input_per_1m"), s.get("output_per_1m")
        assert i and o and o >= i, s["model_id"]


def test_deepseek_note_mentions_peak():
    """시간대 요금이 있는 제공자는 어느 기준인지 밝혀야 오해가 없다."""
    ds = [s for s in SEED if s["provider"] == "deepseek"]
    assert ds and all("비피크" in (s.get("note") or "") for s in ds)


def test_per_post_estimate():
    """글 한 편 비용 추정 — 싼 모델이 비싼 모델보다 싸야 한다."""
    flash = estimate_per_post(0.22, 0.66)
    gpt5 = estimate_per_post(1.25, 10.0)
    assert 0 < flash < gpt5
    assert estimate_per_post(None, None) == 0.0


# ── 조회 API ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_returns_price_and_badge(db):
    """화면이 요금·배지를 함께 받아야 선택 시점에 비용을 볼 수 있다."""
    db.add(AIModel(provider="deepseek", model_id="deepseek-v4-flash",
                   display_name="DeepSeek V4 Flash", capability="text",
                   is_available=True, tier="value"))
    db.add(AIModelPrice(provider="deepseek", model_id="deepseek-v4-flash",
                        input_per_1m=0.22, output_per_1m=0.66,
                        currency="USD", note="비피크 기준"))
    await db.commit()

    from app.routers.ai_models import list_models

    out = await list_models(provider=None, capability="text",
                            include_unavailable=False, db=db, _user=None)
    item = out["items"][0]
    assert item["tier"] == "value"
    assert item["price"]["output_per_1m"] == 0.66
    assert item["price"]["per_post_estimate"] > 0
    assert "비피크" in item["price"]["note"]


@pytest.mark.asyncio
async def test_api_hides_unavailable_by_default(db):
    """기본 목록에는 죽은 모델이 안 나오되, 요청하면 볼 수 있어야 한다."""
    db.add(AIModel(provider="google", model_id="살아있음",
                   capability="text", is_available=True))
    db.add(AIModel(provider="google", model_id="사라짐",
                   capability="text", is_available=False))
    await db.commit()

    from app.routers.ai_models import list_models

    on = await list_models(provider=None, capability="text",
                           include_unavailable=False, db=db, _user=None)
    assert {i["model_id"] for i in on["items"]} == {"살아있음"}

    both = await list_models(provider=None, capability="text",
                             include_unavailable=True, db=db, _user=None)
    assert {i["model_id"] for i in both["items"]} == {"살아있음", "사라짐"}


@pytest.mark.asyncio
async def test_api_filters_by_capability(db):
    """이미지 모델이 글쓰기 선택지에 섞이면 안 된다."""
    db.add(AIModel(provider="openai", model_id="글", capability="text",
                   is_available=True))
    db.add(AIModel(provider="openai", model_id="그림", capability="image",
                   is_available=True))
    await db.commit()

    from app.routers.ai_models import list_models

    out = await list_models(provider=None, capability="text",
                            include_unavailable=False, db=db, _user=None)
    assert {i["model_id"] for i in out["items"]} == {"글"}


# ── 마이그레이션 안전장치 (2026-08-30) ────────────────────
# 054 는 테이블 '이름' 만 보고 존재하면 건너뛰었다. 구조가 다른 옛 ai_models
# 가 남아 있어 조회가 UndefinedColumnError 로 실패했다. 이름이 같아도 구조가
# 다를 수 있다.

def test_migration_checks_columns_not_just_table_name():
    """이름만 확인하는 마이그레이션은 구조가 다른 테이블을 지나친다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    src = (root / "alembic/versions/055_replace_legacy_ai_models.py").read_text(
        encoding="utf-8")
    assert "_has_column" in src
    assert "MARKER_COLUMN" in src


def test_migration_preserves_legacy_rows():
    """옛 데이터는 사용자가 수동 입력한 것이라 지우지 않고 옮긴다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    src = (root / "alembic/versions/055_replace_legacy_ai_models.py").read_text(
        encoding="utf-8")
    assert "rename_table" in src
    assert "ai_models_legacy" in src
    # 옛 테이블을 통째로 지우는 코드가 있으면 안 된다
    assert 'op.drop_table(TABLE)' not in src.split("def downgrade")[0]


def test_model_columns_match_migration():
    """모델 클래스와 마이그레이션 컬럼이 어긋나면 조회가 깨진다."""
    from pathlib import Path

    from app.models.ai_model import AIModel

    root = Path(__file__).resolve().parents[2]
    src = (root / "alembic/versions/055_replace_legacy_ai_models.py").read_text(
        encoding="utf-8")
    for col in AIModel.__table__.columns:
        assert f'"{col.name}"' in src, f"마이그레이션에 {col.name} 누락"
