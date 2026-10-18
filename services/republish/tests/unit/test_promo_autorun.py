"""오토런 홍보 링크 붙이기·제목 틀 정리 테스트.

순서도: docs/flowcharts/promo_link_autorun.md
"""
import asyncio
from types import SimpleNamespace

from app.services.generation.title_trim import trim
from app.services.promo import assembler, auto_attach

LINK = SimpleNamespace(
    name="다이사 이사 가격비교", url="https://appu.kr/?i=12538506",
    button_text="이사 견적 무료 비교하기", cpa_offer_id=None,
    notice="이 포스팅은 애드릭스 수익을 위해 작성되었습니다.")

ON = {"promo_link": {"auto": True, "exclude": ["지원사업", "전입신고"]}}

PATTERNS = {"title_strip_patterns": [
    r"^이사\s*견적(을)?\s*(받았다면|받은\s*(날|뒤|후)|받고(\s*나서)?|받아\s*든)\s+",
    r"\s*이대로\s*괜찮(은\s*걸까요?|을까요?)\s*$",
    r"\s*다\s*됐나요?\s*$",
    r"\s*이\s*정도면\s*적정한\s*걸까요?\s*$",
]}


def _run(html: str, title: str, settings: dict, monkeypatch, link=LINK) -> str:
    """링크 고르기를 흉내 내고 attach 를 돌린다."""
    async def _pick(db, t, blog_id=None):
        return link

    async def _url(db, lk, post_id=None, blog_id=None):
        return lk.url if lk else ""

    monkeypatch.setattr(auto_attach.link_service, "pick_by_keyword", _pick)
    monkeypatch.setattr(auto_attach.link_service, "tracked_url", _url)
    return asyncio.run(auto_attach.attach(None, html, title, 21, settings))


def test_스위치_꺼지면_그대로(monkeypatch) -> None:
    """모듈 설정이 없으면 다른 블로그 글은 지금과 같다."""
    assert _run("<p>본문</p>", "부산 이사업체 비교", {}, monkeypatch) == "<p>본문</p>"


def test_업체_글에_고지문과_버튼(monkeypatch) -> None:
    """켜진 모듈의 업체 글에는 고지문이 맨 위, 버튼이 맨 끝에 붙는다."""
    out = _run("<p>본문</p>", "부산 이사업체 잘하는 곳 비교", ON, monkeypatch)
    assert out.startswith('<p style="font-size:15px')
    assert out.endswith("이사 견적 무료 비교하기</a></div>")
    assert out.count("appu.kr") == 1


def test_제외_낱말이면_붙이지_않음(monkeypatch) -> None:
    """키워드는 맞아도 정보 글(지원사업)은 붙이지 않는다."""
    title = "국민기초생활보장수급자 이사비용 지원사업 신청하면 얼마나 나오나"
    assert _run("<p>본문</p>", title, ON, monkeypatch) == "<p>본문</p>"


def test_맞는_링크_없으면_그대로(monkeypatch) -> None:
    """맞는 링크가 없으면 정보 글로 나간다."""
    assert _run("<p>본문</p>", "잔금일 이삿날", ON, monkeypatch, link=None) == "<p>본문</p>"


def test_실패해도_글은_살린다(monkeypatch) -> None:
    """링크 고르기가 터져도 원래 본문을 돌려준다."""
    async def _boom(db, t, blog_id=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(auto_attach.link_service, "pick_by_keyword", _boom)
    out = asyncio.run(auto_attach.attach(None, "<p>본문</p>", "이사업체", 21, ON))
    assert out == "<p>본문</p>"


def test_작업대_재조립은_홍보분만_뗀다() -> None:
    """오토런이 붙인 고지문·버튼은 떼고 내부 링크 버튼은 남긴다."""
    body = '<p>본문</p>\n<div class="button-link"><a href="/p/1">관련 글</a></div>'
    done = assembler.assemble(body, LINK, tracked_url=LINK.url)
    assert assembler.strip_promo(done) == body


def test_제목_접두_꼬리_정리() -> None:
    """기계적으로 붙은 접두·꼬리를 지운다."""
    assert trim("이사 견적 받았다면 장기수선충당금 돌려받기 아파트와 오피스텔 차이",
                PATTERNS) == "장기수선충당금 돌려받기 아파트와 오피스텔 차이"
    assert trim("이사비용 줄이기 3가지 핵심만 알려드릴게요 이대로 괜찮은 걸까요",
                PATTERNS) == "이사비용 줄이기 3가지 핵심만 알려드릴게요"
    assert trim("전세보증금 못 받을 때 임차권등기명령 이사 전 준비 다 됐나",
                PATTERNS) == "전세보증금 못 받을 때 임차권등기명령 이사 전 준비"
    assert trim("이사 견적 받은 날 20평 아파트에서 꼭 해야 할 일 정리",
                PATTERNS) == "20평 아파트에서 꼭 해야 할 일 정리"


def test_제목_정리_안전장치() -> None:
    """설정 없음·너무 짧아짐·틀 오류면 원래 제목."""
    assert trim("이사 견적 받았다면 비용", {}) == "이사 견적 받았다면 비용"
    assert trim("이사 견적 받고 짐", PATTERNS) == "이사 견적 받고 짐"
    bad = {"title_strip_patterns": ["("]}
    assert trim("부산 이사업체 비교 정리", bad) == "부산 이사업체 비교 정리"
