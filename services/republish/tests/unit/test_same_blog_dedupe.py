"""같은 블로그 비슷한 제목 거르기(same_blog_dedupe) — 취업인포마스터 10/8."""
import asyncio
from types import SimpleNamespace

from app.services.generation import same_blog_dedupe as sb

REGIONS = {"김해", "경산", "수원", "강릉", "부산", "인천시", "수원시", "성남시"}


def test_normalize_drops_region_year_and_aliases():
    assert sb.normalize("2025년 김해 엘지전자 채용", REGIONS) == "lg전자 채용"
    assert sb.normalize("LG전자 채용", REGIONS) == "lg전자 채용"


def test_region_swap_is_same():
    assert sb.is_same("김해 알바천국 지역별 일자리 채용공고 확인",
                      "알바천국 경산 지역별 일자리 어떻게 찾을까", REGIONS)
    assert sb.is_same("2025 수원시 전기차 보조금", "2026 성남시 전기차 보조금 신청", REGIONS)


def test_template_words_alone_are_not_same():
    assert not sb.is_same("직장인을 위한 피로 회복 7가지 비법",
                          "직장인을 위한 내장지방 빼는 법 7가지 소개", REGIONS)
    assert not sb.is_same("정보처리기사 응시 자격 확인 방법과 서류 제출 기한",
                          "전기기사 응시 자격, 비전공자가 학력·경력으로 응시하는 경우 정리", REGIONS)


def test_blog_topic_words_are_ignored():
    recent = ["간호조무사 자격증 취득 방법은 어떻게 준비해야 할까",
              "미용사 자격증 취득 필수 비법", "플로리스트 자격증 취득 방법과 준비 과정",
              "산림치유지도사 자격증 취득법 준비 순서"]
    assert sb.find_similar("보육교사 1급 자격증 취득 방법", recent, REGIONS) is None
    assert sb.find_similar("간호조무사 자격증 취득 방법 준비", recent, REGIONS) == recent[0]


def test_switch_off_does_nothing():
    blog, title = SimpleNamespace(id=17), SimpleNamespace(id=1, title="김해 알바천국")
    assert asyncio.run(sb.apply(None, blog, title, {})) is None
    assert asyncio.run(sb.apply(None, blog, title, None)) is None


def test_strong_overlap_only_in_long_mode():
    """말끝만 다른 제목 — 기본은 통과, 긴 기간 모드(strong=4)는 같은 글 (인생꿀팁 10/23)."""
    a = "농협카드 등록 유효기간 체크하지 않으면 결제 차단됩니다"
    b = "농협카드 등록 유효기간 놓치면 결제 차단될 수 있습니다"
    assert not sb.is_same(a, b, REGIONS)
    assert sb.is_same(a, b, REGIONS, strong=sb.STRONG_SHARED)
    assert not sb.is_same("NH농협카드 사용내역 간편하게 조회하는 방법과 팁",
                          "농협카드 분실신고 방법은 무엇인가요", REGIONS, strong=sb.STRONG_SHARED)


def test_sibling_site_titles_found():
    """잡학다식(형제 사이트) 9월 글과 같은 주제면 건너뛴다."""
    recent = ["은행별 통장사본 출력 방법 1분 만에 해결하기",
              "목걸이 체인 종류별 튼튼함과 관리법 5가지 알아보기"]
    hit = sb.find_similar("통장사본 출력 은행별 PC와 모바일로 쉽게 해결하는 방법",
                          recent, REGIONS, strong=sb.STRONG_SHARED)
    assert hit == recent[0]


def _fake_apply(monkeypatch, recent_rows, history_rows, site_ids):
    calls = {}

    async def fake_recent(db, blog_id, days=sb.DAYS):
        calls["recent"] = (blog_id, days)
        return recent_rows

    async def fake_history(db, ids, days):
        calls["history"] = (list(ids), days)
        return history_rows

    async def fake_site(db, blog):
        return site_ids

    monkeypatch.setattr(sb, "recent_titles", fake_recent)
    monkeypatch.setattr(sb, "history_titles", fake_history)
    monkeypatch.setattr(sb, "_site_blog_ids", fake_site)
    return calls


def test_old_keys_absent_keeps_60day_path(monkeypatch):
    calls = _fake_apply(monkeypatch, ["통장사본 출력 은행별 방법"], [], [14, 9])
    blog, title = SimpleNamespace(id=14), SimpleNamespace(id=1, title="통장사본 출력 은행별 방법 정리")
    msg = asyncio.run(sb.apply(None, blog, title, {"dedupe_same_blog": True}))
    assert calls == {"recent": (14, sb.DAYS)}
    assert msg.startswith("제목 관문(같은블로그중복) — 60일 안에 이 블로그에")


def test_long_mode_uses_sibling_history(monkeypatch):
    calls = _fake_apply(monkeypatch, [], ["은행별 통장사본 출력 방법 1분 만에 해결하기"], [14, 9, 7, 8])
    blog = SimpleNamespace(id=14)
    title = SimpleNamespace(id=2, title="통장사본 출력 은행별 PC와 모바일로 쉽게 해결하는 방법")
    settings = {"dedupe_same_blog": True, "dedupe_same_blog_days": 0, "dedupe_sibling_sites": True}
    msg = asyncio.run(sb.apply(None, blog, title, settings))
    assert calls == {"history": ([14, 9, 7, 8], 0)}
    assert "지금까지 같은 사이트(형제 블로그 포함)에" in msg
