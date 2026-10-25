"""리뉴얼 검수 반영(10/25 마케팅) — 사실 관문·카드 글자·검색어 core·자기 링크."""
import asyncio
import json

from app.services.generation import lead_keyword_pick as pick
from app.services.generation.card_text import card_text, fix_orphan
from app.services.renewal import renewal_fact as rf
from app.services.renewal.renewal_record import MIN_REWRITE, strip_self_links


class FakeAI:
    """차례대로 답을 돌려주는 가짜 AI."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    async def generate(self, **kw):
        self.calls += 1
        a = self.answers.pop(0) if self.answers else {"items": []}
        return {"content": json.dumps(a, ensure_ascii=False)}


def test_card_text_drops_year_brackets_and_tail():
    assert card_text("경찰서 민원실 업무시간과 점심시간 토요일 근무 (2026년 기준)") == \
        "경찰서 민원실 업무시간과 점심시간 토요일 근무"
    assert card_text("셀프염색할 때 꿀팁 / 셀프염색하는 방법 참고하세요.") == "셀프염색할 때 꿀팁"
    assert card_text("2026년 최저임금 인상 내용 정리") == "최저임금 인상 내용 정리"
    assert card_text("고추냉이 와사비 차이와 활용하는 법") == "고추냉이 와사비 차이와 활용하는 법"
    assert card_text("짧음, 뒤가 긴 제목입니다") == "짧음, 뒤가 긴 제목입니다"


def test_fix_orphan_moves_last_word():
    assert fix_orphan(["고추냉이 와사비 차이와 활용하는", "법"], lambda t: True) == \
        ["고추냉이 와사비 차이와", "활용하는 법"]
    assert fix_orphan(["가나다 라마", "바사"], lambda t: True) == ["가나다 라마", "바사"]
    assert fix_orphan(["가나다 라마", "법"], lambda t: False) == ["가나다 라마", "법"]


def test_core_candidate_finds_tail_noun_phrase():
    t = "아파트와 공동주택의 완강기 설치 기준"
    cands = pick.title_candidates(t, None, set())
    assert "완강기 설치 기준" in [c.text for c in cands if c.source == "core"]
    assert pick.hints(cands, t)[0] == "완강기 설치 기준"
    c = next(c for c in cands if c.text == "완강기 설치 기준")
    c.volume = 2250
    assert pick.choose(cands + [pick.Candidate("아파트 완강기", "related", 310)]).text == \
        "완강기 설치 기준"


def test_core_skips_generic_and_verbs():
    assert pick.core_words(pick.words("온누리상품권 구매처와 할인 한도 안내")) == []
    assert pick.core_words(pick.words("고추냉이 와사비 차이와 활용하는 법")) == []
    assert pick.core_words(pick.words("제습기 전기세 아끼는 5가지 꿀팁")) == []


def test_strip_self_links():
    h = ('<p>a</p>\n<div class="button-link"><a href="https://fund.doooit082.com/613/">제습기</a></div>\n'
         '<p>x <a href="https://fund.doooit082.com/613">자기</a> '
         '<a href="https://fund.doooit082.com/600/">남</a></p>')
    out = strip_self_links(h, "https://fund.doooit082.com/613/")
    assert "/613" not in out and "자기" in out and "/600/" in out
    assert strip_self_links(h, "") == h


def test_scrub_claims_removes_fake_experience_and_crowd():
    h = ("<p>해열제는 체온을 보고 먹입니다. 제 아이도 처음 열이 났을 때 당황했어요. "
         "실제로 많은 사용자들이 이 방법으로 전기세를 줄였다고 보고하고 있습니다.</p>"
         "<p>필자는 최근 시장에서 실감했습니다.</p>")
    out, removed = rf.scrub_claims(h)
    assert len(removed) == 3
    assert "해열제는 체온을 보고 먹입니다." in out and "필자" not in out and "<p></p>" not in out


def test_strict_topic():
    assert rf.strict_topic("온누리상품권 구매처와 할인 한도 안내") == "금액(할인율·한도·지원금)"
    assert rf.strict_topic("아파트 완강기 설치 기준") == "법령(과태료·기준)"
    assert rf.strict_topic("아기 해열제 용량") == "건강(약 용량·간격)"
    assert rf.strict_topic("고추냉이 와사비 차이") is None
    assert rf.strict_topic("이유식 만들기", "<p>하루 200ml</p>") == "건강(약 용량·간격)"


def test_gate_premise_returned_first():
    ai = FakeAI([{"premise": "고추냉이=와사비", "items": []}])
    out = asyncio.run(rf.run(ai, "<p>고추냉이는 겨자무입니다.</p>", "", "고추냉이 와사비 차이"))
    assert out.premise == "고추냉이=와사비" and out.hold is None


def test_gate_strict_holds_when_errors_left():
    bad = {"sentence": "법인은 10만 원 할인됩니다.", "confidence": "높음", "reason": "근거 없음"}
    ai = FakeAI([{"premise": "", "items": [bad]},
                 {"fixes": [{"sentence": bad["sentence"], "replacement": "법인 10만 원 할인."}]},
                 {"premise": "", "items": [dict(bad, sentence="법인 10만 원 할인.")]}])
    out = asyncio.run(rf.run(ai, "<p>법인은 10만 원 할인됩니다.</p>", "", "온누리상품권 할인 한도"))
    assert out.hold and out.hold.startswith("금액")


def test_gate_loose_topic_deletes_left_sentences():
    bad = {"sentence": "와사비는 5천 원입니다.", "confidence": "높음", "reason": "근거 없음"}
    ai = FakeAI([{"premise": "", "items": [bad]}, {"fixes": []},
                 {"premise": "", "items": []}])
    out = asyncio.run(rf.run(ai, "<p>맛있어요. 와사비는 5천 원입니다.</p>", "", "고추냉이 와사비 차이",
                             allow_premise=False))
    assert out.hold is None and "5천" not in out.html and "맛있어요." in out.html


def test_gate_check_failure_holds_only_strict():
    class Broken:
        async def generate(self, **kw):
            raise RuntimeError("x")
    strict = asyncio.run(rf.run(Broken(), "<p>a.</p>", "", "완강기 설치 기준"))
    loose = asyncio.run(rf.run(Broken(), "<p>a.</p>", "", "제습기 전기세"))
    assert strict.hold and loose.hold is None


def test_min_rewrite():
    assert MIN_REWRITE == 1300


def test_after_premise_rewrite_check_failure_holds():
    class Broken:
        async def generate(self, **kw):
            return None
    out = asyncio.run(rf.run(Broken(), "<p>a.</p>", "", "고추냉이 와사비 차이", allow_premise=False))
    assert out.hold == "사실 검사 호출 실패"


def test_after_premise_rewrite_premise_left_holds():
    ai = FakeAI([{"premise": "아직 틀림", "items": []}, {"premise": "아직 틀림", "items": []}])
    out = asyncio.run(rf.run(ai, "<p>a.</p>", "", "고추냉이 와사비 차이", allow_premise=False))
    assert out.hold and out.hold.startswith("전제를 바로잡지 못함")


def test_scrub_plain_first_person():
    out, removed = rf.scrub_claims("<p>저는 일본 요리를 사랑합니다. 와사비는 뿌리입니다.</p>")
    assert removed and "와사비는 뿌리입니다." in out


def test_drop_title_tails():
    from app.services.renewal.renewal_title import _drop_tails
    assert _drop_tails("제습기 전기세 절약 방법 알아보기 뽀송하게 유지하는 꿀팁") == \
        "제습기 전기세 절약 방법과 뽀송하게 유지하는 꿀팁"


def test_plain_math_and_more_vague():
    h = r"<p>\[ \text{전기세} = 300W \times 8 \text{시간} \times \frac{1 \text{kW}}{1000 \text{W}} = 360원 \]</p>"
    out = rf.plain_math(h)
    assert "\\" not in out and "300W × 8" in out and "1 kW/1000 W" in out
    _, removed = rf.scrub_claims("<p>사용자들은 이 기능 덕분에 줄였다고 말합니다. 전기세 절약 효과가 있다는 보고도 있습니다. 1등급이 낫습니다.</p>")
    assert len(removed) == 2


def test_title_awkward_particle_joined():
    from app.services.renewal.renewal_title import _drop_tails
    assert _drop_tails("제습기 전기세 절약 방법은 뽀송하게 유지하는 꿀팁") == \
        "제습기 전기세 절약 방법과 뽀송하게 유지하는 꿀팁"
    assert _drop_tails("전기요금 누진 차이는 이렇게 줄이는 팁") == "전기요금 누진 차이와 이렇게 줄이는 팁"
    assert _drop_tails("에어컨 요금 계산 방법은 무엇일까요") == "에어컨 요금 계산 방법"
    for keep in ("제습기 전기세 계산법과 줄이는 꿀팁", "제습기 전기세 계산 방법 정리",
                 "완강기 설치 기준과 아파트 세대점검 정리"):
        assert _drop_tails(keep) == keep


def test_rewrite_text_month_and_weak_cause():
    from app.services.renewal.renewal_generator import _REWRITE_TEXT
    assert "72kWh" in _REWRITE_TEXT and "한전 요금표" in _REWRITE_TEXT and "1,800자" in _REWRITE_TEXT
    assert "근거 약한 인과" in rf.CHECK_PROMPT
    rf.CHECK_PROMPT.format(title="t", refs="r", body="b")  # 중괄호 깨짐 없음
