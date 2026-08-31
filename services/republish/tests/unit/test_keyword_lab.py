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
