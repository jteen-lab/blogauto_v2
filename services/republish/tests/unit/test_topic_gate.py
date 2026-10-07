"""제목 관문(topic_gate)·건강 글 보류(health_hold) — 마케팅 고칠 목록 10/7."""
import asyncio
from datetime import date
from types import SimpleNamespace

from app.services.generation import health_hold, topic_gate as tg
from app.services.reference import health_sources as hs

OCT = date(2026, 10, 7)


def _code(title, today=OCT):
    v = tg.check_title(title, today)
    return v.code if v else None


def test_risky_contact_and_timetable_blocked():
    assert _code("안산 시외버스터미널 전화번호 운행 정보 예매 주차 시간표 안내") == "위험주제"
    assert _code("광명 지하철 시간표와 KTX 셔틀 전동열차 필수 체크리스트") == "위험주제"
    assert tg.check_title("롯데카드 고객센터 전화번호", OCT).permanent


def test_past_year_blocked_current_year_ok():
    assert _code("2025년 전기차 보조금 신청 가이드") == "지난연도"
    assert _code("수원시 전기차 보조금 2025 상반기 차종별 현황") == "지난연도"
    assert _code("2026년 전기차 보조금 신청 가이드") is None
    assert _code("2027년 최저임금 전망") is None


def test_loan_products_blocked():
    for t in ("굿모닝캐피탈 대부 대출 상품과 금리 신청 방법 총정리",
              "유미캐피탈대부 대출 조건과 장단점 소개",
              "해피머니론 단박300 소액대출 신청 조건과 방법 알아보기",
              "삼호 저축은행 대출조건과 신청 팁 정리",
              "현대카드 카드론 금리 비교"):
        assert _code(t) == "대출상품", t
    assert tg.check_title("유미캐피탈대부 대출", OCT).reason == "대부업체"


def test_loan_words_that_are_not_products():
    for t in ("햇살론 신청 조건과 한도 정리", "보금자리론 금리 2026",
              "토론 잘하는 법 정리", "결론부터 말하는 글쓰기", "대부분의 사람이 모르는 절약 팁",
              "청년 전세대출 조건 정리"):
        assert _code(t) is None, t


def test_out_of_season_skipped_not_archived():
    v = tg.check_title("봄 제철 보약으로 즐기는 봄동 효능과 요리법 안내", OCT)
    assert v.code == "제철아님" and not v.permanent
    assert _code("봄동 효능과 손질법", date(2026, 1, 10)) is None
    assert _code("봄동 효능과 손질법", date(2026, 11, 20)) is None   # 한 달 전 허용
    assert _code("김장 김치 황금 레시피") is None                     # 10월은 김장철
    assert _code("수박 고르는 법", OCT) == "제철아님"
    assert _code("방어운전 요령 정리") is None


def test_normal_titles_pass():
    for t in ("소고기 미역국 황금 레시피", "윈도우 11 설치 순서 정리",
              "69년생 국민연금 개시일과 소득 대응 전략"):
        assert tg.check_title(t, OCT) is None, t


def test_duplicate_other_blog_same_topic():
    recent = [("인생꿀팁", 5894, "테슬라 삼성 카드 결제 방법과 혜택 정리")]
    assert tg.find_duplicate("테슬라 삼성카드 결제 방법과 혜택은 무엇인가", 1, recent)
    assert tg.find_duplicate("아무 제목", 5894, recent)            # 같은 정식제목
    assert tg.find_duplicate("소고기 미역국 황금 레시피", 2, recent) is None


def test_apply_archives_permanent_and_skips_temporary(monkeypatch):
    class DB:
        commits = 0

        async def commit(self):
            DB.commits += 1

    async def no_recent(db, blog_id):
        return []

    monkeypatch.setattr(tg, "_recent_other_posts", no_recent)
    blog = SimpleNamespace(id=1, name="머니조아")
    loan = SimpleNamespace(id=9, title="삼호 저축은행 대출조건", status="available", hold_reason=None)
    msg = asyncio.run(tg.apply(DB(), blog, loan))
    assert msg and loan.status == "archived" and "대출상품" in loan.hold_reason
    spring = SimpleNamespace(id=10, title="수박 화채 만들기", status="available", hold_reason=None)
    assert asyncio.run(tg.apply(DB(), blog, spring))
    assert spring.status == "available"
    ok = SimpleNamespace(id=11, title="소고기 미역국 레시피", status="available", hold_reason=None)
    assert asyncio.run(tg.apply(DB(), blog, ok)) is None


def test_health_topic_sees_title_even_with_topic_names():
    assert hs.is_health_topic(["음식/레시피", "부작용·주의"], "카무트 효능과 부작용")
    assert hs.is_health_topic(["음식/레시피", "한식"], "마늘 효능 총정리")
    assert not hs.is_health_topic(["금융", "대출"], "청년 전세대출 조건")


def test_homepages_are_not_citations():
    assert hs.is_homepage("https://health.kdca.go.kr/")
    assert hs.is_homepage("https://www.foodsafetykorea.go.kr/")
    assert not hs.is_homepage("https://www.mfds.go.kr/brd/m_768/view.do?seq=3693")
    docs = [SimpleNamespace(url="https://health.kdca.go.kr/", title="포털"),
            SimpleNamespace(url="https://www.nics.go.kr/food/kfi/x?id=1", title="농식품올바로")]
    refs = hs.official_refs(docs)
    assert len(refs) == 1 and "농촌진흥청" in refs[0]["org"]


def test_health_without_official_is_held():
    class DB:
        async def commit(self):
            pass

    title = SimpleNamespace(hold_count=0, last_held_at=None, hold_reason=None)
    ref = SimpleNamespace(health=True, official_refs=0)
    assert asyncio.run(health_hold.hold_if_unsourced(DB(), title, ref, "카무트"))
    assert title.hold_count == 1 and "공식 출처" in title.hold_reason
    ok = SimpleNamespace(health=True, official_refs=2)
    assert asyncio.run(health_hold.hold_if_unsourced(DB(), title, ok, "x")) is None
    assert not health_hold.needs_hold(SimpleNamespace(health=False, official_refs=0))
