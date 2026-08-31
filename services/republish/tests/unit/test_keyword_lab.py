"""키워드 관리(실험실) — 수요를 먼저 재는 수집 (2026-08-31).

현재 수집은 타 블로그 제목 스크랩 → 키워드 추출 → 재스크랩의 닫힌 고리다
(정식제목 3,230건 전부 transfer, 데이터랩·검색광고 저장 0건).
순서를 뒤집어 수요를 먼저 재고 후보를 만든다.

**기존 파이프라인을 건드리지 않는 것이 전제다.** 운영 중인 12개 블로그가
seed_keywords·temp_titles 위에서 돌고 있다.

순서도: docs/flowcharts/keyword_lab.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from app.models.keyword_candidate import (
    VERDICT_ADOPT, VERDICT_HOLD, VERDICT_PENDING, VERDICT_REJECT,
    KeywordCandidate,
)
from app.services.keyword_lab.scoring import (
    MIN_SATURATION, MIN_SEARCH_VOLUME, Thresholds, judge, risk_label,
    saturation_of,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "templates"


# ── 판정 ─────────────────────────────────────────────────
def test_low_volume_is_rejected() -> None:
    """검색량이 없으면 써도 아무도 오지 않는다."""
    verdict, reason, _ = judge("아무도 안 찾는 말", 30, 10)
    assert verdict == VERDICT_REJECT
    assert "검색량" in reason


def test_saturated_keyword_is_rejected() -> None:
    """검색량이 커도 문서가 훨씬 많으면 비집고 들어갈 자리가 없다.

    검색량만 보는 것과 이 판정의 차이가 이 기능의 핵심이다.
    """
    verdict, reason, _ = judge("포화 키워드", 5000, 200_000)
    assert verdict == VERDICT_REJECT
    assert "포화" in reason


def test_healthy_keyword_is_adopted() -> None:
    verdict, _, risk = judge("전기기사 실기 난이도", 1200, 3000)
    assert verdict == VERDICT_ADOPT
    assert risk is None


def test_zero_documents_is_the_best_case() -> None:
    """아무도 안 쓴 자리다. 0으로 나눌 수 없다고 버리면 안 된다."""
    verdict, _, _ = judge("신규 키워드", 500, 0)
    assert verdict == VERDICT_ADOPT
    assert saturation_of(500, 0) == 500.0


def test_unmeasured_stays_pending() -> None:
    """문서수를 안 재고 채택하면 공급을 보지 않고 뽑는 셈이다."""
    verdict, reason, _ = judge("측정 전", 900, None)
    assert verdict == VERDICT_PENDING
    assert "문서수" in reason


def test_risky_type_is_held_not_rejected() -> None:
    """같은 말이 들어가도 정상 정보 글일 수 있다. 사람이 정한다."""
    verdict, _, risk = judge("롯데카드 고객센터", 8000, 4000)
    assert verdict == VERDICT_HOLD
    assert risk == "연락처"


@pytest.mark.parametrize("keyword,label", [
    ("티월드 고객센터 전화번호", "연락처"),
    ("메가박스 상영시간표", "영업시간"),
    ("대구 구인구직 채용정보", "채용조건"),
    ("금강제화 상품권 현금화", "상품권거래"),
])
def test_risk_patterns_match_the_quality_gate(keyword: str, label: str) -> None:
    """품질 게이트가 잡는 유형과 같은 축이어야 한다.

    수집에서 거르지 않으면 생성·발행 단계가 계속 그 부담을 진다.
    실제로 지금 수집 유입 1·2위가 매장·시설 정보와 고객센터·연락처다.
    """
    assert risk_label(keyword) == label


def test_risky_but_low_volume_is_still_rejected() -> None:
    """수요가 없으면 위험 여부를 따질 것도 없다."""
    verdict, _, risk = judge("무명 고객센터", 10, 5)
    assert verdict == VERDICT_REJECT
    assert risk == "연락처"


# ── 기준 조정 ────────────────────────────────────────────
def test_thresholds_can_be_tightened() -> None:
    """니치마다 적정선이 다르다."""
    strict = Thresholds.build(2000, 1.0)
    verdict, _, _ = judge("전기기사 실기 난이도", 1200, 3000, strict)
    assert verdict == VERDICT_REJECT


def test_bad_threshold_values_fall_back() -> None:
    th = Thresholds.build(None, None)
    assert th.min_volume == MIN_SEARCH_VOLUME
    assert th.min_saturation == MIN_SATURATION

    th = Thresholds.build("이상한값", "값")
    assert th.min_volume == MIN_SEARCH_VOLUME

    th = Thresholds.build(-50, -1)
    assert th.min_volume >= 0 and th.min_saturation >= 0


# ── 기존 파이프라인과 분리 ───────────────────────────────
def test_writes_only_to_its_own_table() -> None:
    """운영 중인 수집 테이블을 건드리면 무엇이 원인인지 가릴 수 없다."""
    import ast

    source = (ROOT / "app/services/keyword_lab/service.py").read_text(
        encoding="utf-8")
    # 주석에서 "seed_keywords 를 건드리지 않는다" 고 설명하는 것은 괜찮다.
    # 코드가 실제로 참조하는지를 본다.
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.name for a in node.names}

    for forbidden in ("SeedKeyword", "TempTitle", "MainTitle", "CrawledPost"):
        assert forbidden not in names, f"{forbidden} 를 건드리고 있다"
    assert "KeywordCandidate" in names


def test_schema_can_replace_seed_keywords_later() -> None:
    """seed_keywords 에는 검색량 컬럼이 아예 없어 승격해도 측정값이 사라진다.

    나중에 대체할 수 있도록 처음부터 지표를 들고 있어야 한다.
    """
    cols = {c.name for c in KeywordCandidate.__table__.columns}
    for needed in ("search_volume", "doc_count", "saturation",
                   "competition", "verdict", "topic_id", "subtopic_id",
                   "promoted"):
        assert needed in cols, needed


# ── 설정에 있는 키를 쓴다 ────────────────────────────────
def test_uses_existing_api_keys_only() -> None:
    """새 키를 요구하지 않는다. 이미 설정에 있는 것을 쓴다."""
    source = (ROOT / "app/services/keyword_lab/service.py").read_text(
        encoding="utf-8")
    assert "NaverAdsService" in source
    assert "NaverSearchService" in source
    assert "api_key" not in source.replace("naver_ads_api_key", ""), \
        "서비스가 직접 키를 다루면 안 된다 — 기존 서비스에 위임한다"


def test_status_endpoint_reports_missing_keys() -> None:
    """눌러 보고 실패하는 것보다 먼저 알리는 편이 낫다."""
    source = (ROOT / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
    assert "naver_ads_api_key" in source
    assert "naver_search_client_id" in source


# ── 시드 ─────────────────────────────────────────────────
def test_seeds_come_from_blog_categories_not_hardcoded() -> None:
    """지금 데이터랩 수집은 ['뉴스','이슈','트렌드'] 로 고정돼 있어
    취업/자격증 블로그에도 '뉴스' 로 조회한다."""
    source = (ROOT / "app/services/keyword_lab/service.py").read_text(
        encoding="utf-8")
    assert "BlogCategory" in source and "SubTopic" in source
    for hardcoded in ('"뉴스"', '"이슈"', '"트렌드"'):
        assert hardcoded not in source


# ── 화면 ─────────────────────────────────────────────────
def _render() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    src = (TEMPLATES / "keyword_lab/index.html").read_text(encoding="utf-8")
    body = re.search(r"{% block content %}(.*?){% endblock %}", src, re.S)
    assert body
    return env.from_string(body.group(1)).render()


def test_page_uses_the_shared_table() -> None:
    """화면마다 따로 만들면 동작이 갈라지고 고칠 곳이 늘어난다."""
    html = _render()
    assert html.count('class="list-table"') == 4      # 판정 4탭
    assert "list-table--fixed" in html


def test_verdict_tabs_are_independent() -> None:
    html = _render()
    scopes = set(re.findall(r"listToggleOne\('(kwlab-[a-z]+)'", html))
    assert scopes == {"kwlab-adopt", "kwlab-hold", "kwlab-pending",
                      "kwlab-reject"}


def test_page_warns_before_running_without_keys() -> None:
    src = (TEMPLATES / "keyword_lab/index.html").read_text(encoding="utf-8")
    assert "apiStatus.naver_ads" in src and "apiStatus.naver_search" in src


def test_collect_and_measure_are_separate_actions() -> None:
    """한 요청에 묶으면 타임아웃이 나고, 끊기면 어디까지 쟀는지 모른다."""
    src = (TEMPLATES / "keyword_lab/index.html").read_text(encoding="utf-8")
    assert "collect()" in src and "measure()" in src
    router = (ROOT / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
    assert '"/collect"' in router and '"/measure"' in router


def test_menu_entry_exists() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert base.count('href="/keyword-lab"') == 2, "PC·모바일 메뉴 모두 필요"


# ── 불리언 속성 바인딩 ───────────────────────────────────
def test_boolean_attribute_bindings_are_real_booleans() -> None:
    """Alpine 은 **빈 문자열을 속성 제거 대상으로 보지 않는다.**

    3.13.3 실제 코드:
        [null, undefined, false].includes(value) ? removeAttribute : setAttribute
    그리고 disabled 는 불리언 속성이라 setAttribute 시 값이 'disabled' 가 된다.

    busy 를 ''(빈 문자열)로 두고 :disabled="busy" 로 묶었더니 버튼이 처음부터
    영구 비활성이었다. 초기 상태에서 어떤 불리언 속성도 켜지면 안 된다.
    """
    import json
    import subprocess

    src = (TEMPLATES / "keyword_lab/index.html").read_text(encoding="utf-8")
    body = re.search(r"{% block content %}(.*?){% endblock %}", src, re.S)
    assert body

    # Alpine 이 불리언으로 다루는 속성들
    bool_attrs = ("disabled", "checked", "required", "readonly", "hidden",
                  "open", "selected", "multiple")
    bindings = [
        (attr, expr) for attr, expr in
        re.findall(r':([a-z]+)\s*=\s*"([^"]*)"', body.group(1))
        if attr in bool_attrs
    ]
    assert bindings, "검사할 불리언 바인딩이 없다"

    program = f"""
global.document = {{addEventListener(){{}}, querySelector(){{return null}},
                    getElementById(){{return null}}, querySelectorAll(){{return []}}}};
global.window = {{addEventListener(){{}}}};
const fs = require('fs');
eval(fs.readFileSync({str(ROOT / 'app/static/js/components/list_selection.js')!r}, 'utf8'));
eval(fs.readFileSync({str(ROOT / 'app/static/js/keyword_lab/app.js')!r}, 'utf8'));
const app = keywordLabApp();

// Alpine 3.13.3 의 규칙 그대로
const removes = v => [null, undefined, false].includes(v);

const bad = [];
for (const [attr, expr] of {json.dumps(bindings)}) {{
  let v;
  try {{ v = new Function('s', `with (s) {{ return (${{expr}}) }}`)(app); }}
  catch (e) {{ bad.push([attr, expr, '평가 실패: ' + e.message]); continue; }}
  if (!removes(v)) bad.push([attr, expr, `초기값 ${{JSON.stringify(v)}} → 속성이 켜진다`]);
}}
console.log(JSON.stringify(bad));
"""
    result = subprocess.run(["node", "-e", program], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    bad = json.loads(result.stdout.strip())
    assert not bad, "초기 상태에서 켜지는 불리언 속성:\n" + "\n".join(
        f"  :{a}=\"{e}\" — {why}" for a, e, why in bad)


# ── 실패를 숨기지 않는다 ─────────────────────────────────
@pytest.mark.asyncio
async def test_collect_reports_api_failure_instead_of_zero() -> None:
    """403 을 로그에만 남기고 '0개 수집' 으로 끝내면 안 된다.

    실제로 고객 ID 가 한 글자('e')로 저장돼 인증이 계속 실패했는데,
    화면에는 '0개 수집' 만 보여 원인을 알 수 없었다.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.services.keyword_lab.service import KeywordLabService

    db = SimpleNamespace(add=lambda *a: None, commit=AsyncMock())
    svc = KeywordLabService(db=db, settings=SimpleNamespace(), user_id=1)
    svc.seeds_for_blog = AsyncMock(return_value=[
        {"seed": "자격증", "topic_id": 13, "subtopic_id": 56}])
    svc._existing_keywords = AsyncMock(return_value=set())

    fake_ads = SimpleNamespace(
        is_configured=lambda: True,
        get_keyword_stats=AsyncMock(return_value={
            "success": False,
            "error": "네이버 검색광고 인증 실패 — 고객 ID(CUSTOMER_ID) 확인",
        }),
    )
    with patch("app.services.keyword_lab.service.NaverAdsService",
               return_value=fake_ads):
        result = await svc.collect(blog_id=19)

    assert result["success"] is False, "성공으로 돌려주면 화면이 '0개' 라고만 말한다"
    assert "고객 ID" in result["error"]


@pytest.mark.asyncio
async def test_partial_failure_still_saves_what_it_got() -> None:
    """일부 시드만 실패하면 받은 것은 저장하고 오류는 함께 알린다."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.services.keyword_lab.service import KeywordLabService

    added = []
    db = SimpleNamespace(add=added.append, commit=AsyncMock())
    svc = KeywordLabService(db=db, settings=SimpleNamespace(), user_id=1)
    svc._existing_keywords = AsyncMock(return_value=set())

    calls = {"n": 0}

    async def _stats(keywords, include_related=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"success": True,
                    "keywords": [{"keyword": "전기기사", "total_search_volume": 900}],
                    "related_keywords": []}
        return {"success": False, "error": "호출 한도 초과"}

    fake_ads = SimpleNamespace(is_configured=lambda: True,
                               get_keyword_stats=_stats)
    with patch("app.services.keyword_lab.service.NaverAdsService",
               return_value=fake_ads):
        result = await svc.collect(seeds=[f"시드{i}" for i in range(1, 8)])

    assert result["success"] is True
    assert result["saved"] == 1
    assert "호출 한도 초과" in result["errors"]


def test_naver_ads_error_explains_what_to_fix() -> None:
    """상태 코드만 남기면 '403' 만 보이고 무엇을 고칠지 알 수 없다."""
    from types import SimpleNamespace

    from app.services.naver_ads_service import NaverAdsService

    svc = NaverAdsService(SimpleNamespace())
    resp = SimpleNamespace(
        status_code=403,
        json=lambda: {"detail": "Auth failed with api-key: 010..., customer-id: -1"},
        text="",
    )
    msg = svc._explain(resp)
    assert "고객 ID" in msg or "CUSTOMER_ID" in msg
    assert "customer-id: -1" in msg, "네이버가 준 사유를 그대로 올려야 한다"

    resp429 = SimpleNamespace(status_code=429, json=lambda: {}, text="")
    assert "한도" in svc._explain(resp429)


def test_connection_test_actually_calls_the_api() -> None:
    """키가 '채워져 있는지' 만 보면 잘못된 값도 통과한다."""
    src = (ROOT / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
    assert "get_keyword_stats" in src
    assert "search_blog" in src


def test_failure_is_shown_on_screen_not_only_toast() -> None:
    """토스트는 5초 뒤 사라져 무엇을 고칠지 다시 볼 수 없다."""
    page = (TEMPLATES / "keyword_lab/index.html").read_text(encoding="utf-8")
    assert 'x-show="failure"' in page
    assert "testConnection()" in page


# ── 네이버 hintKeywords 제약 ─────────────────────────────
def test_hint_keywords_drop_spaces() -> None:
    """네이버 keywordstool 은 공백이 든 키워드를 거부한다.

    실측:
        '음식 효능'      → 400 code 11001
        '음식효능'       → 200
        '레시피/조리법'   → 200   (슬래시는 괜찮다)

    **하나라도 섞이면 요청 전체가 실패한다.** 레시피노트의 카테고리
    이름에 공백이 있어 수집이 통째로 400 이었다.
    """
    from app.services.naver_ads_service import NaverAdsService

    out = NaverAdsService.normalize_hints(
        ["음식 효능", "조리법·손질", "자격증", "직업 정보"])
    # 가운뎃점은 두 개념이 붙은 것이라 나눈다 — 통째로 지우면
    # '조리법손질' 이라는 뜻 없는 합성어가 되어 연관어가 자기 자신뿐이다.
    assert out == ["음식효능", "조리법", "손질", "자격증", "직업정보"]
    assert all(" " not in k for k in out)
    assert all("·" not in k for k in out)


def test_hint_keywords_drop_empties_and_duplicates() -> None:
    """공백을 없애면 서로 같아지는 키워드가 생긴다."""
    from app.services.naver_ads_service import NaverAdsService

    out = NaverAdsService.normalize_hints(
        ["음식 효능", "음식효능", "  ", "", None, "음 식 효 능"])
    assert out == ["음식효능"]


def test_real_category_names_all_pass() -> None:
    """레시피노트 실제 카테고리 — 이 조합이 400 을 냈다.

    실제 API 로 확인: 정규화 후 9개 시드로 1,214건이 들어온다.
    """
    from app.services.naver_ads_service import NaverAdsService

    out = NaverAdsService.normalize_hints([
        "음식 효능", "요리 레시피", "조리법·손질",
        "보관·저장", "식재료 효능", "부작용·주의",
    ])
    assert out == ["음식효능", "요리레시피", "조리법", "손질",
                   "보관", "저장", "식재료효능", "부작용", "주의"]
    for kw in out:
        assert re.fullmatch(r"[0-9A-Za-z가-힣]+", kw), kw


@pytest.mark.asyncio
async def test_empty_after_normalize_is_reported() -> None:
    """전부 공백이면 조회할 것이 없다. 400 을 받으러 가지 않는다."""
    from types import SimpleNamespace

    from app.services.naver_ads_service import NaverAdsService

    svc = NaverAdsService(SimpleNamespace(has_naver_ads_api=True))
    result = await svc.get_keyword_stats(["   ", ""])
    assert result["success"] is False
    assert "키워드가 없습니다" in result["error"]


def test_400_error_explains_the_cause() -> None:
    from types import SimpleNamespace

    from app.services.naver_ads_service import NaverAdsService

    svc = NaverAdsService(SimpleNamespace())
    resp = SimpleNamespace(
        status_code=400,
        json=lambda: {"code": 11001,
                      "message": "hintKeywords 파라미터가 유효하지 않습니다."},
        text="",
    )
    msg = svc._explain(resp)
    assert "400" in msg
    assert "hintKeywords" in msg, "네이버가 준 사유가 담겨야 한다"


# ── 니치는 시드가 아니라 분류 결과 ───────────────────────
@pytest.mark.asyncio
async def test_niche_comes_from_classifying_each_keyword() -> None:
    """시드를 그대로 물려주면 안 된다.

    레시피노트를 고르고 시드에 '마라탕' 을 넣었더니 수집된 키워드가
    전부 '음식 효능'(첫 카테고리)으로 붙었다. 그러면 나중에 카테고리별로
    넘길 수가 없다. 키워드 하나하나를 분류해야 한다.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.services.keyword_lab.service import KeywordLabService

    added = []
    db = SimpleNamespace(add=added.append, commit=AsyncMock())
    svc = KeywordLabService(db=db, settings=SimpleNamespace(), user_id=1)
    svc._existing_keywords = AsyncMock(return_value=set())

    # 키워드마다 다른 카테고리를 돌려주는 매칭기
    table = {"마라탕": (12, 53), "마라탕 재료": (12, 54), "저금리대출": (9, 90)}

    async def _match(kw):
        t, s = table.get(kw, (None, None))
        return (t, s, None)

    svc._matcher = AsyncMock(return_value=SimpleNamespace(
        match_and_apply_to_keyword=_match))

    fake_ads = SimpleNamespace(
        is_configured=lambda: True,
        get_keyword_stats=AsyncMock(return_value={
            "success": True,
            "keywords": [{"keyword": "마라탕", "total_search_volume": 5000}],
            "related_keywords": [
                {"keyword": "마라탕 재료", "total_search_volume": 900},
                {"keyword": "저금리대출", "total_search_volume": 700},
            ],
        }),
    )
    with patch("app.services.keyword_lab.service.NaverAdsService",
               return_value=fake_ads):
        await svc.collect(seeds=["마라탕"])

    by_kw = {c.keyword: (c.topic_id, c.subtopic_id) for c in added}
    assert by_kw["마라탕"] == (12, 53)
    assert by_kw["마라탕 재료"] == (12, 54)
    assert by_kw["저금리대출"] == (9, 90), "시드 카테고리를 물려주면 안 된다"
    assert len({v for v in by_kw.values()}) == 3, "전부 같은 카테고리로 붙었다"


@pytest.mark.asyncio
async def test_unclassified_keyword_stays_unclassified() -> None:
    """분류가 안 되면 비워 둔다.

    시드 카테고리를 물려줬더니 「물류창고」와 「프랑스디저트」가 둘 다
    '음식 효능' 이 됐다. 틀린 분류는 미분류보다 나쁘다.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.services.keyword_lab.service import KeywordLabService

    added = []
    db = SimpleNamespace(add=added.append, commit=AsyncMock())
    svc = KeywordLabService(db=db, settings=SimpleNamespace(), user_id=1)
    svc._existing_keywords = AsyncMock(return_value=set())
    svc.seeds_for_blog = AsyncMock(return_value=[
        {"seed": "음식효능", "topic_id": 12, "subtopic_id": 53}])
    svc._matcher = AsyncMock(return_value=SimpleNamespace(
        match_and_apply_to_keyword=AsyncMock(return_value=(None, None, None))))

    fake_ads = SimpleNamespace(
        is_configured=lambda: True,
        get_keyword_stats=AsyncMock(return_value={
            "success": True,
            "keywords": [{"keyword": "듣도보도못한말", "total_search_volume": 300}],
            "related_keywords": [],
        }),
    )
    with patch("app.services.keyword_lab.service.NaverAdsService",
               return_value=fake_ads):
        await svc.collect(blog_id=19)

    assert added[0].topic_id is None and added[0].subtopic_id is None


def test_matcher_failure_does_not_stop_collection() -> None:
    """분류가 실패했다고 수집을 멈추면 안 된다. 니치는 보조 정보다."""
    src = (ROOT / "app/services/keyword_lab/service.py").read_text(
        encoding="utf-8")
    start = src.index("async def _classify(")
    end = src.index("async def _matcher(")
    assert "except Exception" in src[start:end], "분류 실패가 수집을 죽인다"
    assert "_matcher_cache" in src[end:], "매칭기 초기화 실패도 견뎌야 한다"


# ── 화면: 니치 열과 정렬 ─────────────────────────────────
def test_niche_column_replaces_seed_and_sorts() -> None:
    src = (ROOT / "app/static/js/keyword_lab/app.js").read_text(encoding="utf-8")
    block = re.search(r"listColumns\(\) \{\s*return \[(.*?)\];", src, re.S)
    assert block
    body = block.group(1)
    assert "'niche'" in body and "label: '니치'" in body
    assert "label: '시드'" not in body, "시드 열이 남아 있다"

    # 배지 열을 뺀 모든 열이 정렬 가능해야 한다
    for line in body.strip().splitlines():
        line = line.strip()
        if not line.startswith("{") or "_badges" in line:
            continue
        assert "sortable: true" in line, line


def test_seed_input_is_normalized_before_sending() -> None:
    """오류가 나기 전에 막는다. 서버와 같은 규칙을 쓴다."""
    src = (ROOT / "app/static/js/keyword_lab/app.js").read_text(encoding="utf-8")
    assert "normalizeSeeds(" in src
    assert "[^0-9A-Za-z가-힣]" in src


def test_api_returns_niche_name() -> None:
    """id 만 주면 화면에서 정렬도 검색도 할 수 없다."""
    src = (ROOT / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
    assert '"niche": _niche(r)' in src
    assert "미분류" in src
