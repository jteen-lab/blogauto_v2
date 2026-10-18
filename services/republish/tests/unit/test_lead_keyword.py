"""제목 맨 앞 검색어 — 검색량으로 고르기 (수작남 10/19 마케팅)."""
import pytest

from app.services.generation import lead_keyword as lk


def test_candidates_front_word_groups_then_keywords():
    c = lk.candidates("서울관악우체국 근무시간 전화번호 확인하기", ["관악우체국"])
    assert c[0] == "서울관악우체국 근무시간"
    assert "관악우체국" in c
    assert len(c) <= lk.MAX_CANDIDATES


def test_choose_prefers_multiword_with_volume():
    vols = {"마운자로어지러움": 320, "마운자로": 90000, "마운자로주사맞고": 0}
    assert lk.choose(vols, ["마운자로 어지러움", "마운자로 주사맞고", "마운자로"]) == (
        "마운자로 어지러움", 320)


def test_choose_falls_back_to_single_then_none():
    assert lk.choose({"마운자로": 900}, ["마운자로 주사", "마운자로"]) == ("마운자로", 900)
    assert lk.choose({"옷": 99999}, ["옷"]) is None


@pytest.mark.asyncio
async def test_apply_off_returns_same_settings():
    s = {"title_recombine": {"custom_prompt": "x"}}
    out, kw = await lk.apply(None, 1, s, "아무 제목")
    assert out is s and kw is None


@pytest.mark.asyncio
async def test_apply_appends_instruction_without_touching_original(monkeypatch):
    async def fake_volumes(db, user_id, cands):
        return {"관악우체국근무시간": 210}

    monkeypatch.setattr(lk, "_volumes", fake_volumes)
    s = {"title_lead_keyword": True, "title_recombine": {"custom_prompt": "규칙"}}
    out, kw = await lk.apply(None, 1, s, "관악우체국 근무시간 정리")
    assert kw == "관악우체국 근무시간"
    assert "「관악우체국 근무시간」" in out["title_recombine"]["custom_prompt"]
    assert s["title_recombine"]["custom_prompt"] == "규칙"


def test_starts_with_ignores_spaces():
    assert lk.starts_with("관악우체국근무시간 정리", "관악우체국 근무시간")
    assert not lk.starts_with("정리 관악우체국 근무시간", "관악우체국 근무시간")
    assert lk.starts_with("무엇이든", None)
