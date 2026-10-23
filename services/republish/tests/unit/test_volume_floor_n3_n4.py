"""N2 검색량 바닥선 · N3 90일 블로그 간 중복 · N4 최종 제목 지난 연도 (2026-10-23)."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.generation import lead_keyword as lk
from app.services.generation import lead_keyword_flow as lf
from app.services.generation import topic_gate as tg
from app.services.generation import volume_floor as vf
from app.services.generation.lead_keyword_pick import Candidate

OCT = date(2026, 10, 23)
NOW = datetime.now(timezone.utc)


class DB:
    async def commit(self):
        return None


def _title(**kw):
    base = dict(id=1, title="고흥석류 효능", cpa_offer_id=None, keywords=None,
                search_volume=None, search_volume_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_remembered_within_30_days():
    assert vf.remembered(_title(), 50) is None
    assert vf.remembered(_title(search_volume=20, search_volume_at=NOW), 50) is False
    assert vf.remembered(_title(search_volume=20, search_volume_at=NOW), 10) is True
    old = NOW - timedelta(days=31)
    assert vf.remembered(_title(search_volume=20, search_volume_at=old), 50) is None


def test_check_skips_low_records_volume_and_passes_on_failure(monkeypatch):
    blog = SimpleNamespace(id=1, name="잡학다식")
    on = {"title_lead_keyword": True}

    async def low(*a):
        return lk.Lead("low", None, 12)

    monkeypatch.setattr(lk, "measure", low)
    t = _title()
    msg = asyncio.run(vf.check(DB(), 1, blog, t, on))
    assert msg and "12회" in msg and t.search_volume == 12 and t.search_volume_at

    async def fail(*a):
        return lk.Lead("fail")

    monkeypatch.setattr(lk, "measure", fail)
    assert asyncio.run(vf.check(DB(), 1, blog, _title(), on)) is None       # 조회 실패 → 통과
    assert asyncio.run(vf.check(DB(), 1, blog, _title(), {})) is None       # 스위치 꺼짐
    assert asyncio.run(vf.check(DB(), 1, blog, _title(cpa_offer_id=3), on)) is None


def test_long_duplicate_uses_meaning_words():
    recent = [("굿팁꿀팁", 1, "직장인을 위한 내장지방 빼는 법 7가지 소개", 30),
              ("인생꿀팁", 2, "목이 뻐근할 때 꼭 알아야 할 관리법", 40),
              ("잡학다식", 3, "청주 콜택시 전화번호와 야간 요금 안내", 50)]
    assert tg.find_duplicate("직장인을 위한 피로 회복 7가지 비법", 9, recent) is None
    assert "90일" in tg.find_duplicate("목이 뻐근할 때 어떤 관리법이 좋을까", 9, recent)
    assert tg.find_duplicate("대구 콜택시 전화번호와 야간 요금 안내", 9, recent) is None
    # 7일 안은 지금 기준(넓음) 그대로
    assert tg.find_duplicate("직장인을 위한 피로 회복 7가지 비법", 9,
                             [("굿팁꿀팁", 1, "직장인을 위한 내장지방 빼는 법 7가지 소개", 3)])


def test_strip_past_year_final_title():
    assert tg.strip_past_year("HMM 배당금 지급일과 주주 필수 확인 사항 2023", OCT) == \
        "HMM 배당금 지급일과 주주 필수 확인 사항"
    assert tg.strip_past_year("방콕 대중교통 이용법과 요금 (2025년 업데이트)", OCT) == \
        "방콕 대중교통 이용법과 요금"
    assert tg.strip_past_year("2026년 근로장려금 신청", OCT) is None
    assert tg.strip_past_year("25년 근속 포상", OCT) is None
    assert tg.check_title("25년 상반기 달라진 청년 정책", OCT).code == "지난연도"


def test_finalize_adds_body_notes():
    c = Candidate("석류 효능", "stripped", 9050)
    title, notes = lf.finalize("석류 효능, 고흥 석류로 알아본 먹는 법", c, "instruction")
    assert title.startswith("석류 효능") and any("석류 효능" in n for n in notes)
    title, notes = lf.finalize("전기차 보조금 신청 2025", None, "none")
    assert "2025" not in title and any("과거형" in n for n in notes)
    s = lf.with_body({"a": 1}, notes)
    assert lf.body_notes(s) == notes and lf.with_body({"a": 1}, []) == {"a": 1}
