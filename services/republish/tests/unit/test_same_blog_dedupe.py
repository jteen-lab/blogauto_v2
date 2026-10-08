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
