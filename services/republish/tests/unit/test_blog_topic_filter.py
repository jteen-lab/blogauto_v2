"""모듈 거름망 — 지운 주제 잠시 피하기·피할 주제 유형 (수작남 10/19 마케팅)."""
from datetime import date

import pytest

from app.services.generation import blog_topic_filter as btf

DELETED = ["1365 자원봉사 참여 방법 안내", "일요일 당번약국 어떻게 찾나",
           "직장인을 위한 내장지방 감소법 7가지", "마운자로 주사 맞고 어지러움 지속되나요"]
SETTINGS = {
    "avoid_topics": {"until": "2026-11-16", "titles": DELETED},
    "skip_title_patterns": [{"pattern": r"근무\s*시간|홈페이지", "label": "공식 사이트 우세"}],
}
TODAY = date(2026, 10, 20)


@pytest.mark.parametrize("title", [
    "1365 자원봉사 홈페이지 통해서 봉사 참여하는 방법",
    "일요일 당번약국 찾는 방법과 네이버 지도로 빠르게 확인하는 법",
    "직장인을 위한 내장지방 빼는 법 7가지 소개",
    "마운자로 주사 맞고 어지러움이 계속된다면",
])
def test_october_rewrites_are_avoided(title):
    """마케팅 표의 10월 새 글은 지운 글과 같은 주제로 잡혀야 한다."""
    assert btf.avoided(title, SETTINGS["avoid_topics"], TODAY)


@pytest.mark.parametrize("title", [
    "훠궈 육수 베이스 종류별 차이와 취향에 맞게 고르는 방법",
    "전국 캠핑장별 장단점 비교 가족에게 맞는 곳 고르는 법",
])
def test_new_subjects_pass(title):
    assert btf.avoided(title, SETTINGS["avoid_topics"], TODAY) is None


def test_avoid_expires_after_until():
    assert btf.avoided("마운자로 주사 맞고 어지러움이 계속된다면",
                       SETTINGS["avoid_topics"], date(2026, 11, 17)) is None


def test_pattern_skip_and_verdict_message():
    msg = btf.verdict("관악우체국 근무시간과 위치", {"skip_title_patterns":
                                                SETTINGS["skip_title_patterns"]}, TODAY)
    assert msg and "피할주제" in msg and "근무시간" in msg


def test_bad_regex_is_ignored():
    assert btf.skipped_by_pattern("아무 제목", [{"pattern": "("}]) is None


def test_no_settings_passes():
    assert btf.verdict("아무 제목", None, TODAY) is None
    assert btf.verdict("아무 제목", {"avoid_topics": "잘못된 값"}, TODAY) is None


@pytest.mark.asyncio
async def test_apply_returns_reason():
    class T:
        id = 1
        title = "일요일 당번약국 찾는 방법"

    class B:
        id = 13
    msg = await btf.apply(None, B(), T(), {"avoid_topics": {"until": "2099-01-01",
                                                          "titles": DELETED}})
    assert msg and "지운주제" in msg
