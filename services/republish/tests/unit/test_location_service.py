"""
지역명 서비스 단위 테스트
"""

import pytest
import sys
import os

# shared 모듈 경로 추가
shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from services.location_service import (
    LocationService,
    extract_location,
    is_same_location,
    remove_location,
    normalize_location,
)


class TestExtractLocation:
    """지역명 추출 테스트"""

    def test_extract_province_city(self):
        """시/도 + 시/군 추출"""
        title = "경북 포항시 이삿짐센터 추천"
        loc = extract_location(title)

        assert loc is not None
        assert loc["province"] == "경북"
        assert loc["city"] == "포항"

    def test_extract_city_only(self):
        """시/군만 있는 경우"""
        title = "포항 이삿짐센터 포장이사 업체추천"
        loc = extract_location(title)

        assert loc is not None
        assert loc["city"] == "포항"

    def test_extract_full_address(self):
        """전체 주소 추출"""
        title = "경북 포항시 북구 기북면 대곡리 이삿짐센터"
        loc = extract_location(title)

        assert loc is not None
        assert loc["province"] == "경북"
        assert loc["city"] == "포항"
        assert loc["district"] == "북구"

    def test_extract_alias(self):
        """약칭 처리"""
        title = "경상북도 포항시 이삿짐센터"
        loc = extract_location(title)

        assert loc is not None
        assert loc["province"] == "경북"  # 정규화됨

    def test_no_location(self):
        """지역명 없는 제목"""
        title = "이삭토스트 맛집탐방 인기메뉴 총정리"
        loc = extract_location(title)

        assert loc is None

    def test_gyeonggi_ilsan(self):
        """경기도 일산 추출"""
        title = "일산 이삿짐센터 포장이사"
        loc = extract_location(title)

        assert loc is not None
        assert loc["city"] == "일산"
        # 경기도는 일산에서 유추됨
        if loc.get("province"):
            assert loc["province"] == "경기"

    def test_seoul_gangnam(self):
        """서울 강남구 추출"""
        title = "서울 강남구 맛집 추천"
        loc = extract_location(title)

        assert loc is not None
        assert loc["province"] == "서울"

    def test_busan(self):
        """부산 추출"""
        title = "부산 해운대 맛집 투어"
        loc = extract_location(title)

        assert loc is not None
        assert loc["province"] == "부산"


class TestIsSameLocation:
    """지역 동일성 비교 테스트"""

    def test_same_city(self):
        """같은 도시"""
        loc1 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}
        loc2 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}

        assert is_same_location(loc1, loc2) is True

    def test_different_city(self):
        """다른 도시"""
        loc1 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}
        loc2 = {"province": "경기", "city": "일산", "district": None, "raw_text": "경기 일산"}

        assert is_same_location(loc1, loc2) is False

    def test_same_province_different_city(self):
        """같은 도, 다른 시"""
        loc1 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}
        loc2 = {"province": "경북", "city": "경주", "district": None, "raw_text": "경북 경주"}

        assert is_same_location(loc1, loc2) is False

    def test_both_none(self):
        """둘 다 지역 없음"""
        assert is_same_location(None, None) is True

    def test_one_none(self):
        """한쪽만 지역 없음 - 매칭 허용"""
        loc1 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}

        assert is_same_location(loc1, None) is True
        assert is_same_location(None, loc1) is True

    def test_detailed_vs_simple(self):
        """상세 주소 vs 간단 주소"""
        loc1 = {"province": "경북", "city": "포항", "district": "북구", "raw_text": "경북 포항 북구"}
        loc2 = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}

        assert is_same_location(loc1, loc2) is True


class TestRemoveLocation:
    """지역명 제거 테스트"""

    def test_remove_from_start(self):
        """앞에서 지역명 제거"""
        title = "포항 이삿짐센터 포장이사"
        loc = extract_location(title)
        cleaned = remove_location(title, loc)

        assert "포항" not in cleaned
        assert "이삿짐센터" in cleaned

    def test_remove_full_address(self):
        """전체 주소 제거"""
        title = "경북 포항시 북구 기북면 이삿짐센터"
        loc = extract_location(title)
        cleaned = remove_location(title, loc)

        assert "경북" not in cleaned
        assert "포항" not in cleaned
        assert "이삿짐센터" in cleaned

    def test_no_location_to_remove(self):
        """제거할 지역 없음"""
        title = "이삭토스트 맛집탐방"
        cleaned = remove_location(title, None)

        assert cleaned == title

    def test_preserve_content(self):
        """콘텐츠 보존 확인"""
        title = "서울 맛집 베스트 10선"
        loc = extract_location(title)
        cleaned = remove_location(title, loc)

        assert "맛집" in cleaned
        assert "베스트" in cleaned


class TestNormalizeLocation:
    """지역 정규화 테스트"""

    def test_normalize_province_city(self):
        """시/도 + 시 정규화"""
        loc = {"province": "경북", "city": "포항", "district": None, "raw_text": "경북 포항"}
        normalized = normalize_location(loc)

        assert normalized == "경북-포항"

    def test_normalize_province_only(self):
        """시/도만 있는 경우"""
        loc = {"province": "서울", "city": None, "district": None, "raw_text": "서울"}
        normalized = normalize_location(loc)

        assert normalized == "서울"

    def test_normalize_none(self):
        """None 입력"""
        assert normalize_location(None) == ""


class TestLocationService:
    """LocationService 클래스 테스트"""

    def test_singleton(self):
        """싱글톤 패턴 확인"""
        service1 = LocationService()
        service2 = LocationService()

        assert service1 is service2

    def test_get_all_location_names(self):
        """모든 지역명 조회"""
        service = LocationService()
        names = service.get_all_location_names()

        assert isinstance(names, set)
        assert len(names) > 0
        # 주요 도시 포함 여부 확인
        assert "서울" in names or "서울특별시" in names
