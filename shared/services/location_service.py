"""
지역명 추출 및 비교 서비스

제목에서 한국 행정구역명을 추출하고 비교하는 기능을 제공합니다.
유사도 매칭 시 "지역이 다르면 그룹화하지 않음" 원칙의 기반이 됩니다.
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Set
import logging

logger = logging.getLogger(__name__)


class LocationService:
    """지역명 추출 및 비교 서비스 (싱글톤)"""

    _instance: Optional["LocationService"] = None
    _location_data: Optional[Dict] = None
    _lookup_cache: Optional[Dict[str, str]] = None

    def __new__(cls) -> "LocationService":
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """초기화 - 데이터가 없으면 로드"""
        if self._location_data is None:
            self._load_location_data()
            self._build_lookup_cache()

    def _load_location_data(self) -> None:
        """지역명 데이터 JSON 파일 로드"""
        data_path = Path(__file__).parent.parent / "data" / "korean_locations.json"

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                self._location_data = json.load(f)
            logger.info(f"[LOCATION] 지역명 데이터 로드 완료: {data_path}")
        except FileNotFoundError:
            logger.error(f"[LOCATION] 지역명 데이터 파일을 찾을 수 없습니다: {data_path}")
            self._location_data = {"provinces": {}, "cities": {}, "districts": {}}
        except json.JSONDecodeError as e:
            logger.error(f"[LOCATION] JSON 파싱 오류: {e}")
            self._location_data = {"provinces": {}, "cities": {}, "districts": {}}

    def _build_lookup_cache(self) -> None:
        """빠른 조회를 위한 역방향 캐시 구축"""
        self._lookup_cache = {}

        if not self._location_data:
            return

        # 시/도 및 별칭 캐싱
        for province, info in self._location_data.get("provinces", {}).items():
            self._lookup_cache[province] = ("province", province)
            for alias in info.get("aliases", []):
                self._lookup_cache[alias] = ("province", province)

        # 시/군 및 별칭 캐싱
        for city, info in self._location_data.get("cities", {}).items():
            self._lookup_cache[city] = ("city", city)
            for alias in info.get("aliases", []):
                self._lookup_cache[alias] = ("city", city)

        # 구 캐싱
        for district in self._location_data.get("districts", {}).keys():
            self._lookup_cache[district] = ("district", district)

        logger.debug(f"[LOCATION] 조회 캐시 구축 완료: {len(self._lookup_cache)}개 항목")

    def extract_location(self, title: str) -> Optional[Dict]:
        """
        제목에서 지역명 추출

        Args:
            title: 분석할 제목

        Returns:
            추출된 지역 정보 딕셔너리 또는 None
            {
                "province": "경북",
                "city": "포항",
                "district": "북구",
                "raw_text": "경북 포항시 북구"
            }
        """
        if not title or not self._location_data:
            return None

        result: Dict = {
            "province": None,
            "city": None,
            "district": None,
            "raw_text": None
        }
        matched_texts: List[str] = []

        # 1단계: 시/도 검색
        province_match = self._find_province(title)
        if province_match:
            result["province"] = province_match["name"]
            matched_texts.append(province_match["matched"])

        # 2단계: 시/군/구 검색
        city_match = self._find_city(title, result["province"])
        if city_match:
            result["city"] = city_match["name"]
            matched_texts.append(city_match["matched"])
            # 시에서 도를 유추
            if not result["province"]:
                result["province"] = city_match.get("province")

        # 3단계: 구 검색
        district_match = self._find_district(title, result["city"])
        if district_match:
            result["district"] = district_match["name"]
            matched_texts.append(district_match["matched"])

        # 결과 없으면 None
        if not result["province"] and not result["city"] and not result["district"]:
            logger.debug(f"[LOCATION] 지역명 없음: {title}")
            return None

        result["raw_text"] = " ".join(matched_texts)
        logger.debug(f"[LOCATION] 추출 결과: {title} -> {result}")
        return result

    def _find_province(self, title: str) -> Optional[Dict]:
        """시/도 찾기"""
        provinces = self._location_data.get("provinces", {})

        for province, info in provinces.items():
            # 정식 명칭 검색
            if province in title:
                return {"name": province, "matched": province}
            # 별칭 검색
            for alias in info.get("aliases", []):
                if alias in title:
                    return {"name": province, "matched": alias}

        return None

    def _find_city(self, title: str, province: Optional[str]) -> Optional[Dict]:
        """시/군 찾기"""
        cities = self._location_data.get("cities", {})

        for city, info in cities.items():
            # 시/도가 지정되었으면 해당 도 내에서만 검색
            if province and info.get("province") != province:
                continue

            # 정식 명칭 검색
            if city in title:
                return {
                    "name": city,
                    "matched": city,
                    "province": info.get("province")
                }
            # 별칭 검색
            for alias in info.get("aliases", []):
                if alias in title:
                    return {
                        "name": city,
                        "matched": alias,
                        "province": info.get("province")
                    }

        # 시/도 제한 없이 재검색
        if province:
            return self._find_city(title, None)

        return None

    def _find_district(self, title: str, city: Optional[str]) -> Optional[Dict]:
        """구 찾기"""
        districts = self._location_data.get("districts", {})

        for district, info in districts.items():
            # 시가 지정되었으면 해당 시 내 구만 검색
            if city and city not in info.get("cities", []):
                continue

            if district in title:
                return {"name": district, "matched": district}

        # 시 제한 없이 재검색
        if city:
            return self._find_district(title, None)

        return None

    def normalize_location(self, location: Optional[Dict]) -> str:
        """
        지역 정보를 표준화된 문자열로 변환

        Args:
            location: extract_location 결과

        Returns:
            표준화된 지역명 (예: "경북-포항", "서울-강남구", "")
        """
        if not location:
            return ""

        parts = []
        if location.get("province"):
            parts.append(location["province"])
        if location.get("city"):
            parts.append(location["city"])
        elif location.get("district"):
            parts.append(location["district"])

        return "-".join(parts)

    def is_same_location(
        self,
        loc1: Optional[Dict],
        loc2: Optional[Dict]
    ) -> bool:
        """
        두 지역이 동일한지 비교

        규칙:
        1. 둘 다 None이면 True (지역 없음끼리는 매칭 가능)
        2. 하나만 None이면 True (지역 없는 것과 있는 것은 매칭 가능)
        3. 둘 다 있으면 province+city 기준으로 비교

        Args:
            loc1: 첫 번째 지역 정보
            loc2: 두 번째 지역 정보

        Returns:
            동일 여부
        """
        # 둘 다 None
        if loc1 is None and loc2 is None:
            return True

        # 하나만 None (지역 없는 제목은 어디든 매칭 가능)
        if loc1 is None or loc2 is None:
            return True

        # 둘 다 지역 정보가 있는 경우
        norm1 = self.normalize_location(loc1)
        norm2 = self.normalize_location(loc2)

        # 정규화 결과가 비어있으면 매칭 가능
        if not norm1 or not norm2:
            return True

        # province가 같은지 먼저 확인
        prov1 = loc1.get("province")
        prov2 = loc2.get("province")

        if prov1 and prov2 and prov1 != prov2:
            return False

        # city가 있으면 city 비교
        city1 = loc1.get("city")
        city2 = loc2.get("city")

        if city1 and city2:
            return city1 == city2

        # 하나만 city가 있으면 province만 같으면 OK
        return True

    def remove_location_from_title(
        self,
        title: str,
        location: Optional[Dict]
    ) -> str:
        """
        제목에서 지역명 부분 제거

        Args:
            title: 원본 제목
            location: 추출된 지역 정보

        Returns:
            지역명이 제거된 제목
        """
        if not title or not location:
            return title

        result = title

        # 지역명 관련 텍스트 제거
        remove_patterns: List[str] = []

        if location.get("province"):
            province = location["province"]
            prov_info = self._location_data.get("provinces", {}).get(province, {})
            remove_patterns.append(province)
            remove_patterns.extend(prov_info.get("aliases", []))

        if location.get("city"):
            city = location["city"]
            city_info = self._location_data.get("cities", {}).get(city, {})
            remove_patterns.append(city)
            remove_patterns.extend(city_info.get("aliases", []))

        if location.get("district"):
            remove_patterns.append(location["district"])

        # 긴 패턴부터 제거 (더 구체적인 것 먼저)
        remove_patterns.sort(key=len, reverse=True)

        for pattern in remove_patterns:
            result = result.replace(pattern, "")

        # 연속 공백 정리
        result = re.sub(r"\s+", " ", result).strip()

        return result

    def get_all_location_names(self) -> Set[str]:
        """
        모든 지역명 목록 반환 (검색용)

        Returns:
            모든 지역명 세트
        """
        if not self._lookup_cache:
            return set()
        return set(self._lookup_cache.keys())


# 편의 함수
def extract_location(title: str) -> Optional[Dict]:
    """제목에서 지역명 추출 (편의 함수)"""
    return LocationService().extract_location(title)


def is_same_location(loc1: Optional[Dict], loc2: Optional[Dict]) -> bool:
    """두 지역 동일성 비교 (편의 함수)"""
    return LocationService().is_same_location(loc1, loc2)


def remove_location(title: str, location: Optional[Dict]) -> str:
    """제목에서 지역명 제거 (편의 함수)"""
    return LocationService().remove_location_from_title(title, location)


def normalize_location(location: Optional[Dict]) -> str:
    """지역 정보 정규화 (편의 함수)"""
    return LocationService().normalize_location(location)
