"""
캐노니컬 키 생성 서비스

캐노니컬 키: 제목의 핵심 요소를 정규화한 고유 식별자
형식: {지역}|{장소}|{주제}

완전 일치 시 100% 유사도로 즉시 그룹핑
"""

from typing import Optional, List, Dict
import re
import logging
from .location_service import LocationService

logger = logging.getLogger(__name__)


class CanonicalKeyService:
    """캐노니컬 키 생성 서비스 (싱글톤)"""

    _instance: Optional["CanonicalKeyService"] = None

    def __new__(cls) -> "CanonicalKeyService":
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """초기화"""
        if self._initialized:
            return

        self.location_service = LocationService()
        self._build_patterns()
        self._initialized = True
        logger.info("[CANONICAL] CanonicalKeyService 초기화 완료")

    def _build_patterns(self) -> None:
        """키워드 추출용 패턴"""
        # 장소/기관 키워드 (확장 가능)
        self.place_keywords = [
            # 의료기관
            "병원", "의원", "한의원", "치과", "안과", "피부과", "성형외과",
            "대학병원", "종합병원", "요양병원", "재활병원",
            # 장례/예식
            "장례식장", "예식장", "웨딩홀", "컨벤션",
            # 숙박/레저
            "호텔", "리조트", "펜션", "모텔", "콘도",
            # 교육기관
            "대학교", "대학", "고등학교", "중학교", "초등학교", "유치원",
            # 주거
            "아파트", "빌라", "오피스텔", "주상복합", "타운하우스",
            # 상업
            "백화점", "마트", "쇼핑몰", "시장", "아울렛",
            # 종교
            "교회", "성당", "사찰", "절", "법당",
            # 기타
            "공원", "체육관", "수영장", "골프장", "스포츠센터",
        ]

        # 서비스/주제 키워드 (확장 가능)
        self.service_keywords = [
            # 화환 관련 (우선순위 높음)
            "근조화환", "경조화환", "장례식화환", "조화", "화환",
            "축하화환", "개업화환", "취임화환", "승진화환",
            "근조화환오브제", "근조화환당일", "근조화환배달",
            "장례식조화가격", "경조사화환",
            # 꽃배달
            "꽃배달", "플라워", "꽃바구니", "꽃다발", "생화",
            # 장례식장 관련 서비스
            "장례식장",
        ]

        # 서비스 키워드 정규화 맵 (유사 키워드 → 대표 키워드)
        # 핵심: 모든 화환/조화 관련 키워드는 "화환"으로 통일
        self.service_normalization = {
            # 화환 계열 - 모두 "화환"으로 통일
            "근조화환": "화환",
            "경조화환": "화환",
            "장례식화환": "화환",
            "조화": "화환",
            "축하화환": "화환",
            "개업화환": "화환",
            "취임화환": "화환",
            "승진화환": "화환",
            "근조화환오브제": "화환",
            "근조화환당일": "화환",
            "근조화환배달": "화환",
            "장례식조화가격": "화환",
            "경조사화환": "화환",
            "화환": "화환",
            # 꽃배달 계열
            "꽃배달": "꽃배달",
            "플라워": "꽃배달",
            "꽃바구니": "꽃배달",
            "꽃다발": "꽃배달",
            "생화": "꽃배달",
            # 장례 서비스
            "장례식장": "장례",
        }

        logger.debug(
            f"[CANONICAL] 패턴 구축 완료: "
            f"장소 {len(self.place_keywords)}개, 서비스 {len(self.service_keywords)}개"
        )

    def generate_canonical_key(self, title: str) -> Optional[str]:
        """
        제목에서 캐노니컬 키 생성

        Args:
            title: 원본 제목

        Returns:
            캐노니컬 키 (형식: "지역|장소|주제") 또는 None
        """
        if not title:
            return None

        # 1. 지역 추출
        location = self.location_service.extract_location(title)
        location_key = ""
        if location:
            parts = []
            if location.get("province"):
                parts.append(location["province"])
            if location.get("city"):
                parts.append(location["city"])
            location_key = "_".join(parts)

        # 2. 장소/기관 추출
        places = self._extract_places(title)
        place_key = "_".join(places) if places else ""

        # 3. 서비스/주제 추출 (정규화 적용)
        services = self._extract_services(title)
        service_key = "_".join(services) if services else ""

        # 키 생성 (최소 하나 이상의 요소 필요)
        if not any([location_key, place_key, service_key]):
            return None

        canonical_key = f"{location_key}|{place_key}|{service_key}"
        logger.debug(f"[CANONICAL] {title[:30]}... -> {canonical_key}")
        return canonical_key

    def _extract_places(self, title: str) -> List[str]:
        """장소/기관명 추출"""
        found = []
        title_lower = title.lower()

        for keyword in self.place_keywords:
            if keyword in title or keyword in title_lower:
                # 키워드 앞의 고유명사도 함께 추출 시도
                pattern = rf'(\S*{re.escape(keyword)})'
                matches = re.findall(pattern, title)
                for match in matches:
                    # 정규화: 공백 제거
                    normalized = match.replace(" ", "")
                    if normalized and normalized not in found:
                        found.append(normalized)

        # 중복 제거 후 길이 순 정렬 (더 구체적인 것 우선)
        found = list(set(found))
        found.sort(key=len, reverse=True)

        return found[:2]  # 상위 2개만

    def _extract_services(self, title: str) -> List[str]:
        """서비스/주제 키워드 추출 (정규화 적용)"""
        found_normalized = set()

        for keyword in self.service_keywords:
            if keyword in title:
                # 정규화된 키워드로 변환
                normalized = self.service_normalization.get(keyword, keyword)
                found_normalized.add(normalized)

        result = list(found_normalized)
        # 우선순위 정렬 (더 일반적인 것 우선)
        result.sort()

        return result[:2]  # 상위 2개만

    def check_canonical_match(self, title1: str, title2: str) -> Dict:
        """
        두 제목의 캐노니컬 키 일치 여부 확인

        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목

        Returns:
            {
                "match": bool,
                "key1": str or None,
                "key2": str or None,
                "partial_match": bool,  # 부분 일치 여부
                "match_components": list  # 일치하는 구성요소
            }
        """
        key1 = self.generate_canonical_key(title1)
        key2 = self.generate_canonical_key(title2)

        result = {
            "match": False,
            "key1": key1,
            "key2": key2,
            "partial_match": False,
            "match_components": []
        }

        if key1 is None or key2 is None:
            return result

        # 완전 일치
        if key1 == key2:
            result["match"] = True
            result["match_components"] = ["location", "place", "service"]
            logger.debug(f"[CANONICAL] 완전 일치: {key1}")
            return result

        # 부분 일치 검사
        parts1 = key1.split("|")
        parts2 = key2.split("|")

        if len(parts1) == 3 and len(parts2) == 3:
            match_components = []

            # 지역 일치
            if parts1[0] and parts2[0] and parts1[0] == parts2[0]:
                match_components.append("location")

            # 장소 일치
            if parts1[1] and parts2[1] and parts1[1] == parts2[1]:
                match_components.append("place")

            # 서비스 일치
            if parts1[2] and parts2[2] and parts1[2] == parts2[2]:
                match_components.append("service")

            # 지역+장소가 일치하면 부분 일치로 간주
            if "location" in match_components and "place" in match_components:
                result["partial_match"] = True
                result["match_components"] = match_components
                logger.debug(
                    f"[CANONICAL] 부분 일치 (지역+장소): {key1} vs {key2}"
                )

        return result


# 편의 함수
def generate_canonical_key(title: str) -> Optional[str]:
    """캐노니컬 키 생성 (편의 함수)"""
    return CanonicalKeyService().generate_canonical_key(title)


def check_canonical_match(title1: str, title2: str) -> Dict:
    """캐노니컬 키 일치 확인 (편의 함수)"""
    return CanonicalKeyService().check_canonical_match(title1, title2)


# 싱글톤 인스턴스 접근
def get_canonical_key_service() -> CanonicalKeyService:
    """CanonicalKeyService 싱글톤 인스턴스 반환"""
    return CanonicalKeyService()
