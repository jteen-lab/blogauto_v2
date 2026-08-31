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
