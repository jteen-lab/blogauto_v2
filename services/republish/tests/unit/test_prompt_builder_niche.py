"""니치 특화 프롬프트 블록·프리셋 테스트 (2026-08-28 재구성).

배경: 운영 방침이 다니치 → 니치 특화 블로그로 바뀌었고, 기존 프리셋의 추천 니치가
현재 카테고리 체계에 없는 옛 분류였다("패션·뷰티", "영화·드라마" 등).
"""
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import Base
from app.models.prompt_block import PromptBlock
from app.services.prompt_builder import blocks as B
from app.services.prompt_builder.presets import PRESETS
from app.services.prompt_builder.store import ensure_seeded

@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: D103 — 테스트 전용 shim
    return "JSON"


AXES = {
    "persona": B.PERSONAS, "reader": B.READERS,
    "pattern": B.PATTERNS, "tone": B.TONES, "common": B.COMMONS,
}


# ---------- 프리셋 무결성 ----------

def test_every_preset_code_exists_in_blocks():
    """프리셋이 존재하지 않는 블록 코드를 가리키면 프롬프트가 조용히 깨진다."""
    known = {axis: {b["code"] for b in items} for axis, items in AXES.items()}
    for preset in PRESETS:
        if preset.get("full_prompt"):
            continue
        for axis in ("persona", "reader", "pattern", "tone"):
            assert preset[axis] in known[axis], f"{preset['code']}.{axis}={preset[axis]}"
        if preset.get("common"):
            assert preset["common"] in known["common"], preset["code"]


def test_preset_codes_are_unique():
    codes = [p["code"] for p in PRESETS]
    assert len(codes) == len(set(codes))


def test_ymyl_presets_carry_ymyl_principle():
    """돈·건강 주제는 더 엄격한 기준을 받으므로 YMYL 원칙이 붙어야 한다."""
    ymyl = {"n-loan", "n-wealth", "n-welfare", "n-health", "n-parenting"}
    for preset in PRESETS:
        if preset["code"] in ymyl:
            assert preset.get("common") == "C-YMYL", preset["code"]


def test_no_stale_niche_names_remain():
    """현재 카테고리 체계에 없는 옛 니치 표기가 남아 있으면 안 된다."""
    stale = ("패션", "뷰티", "직구", "영화", "드라마", "반려동물", "인테리어", "어학")
    for preset in PRESETS:
        text = str(preset.get("categories", ""))
        for word in stale:
            assert word not in text, f"{preset['code']}에 옛 니치 '{word}'"


def test_presets_cover_top_inventory_niches():
    """제목 재고 상위 니치는 전부 어느 프리셋엔가 들어가야 한다."""
    joined = " ".join(str(p.get("categories", "")) for p in PRESETS)
    for niche in (
        "금융/대출", "생활 정보", "여행/관광", "건강/의학", "재테크/돈관리",
        "음식/레시피", "취업/자격증", "정부지원금/복지", "컴퓨터/IT",
        "AI/인공지능", "보험", "출산/육아", "쇼핑/리뷰", "자동차",
        "지역/업체정보", "세금/절세", "시니어/노후", "부동산",
    ):
        assert niche in joined, niche


# ---------- 신규 블록 ----------

def test_new_blocks_are_registered():
    for axis, code in (
        ("persona", "P-Guide"), ("reader", "R-Applicant"),
        ("pattern", "P6"), ("tone", "T-Eligibility"), ("common", "C-YMYL"),
    ):
        assert any(b["code"] == code for b in AXES[axis]), code


def test_procedure_pattern_has_six_slots():
    body = next(b["body"] for b in B.PATTERNS if b["code"] == "P6")
    for slot in ("- A:", "- B:", "- C:", "- D:", "- E:", "- F:"):
        assert slot in body


def test_ymyl_block_covers_required_points():
    """YMYL 기준: 단정 금지·기준 명시·날조 금지·한계 표기·최신성."""
    body = next(b["body"] for b in B.COMMONS if b["code"] == "C-YMYL")
    for keyword in ("단정", "기준", "지어내지", "한계", "최신성"):
        assert keyword in body, keyword


def test_all_block_codes_unique_per_axis():
    for axis, items in AXES.items():
        codes = [b["code"] for b in items]
        assert len(codes) == len(set(codes)), axis


# ---------- 시드 (회귀) ----------

@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_adds_missing_codes_to_already_seeded_type(db):
    """이전 구현은 '타입에 행이 있으면 통째로 건너뜀'이라 새 블록이 영원히 안 들어갔다."""
    db.add(PromptBlock(
        block_type="pattern", code="P1", label="기존", body="x",
        sort_order=0, is_active=True, is_builtin=True,
    ))
    await db.commit()

    await ensure_seeded(db)

    from sqlalchemy import select
    codes = set((await db.execute(
        select(PromptBlock.code).where(PromptBlock.block_type == "pattern"),
    )).scalars().all())
    assert "P6" in codes, "새 패턴이 시드되지 않음"
    assert "P1" in codes


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_operator_edits(db):
    """운영자가 고친 본문을 시드가 덮으면 안 된다."""
    db.add(PromptBlock(
        block_type="pattern", code="P1", label="운영자수정", body="내가 고친 본문",
        sort_order=0, is_active=True, is_builtin=True,
    ))
    await db.commit()

    await ensure_seeded(db)

    from sqlalchemy import select
    row = (await db.execute(
        select(PromptBlock).where(PromptBlock.code == "P1"),
    )).scalar_one()
    assert row.body == "내가 고친 본문"


@pytest.mark.asyncio
async def test_seed_is_idempotent(db):
    await ensure_seeded(db)
    from sqlalchemy import func, select
    first = (await db.execute(select(func.count(PromptBlock.id)))).scalar()
    await ensure_seeded(db)
    second = (await db.execute(select(func.count(PromptBlock.id)))).scalar()
    assert first == second
