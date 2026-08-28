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
    ymyl_prefixes = ("n-loan", "n-ins", "n-tax", "n-invest", "n-saving",
                     "n-senior", "n-realestate", "n-welfare", "n-health",
                     "n-parenting", "n-food-effect")
    for preset in PRESETS:
        code = str(preset["code"])
        if code.startswith(ymyl_prefixes):
            assert preset.get("common") == "C-YMYL", code


def test_every_preset_has_a_distinct_voice():
    """세분화의 목적은 '다른 사람이 쓴 것처럼' 이다.

    조합이 겹치면 프리셋을 나눠도 결과물이 비슷해져 세분화가 무의미해진다.
    """
    seen = {}
    for preset in PRESETS:
        if preset.get("full_prompt"):
            continue
        combo = (
            preset["persona"], preset["reader"],
            preset["pattern"], preset["tone"],
        )
        assert combo not in seen, (
            f"{preset['code']} 와 {seen[combo]} 의 조합이 동일: {combo}"
        )
        seen[combo] = preset["code"]


def test_voice_axes_are_actually_varied():
    """화자·시작톤이 몇 종류만 돌려쓰이면 세분화 효과가 없다."""
    axis_used = {"persona": set(), "tone": set(), "pattern": set()}
    for preset in PRESETS:
        if preset.get("full_prompt"):
            continue
        for axis in axis_used:
            axis_used[axis].add(preset[axis])
    assert len(axis_used["persona"]) >= 10, axis_used["persona"]
    assert len(axis_used["tone"]) >= 9, axis_used["tone"]
    assert len(axis_used["pattern"]) >= 7, axis_used["pattern"]


def test_no_stale_niche_names_remain():
    """현재 카테고리 체계에 없는 옛 니치 표기가 남아 있으면 안 된다."""
    stale = ("패션", "뷰티", "직구", "영화", "드라마", "반려동물", "인테리어", "어학")
    for preset in PRESETS:
        text = str(preset.get("categories", ""))
        for word in stale:
            assert word not in text, f"{preset['code']}에 옛 니치 '{word}'"


def test_presets_cover_high_inventory_subtopics():
    """재고가 쌓인 하위 주제가 어느 프리셋에도 없으면 그 글은 기본값으로 생성된다."""
    joined = " ".join(str(p.get("categories", "")) for p in PRESETS)
    for subtopic in (
        "대출 정보", "신용대출", "주택담보대출", "전세자금대출", "정책금융",
        "카드·리볼빙", "고객센터·연락처", "노하우/꿀팁", "매장·시설 정보",
        "여행 날씨·시기", "숙소·호텔", "질병 및 증상", "치료·처방",
        "비만·다이어트", "토큰 증권", "적금/예금", "요리 레시피",
        "식재료 효능", "구인구직 사이트", "자격증", "정부 정책·제도",
        "PC·윈도우", "생성형AI", "자동차보험", "보험금 청구", "연말정산",
        "육아팁", "가격 비교", "꽃배달", "연금",
    ):
        assert subtopic in joined, subtopic


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


# ---------- 프리셋 추천용 매핑 (2026-08-28) ----------

def test_every_preset_has_machine_readable_match():
    """UI 추천은 표시 문자열이 아니라 match_topics/match_subtopics 로 판정한다."""
    for preset in PRESETS:
        if preset.get("full_prompt"):
            continue
        assert preset.get("match_topics"), preset["code"]
        assert preset.get("match_subtopics"), preset["code"]


def test_match_topics_are_real_topic_names():
    """존재하지 않는 주제명을 넣으면 추천이 영원히 안 뜬다."""
    real = {
        "금융/대출", "생활 정보", "여행/관광", "건강/의학", "재테크/돈관리",
        "음식/레시피", "취업/자격증", "정부지원금/복지", "컴퓨터/IT",
        "AI/인공지능", "보험", "출산/육아", "쇼핑/리뷰", "자동차",
        "지역/업체정보", "세금/절세", "시니어/노후", "부동산", "의료",
    }
    for preset in PRESETS:
        for topic in preset.get("match_topics") or []:
            assert topic in real, f"{preset['code']}: {topic}"


def test_match_topics_do_not_leak_from_substring():
    """'자동차보험' 이 '자동차' 주제로 잡히면 엉뚱한 추천이 뜬다(초기 구현 버그)."""
    auto = next(p for p in PRESETS if p["code"] == "n-ins-auto")
    assert auto["match_topics"] == ["보험"]


def test_match_subtopics_have_no_inventory_counts():
    """표시용 '(255)' 같은 숫자가 남으면 이름 비교가 실패한다."""
    for preset in PRESETS:
        for sub in preset.get("match_subtopics") or []:
            assert "(" not in sub and ")" not in sub, f"{preset['code']}: {sub}"


# ---------- 블로그 기준 모드 추천 (2026-08-28 회귀) ----------

def test_blog_mode_categories_have_names_for_matching():
    """블로그 기준 모드는 selectedCategories 가 비어 있고
    linking.blogCategories 에만 값이 들어온다(이름 포함).

    추천 로직이 selectedCategories 만 보면 블로그를 골라도 추천이 안 뜬다.
    실제로 그 버그가 있었다. 여기서는 매칭에 쓰는 이름 형식이
    프리셋의 match_* 와 같은 문자열인지 확인한다.
    """
    # 슈마즈 실제 설정(재테크/돈관리 6개 하위주제)
    blog_subtopics = {
        "월급 관리", "적금/예금", "주식", "ETF투자", "연금·노후자금", "절약·가계부",
    }
    matched = [
        p["code"] for p in PRESETS
        if set(p.get("match_subtopics") or []) & blog_subtopics
    ]
    assert "n-invest" in matched, matched
    assert "n-saving" in matched, matched


# 2026-08-28 운영 DB 기준 살아있는 하위주제 전체(123종).
# 표시용 문자열을 축약·변형하면(예: DB '비만/다이어트' → 표기 '비만·다이어트')
# 그 하위주제를 골라도 추천이 영원히 안 뜬다. 실제로 그 버그가 있었다.
DB_SUBTOPICS = {
    "AI 기술 이해", "AI 도구", "생성형AI",
    "멘탈 관리", "병원·진료", "비만/다이어트", "영양제·보충제", "예방·관리",
    "운동", "원인·발병", "증상·자가진단", "질병 및 증상", "치료·처방", "통증 관리",
    "금리·상환", "금융 정보", "대출 정보", "사업자대출", "신용대출",
    "신용점수·관리", "전세자금대출", "정책금융", "주택담보대출", "카드·리볼빙",
    "보험금 청구", "실손의료보험", "암·건강보험", "어린이·태아보험", "자동차보험",
    "종신·정기보험", "해지·환급", "화재·주택보험",
    "매매·청약", "부동산 세금·비용", "이사·인테리어", "임대사업",
    "재개발·재건축", "전세사기 예방", "전월세 계약",
    "고객센터·연락처", "공과금·관리비", "교통·이동", "노하우/꿀팁",
    "매장·시설 정보", "문화 정보", "생활 정보", "통신·인터넷", "행정·증명서",
    "부가가치세", "사업자 세무", "상속·증여", "양도소득세", "연말정산", "종합소득세",
    "가격 비교", "제품 정보",
    "건강보험료", "노인복지", "상속·정리", "연금", "요양·돌봄",
    "국내여행지", "숙소·호텔", "여행 경비·예산", "여행 교통", "여행 날씨·시기",
    "여행 음식·맛집", "여행 정보", "여행 준비물", "해외여행지",
    "보관·저장", "부작용·주의", "식재료 효능", "요리 레시피", "음식 효능", "조리법·손질",
    "과태료·법규", "사고·처리", "신차·구매", "전기·친환경차", "정비·소모품", "중고차",
    "ETF투자", "부업", "앱테크", "연금·노후자금", "월급 관리", "적금/예금",
    "절약·가계부", "주식", "토큰 증권",
    "소상공인 지원", "실업·고용", "에너지·생활 지원", "육아·가족 지원",
    "정부 정책·제도", "주거 지원", "청년 지원",
    "꽃배달", "수리·시공", "이사·청소업체", "이사짐센터", "인터넷업체", "장례·예식",
    "산후조리", "영유아 건강", "육아용품", "육아팁/육아노하우",
    "임산부 태교/일기", "임신 준비/건강", "출산 준비",
    "구인구직 사이트", "면접·자소서", "연봉·처우", "이직·경력",
    "자격증", "직업 정보", "취업 정보",
    "PC·윈도우", "인터넷·보안", "주변기기", "코딩", "프로그램·오피스",
}


def test_presets_cover_every_live_subtopic():
    """어느 하위주제를 골라도 추천이 뜨도록, 전부 어느 프리셋엔가 속해야 한다."""
    covered = set()
    for p in PRESETS:
        covered.update(p.get("match_subtopics") or [])
    missing = DB_SUBTOPICS - covered
    assert not missing, f"프리셋이 덮지 않는 하위주제: {sorted(missing)}"


def test_no_invented_subtopic_names():
    """DB에 없는 이름을 프리셋에 쓰면 그 항목은 영원히 매칭되지 않는다."""
    invented = set()
    for p in PRESETS:
        invented.update(set(p.get("match_subtopics") or []) - DB_SUBTOPICS)
    assert not invented, f"DB에 없는 하위주제 표기: {sorted(invented)}"
