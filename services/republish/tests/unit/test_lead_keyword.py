"""제목 맨 앞 검색어 — 검색량으로 고르기 (수작남 10/19 · N1 확장 10/23 마케팅)."""
import pytest

from app.services.generation import lead_keyword as lk
from app.services.generation import lead_keyword_pick as pk
from app.services.generation.lead_keyword_pick import Candidate

REGIONS = {"고흥", "청주", "대구", "서울", "원주"}


def test_title_candidates_front_groups_keywords_and_stripped():
    c = pk.title_candidates("고흥석류 효능 7가지 정리", ["석류"], REGIONS)
    texts = [x.text for x in c]
    assert texts[0] == "고흥석류 효능"
    assert "석류 효능" in texts and any(x.source == "stripped" for x in c)


def test_segment_keeps_title_words_and_generic_only():
    assert pk.segment("석류효능", "고흥석류 효능 7가지") == "석류 효능"
    assert pk.segment("하이패스등록방법", "하이패스 등록이 필요하다면 이렇게") == "하이패스 등록 방법"
    assert pk.segment("비타민c효능", "고흥석류 효능 7가지") is None      # 새 낱말
    assert pk.segment("국민은행대출", "우리은행 아파트담보대출 조건") is None
    assert pk.segment("효능", "고흥석류 효능 7가지") is None              # 일반어뿐


def test_choose_prefers_multiword_and_floor():
    c = [Candidate("마운자로 어지러움", "title", 320), Candidate("마운자로", "title", 90000),
         Candidate("마운자로 주사맞고", "title", 0)]
    assert pk.choose(c).text == "마운자로 어지러움"
    assert pk.choose([Candidate("마운자로 주사", "title", 40)]) is None   # 바닥선 50
    assert pk.choose([Candidate("마운자로", "title", 900)]).text == "마운자로"


def test_choose_related_when_much_bigger_else_title_side():
    t = Candidate("하이패스 등록", "title", 6000)
    r = Candidate("하이패스 등록 방법", "related", 7830)
    assert pk.choose([t, r]).text == "하이패스 등록"            # 1.5배 안 → 원래 제목 쪽
    t.volume = 100
    assert pk.choose([t, r]).text == "하이패스 등록 방법"


def test_choose_big_word_prefers_longer_phrase():
    big = Candidate("닭볶음탕 레시피", "related", 59910, "높음")
    longer = Candidate("닭볶음탕 레시피 황금비율", "related", 3200, "높음")
    assert pk.choose([big, longer]).text == "닭볶음탕 레시피 황금비율"
    assert pk.choose([big]).text == "닭볶음탕 레시피"


def test_choose_region_lead_keeps_region_bundle():
    c = [Candidate("청주 콜택시", "title", 900), Candidate("콜택시 요금", "related", 5000)]
    assert pk.choose(c, region_first=True).text == "청주 콜택시"
    assert pk.choose(c, region_first=False).text == "콜택시 요금"


def test_judge_uses_related_keywords(monkeypatch):
    monkeypatch.setattr(lk, "_regions", lambda: REGIONS)
    stats = {"고흥석류효능": (5, "낮음"), "석류효능": (9050, "중간"),
             "비타민c효능": (20000, "높음"), "석류": (30000, "높음")}
    lead = lk.judge(stats, "고흥석류 효능 7가지 정리", [], 50)
    assert lead.status == "ok" and lead.pick.text == "석류 효능"
    assert lk.judge({"고흥석류효능": (5, "")}, "고흥석류 효능", [], 50).status == "low"


@pytest.mark.asyncio
async def test_apply_off_returns_same_settings():
    s = {"title_recombine": {"custom_prompt": "x"}}
    out, kw = await lk.apply(None, 1, s, "아무 제목")
    assert out is s and kw is None


@pytest.mark.asyncio
async def test_apply_appends_instruction_and_cpa_only_records(monkeypatch):
    async def fake_measure(db, user_id, title, keywords, low):
        return lk.Lead("ok", Candidate("관악우체국 근무시간", "title", 210), 210)

    monkeypatch.setattr(lk, "measure", fake_measure)
    s = {"title_lead_keyword": True, "title_recombine": {"custom_prompt": "규칙"}}
    out, kw = await lk.apply(None, 1, s, "관악우체국 근무시간 정리")
    assert kw.text == "관악우체국 근무시간"
    assert "「관악우체국 근무시간」" in out["title_recombine"]["custom_prompt"]
    assert s["title_recombine"]["custom_prompt"] == "규칙"
    out2, kw2 = await lk.apply(None, 1, s, "관악우체국 근무시간 정리", cpa=True)
    assert out2 is s and kw2.text == "관악우체국 근무시간"


def test_floor_from_settings():
    assert lk.floor({}) == 50
    assert lk.floor({"title_lead_floor": 10}) == 10


def test_starts_with_ignores_spaces():
    assert lk.starts_with("관악우체국근무시간 정리", "관악우체국 근무시간")
    assert not lk.starts_with("정리 관악우체국 근무시간", "관악우체국 근무시간")
    assert lk.starts_with("무엇이든", None)


def test_fit_puts_keyword_first_and_keeps_rest_short():
    out = lk.fit("하이패스 등록이 필요하다면 꼭 알아야 할 신청 순서와 준비물 총정리", "하이패스 등록")
    assert out.startswith("하이패스 등록, ")
    assert len(out.split(", ", 1)[1]) <= 30
    assert lk.fit("하이패스 등록", "하이패스 등록") == "하이패스 등록"
