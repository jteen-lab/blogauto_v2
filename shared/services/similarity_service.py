"""
유사도 매칭 서비스 V3

다단계 하이브리드 유사도 매칭 서비스입니다.
핵심 원칙: "지역명이 다르면 절대 그룹화하지 않음"

단계:
- Stage 0: 지역명 호환성 검사
- Stage 1: 캐노니컬 키 완전 일치
- Stage 2: 키워드 기반 유사도
- Stage 4: 최종 점수 계산 (지역 패널티 적용)

사용처:
- 임시 제목 → 정식 제목 이동 시 그룹화
- 블로그 크롤링 제목과 정식 제목 매칭
- 그룹 내 제목 재매칭
"""

import re
import html
import unicodedata
import logging
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

# rapidfuzz 사용 (설치된 경우)
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

from .location_service import extract_location, is_same_location, remove_location, LocationService
from .canonical_key_service import CanonicalKeyService, check_canonical_match

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_SIMILARITY_THRESHOLD = 75.0  # 데이터 모듈 설정과 통일
AUTO_MATCH_THRESHOLD = 94.0

# 불용어 목록
KOREAN_STOPWORDS = [
    # 조사
    '및', '과', '에', '에서', '으로', '와', '은', '는', '이', '가', '을', '를',
    '의', '로', '라', '고', '도', '만', '에게', '께', '한테', '보다',
    # 수식어
    '대한', '관한', '위한', '통한', '따른', '인한', '등', '또는', '그리고',
    # 일반 키워드 (정보성)
    '방법', '원인', '증상', '치료', '효과', '정보', '종류', '가격', '비교', '정리',
    '추천', '순위', '후기', '리뷰', '총정리', '완벽정리', '알아보기', '소개',
    # 브랜드/도메인
    'tistory', 'naver', 'blog', 'daum', 'kakao', 'google',
]

# 도메인 골격어(카테고리 공통어) — '핵심어 발산 가드' 판정에서만 제외한다.
# 점수/보너스 계산에는 사용하지 않으므로 점수를 올리지 않고, 캡 판정만 좌우한다.
GENERIC_KEYWORDS = frozenset([
    # 여행 가이드 골격
    '여행', '여행지', '여행기', '숙소', '호텔', '호스텔', '게스트하우스', '리조트',
    '명소', '관광', '관광지', '관광명소', '가볼만한곳', '볼거리', '즐길거리', '먹거리',
    '날씨', '계절', '계절별', '대중교통', '교통', '코스', '일정', '지역', '지역별',
    '특징', '준비', '사항', '방문', '기초', '필수', '가이드', '팁',
    '음식', '맛집', '카페',
    # 블로그 일반 골격
    '베스트', '리스트', '모음', '가지', '개', '곳',
])

# 조사/접미 경량 제거용(형태소 분석 없이 토큰 끝 처리)
PARTICLE_SUFFIXES = (
    '으로', '에서', '에게', '한테', '과의', '와의', '에는', '에서의',
    '과', '와', '을', '를', '이', '가', '은', '는', '의', '에', '로', '도', '만',
    '별', '들',
)

# 핵심어 발산 시 점수 상한(회색지대 하한 미만으로 눌러 하드 분리)
CORE_DIVERGENCE_CAP = 55.0

# 제거할 패턴
BRACKET_PATTERN = re.compile(r'^[\[\(\{<【「『].*?[\]\)\}>】」』]\s*|\s*[\[\(\{<【「『].*?[\]\)\}>】」』]$')
SEPARATOR_PATTERN = re.compile(r'[\|\-:／/·•]')
MULTI_SPACE_PATTERN = re.compile(r'\s+')


class SimilarityService:
    """유사도 매칭 서비스 V2"""

    def __init__(self, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Args:
            threshold: 유사도 임계값 (0-100, 기본 80)
        """
        self.threshold = threshold

    def normalize_text(self, text: str, remove_stopwords: bool = False) -> str:
        """
        텍스트 정규화

        Args:
            text: 원본 텍스트
            remove_stopwords: 불용어 제거 여부

        Returns:
            정규화된 텍스트
        """
        if not text:
            return ""

        result = text

        # 1. HTML 엔티티 디코드
        result = html.unescape(result)

        # 2. NFKC 유니코드 정규화 (전각/반각 통일)
        result = unicodedata.normalize('NFKC', result)

        # 3. 제어문자 및 제로폭 문자 제거
        result = re.sub(r'[\u0000-\u001F\u200B-\u200D\uFEFF]', '', result)

        # 4. 앞/뒤 괄호 태그 제거 (최대 2회)
        for _ in range(2):
            result = BRACKET_PATTERN.sub('', result)

        # 5. 구분자를 공백으로 변환
        result = SEPARATOR_PATTERN.sub(' ', result)

        # 6. 소문자 변환
        result = result.lower()

        # 7. 공백 압축
        result = MULTI_SPACE_PATTERN.sub(' ', result).strip()

        # 8. 불용어 제거 (선택적)
        if remove_stopwords:
            words = result.split()
            words = [w for w in words if w not in KOREAN_STOPWORDS]
            result = ' '.join(words)

        return result

    def _token_sort_ratio_difflib(self, s1: str, s2: str) -> float:
        """
        토큰 정렬 후 유사도 계산 (difflib 버전)
        rapidfuzz.token_sort_ratio와 유사한 동작
        """
        # 토큰 정렬
        tokens1 = sorted(s1.split())
        tokens2 = sorted(s2.split())
        sorted1 = ' '.join(tokens1)
        sorted2 = ' '.join(tokens2)

        # SequenceMatcher로 유사도 계산
        matcher = SequenceMatcher(None, sorted1, sorted2)
        return matcher.ratio() * 100

    def _calculate_keyword_bonus(self, text1: str, text2: str) -> float:
        """
        공통 핵심 키워드에 대한 보너스 점수 계산

        두 텍스트에 공통으로 포함된 의미있는 키워드 비율에 따라 보너스 부여
        """
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())

        # 불용어 및 짧은 토큰 제거
        meaningful1 = {t for t in tokens1 if len(t) > 1 and t not in KOREAN_STOPWORDS}
        meaningful2 = {t for t in tokens2 if len(t) > 1 and t not in KOREAN_STOPWORDS}

        if not meaningful1 or not meaningful2:
            return 0.0

        # 공통 키워드 비율 계산
        common = meaningful1 & meaningful2
        total = meaningful1 | meaningful2

        if not total:
            return 0.0

        overlap_ratio = len(common) / len(total)

        # 최대 15점 보너스 (Jaccard 유사도 기반)
        return overlap_ratio * 15.0

    def _containment_ratio(self, text1: str, text2: str) -> float:
        """짧은 제목의 토큰(불용어 포함)이 긴 제목에 얼마나 포함되는지(0~1).

        불용어 제거로 짧은 유사 제목을 놓치던 문제 보완용. 원문 토큰을 쓰고,
        조사/어미 차이는 부분문자열 매칭으로 흡수한다(가격 ⊆ 가격과,
        비교 ⊆ 비교하는). len<=1 토큰은 제외.
        """
        t1 = [t for t in text1.split() if len(t) > 1]
        t2 = [t for t in text2.split() if len(t) > 1]
        if not t1 or not t2:
            return 0.0
        short, long_ = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
        long_set = set(long_)
        matched = sum(
            1 for s in short
            if s in long_set or any(s in lt for lt in long_)
        )
        return matched / len(short)

    def _strip_token(self, tok: str) -> str:
        """토큰에서 구두점·조사/접미를 경량 제거(형태소 분석 없이)."""
        tok = tok.strip(",.·、，。！!?？:;\"'()[]{}")
        for suf in PARTICLE_SUFFIXES:
            if len(tok) > len(suf) + 1 and tok.endswith(suf):
                return tok[:-len(suf)]
        return tok

    def _distinctive_tokens(self, text: str) -> set:
        """제목의 '차별 토큰' 집합.

        불용어·도메인 골격어(GENERIC_KEYWORDS)·짧은 토큰을 제외해
        제목을 구분짓는 핵심어(지명·제품명·주제어)만 남긴다.
        """
        norm = self.normalize_text(text)
        result = set()
        for raw in norm.split():
            t = self._strip_token(raw)
            if len(t) <= 1:
                continue
            if t in KOREAN_STOPWORDS or t in GENERIC_KEYWORDS:
                continue
            result.add(t)
        return result

    def _core_divergence(self, title1: str, title2: str) -> bool:
        """두 제목의 핵심어가 완전히 발산하는지 판정.

        양쪽 모두 차별 토큰이 있고, 서로 공유하는 차별 토큰이
        (부분문자열 허용) 하나도 없으면 → 서로 다른 핵심 주제로 본다.
        """
        d1 = self._distinctive_tokens(title1)
        d2 = self._distinctive_tokens(title2)
        if not d1 or not d2:
            return False
        for a in d1:
            for b in d2:
                if a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)):
                    return False  # 공유 차별 토큰 존재 → 발산 아님
        return True

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        순수 텍스트 유사도 계산 (지역명 처리 없음)

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 점수 (0-100)
        """
        # 정규화
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)

        if not norm1 or not norm2:
            return 0.0

        # 완전 일치
        if norm1 == norm2:
            return 100.0

        # 포함 관계 검사
        if norm1 in norm2 or norm2 in norm1:
            longer = max(len(norm1), len(norm2))
            shorter = min(len(norm1), len(norm2))
            ratio = shorter / longer if longer > 0 else 0
            return 85.0 + (ratio * 10.0)

        # rapidfuzz 또는 difflib (토큰 정렬 적용)
        if HAS_RAPIDFUZZ:
            base_score = fuzz.token_sort_ratio(norm1, norm2)
        else:
            base_score = self._token_sort_ratio_difflib(norm1, norm2)

        # 키워드 보너스 적용
        bonus = self._calculate_keyword_bonus(norm1, norm2)
        score = min(100.0, base_score + bonus)

        # 포함도(부분집합) 보정: 짧은 제목이 긴 제목에 대부분 포함되면
        # 점수를 회색지대(68~74)까지만 끌어올려 AI가 최종 판정하게 한다.
        # (자동 그룹이 아니라 회색지대 진입까지만 — 오그룹 위험 최소화)
        contain = self._containment_ratio(norm1, norm2)
        if len(norm1.split()) >= 2 and len(norm2.split()) >= 2 and contain >= 0.6:
            contain_score = 68.0 + (contain - 0.6) * 15.0  # 0.6→68 ~ 1.0→74
            score = max(score, contain_score)

        return round(score, 2)

    def calculate_similarity_v2(self, title1: str, title2: str) -> float:
        """
        V2 유사도 계산 (지역명 우선 처리)

        핵심 로직:
        1. 지역명 추출
        2. 지역명이 다르면 → 0점 반환
        3. 지역명 제거 후 텍스트 유사도 계산

        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목

        Returns:
            유사도 점수 (0-100)
        """
        if not title1 or not title2:
            return 0.0

        # 1. 지역명 추출
        loc1 = extract_location(title1)
        loc2 = extract_location(title2)

        # 2. 지역 비교 - 다르면 0점
        if not is_same_location(loc1, loc2):
            logger.debug(f"[SIMILARITY] 지역 불일치: {loc1} vs {loc2}")
            return 0.0

        # 3. 지역명 제거 후 텍스트 유사도 계산
        clean1 = remove_location(title1, loc1)
        clean2 = remove_location(title2, loc2)

        score = self.calculate_text_similarity(clean1, clean2)
        logger.debug(f"[SIMILARITY] {title1[:30]}... vs {title2[:30]}... = {score}")

        return score

    def calculate_similarity_v3(self, title1: str, title2: str) -> Dict:
        """
        V3 다단계 하이브리드 유사도 계산

        단계:
        - Stage 0: 지역명 호환성 검사 (필터링/패널티)
        - Stage 1: 캐노니컬 키 완전 일치
        - Stage 2: 키워드 기반 유사도
        - Stage 4: 최종 점수 계산 (지역 패널티 적용)

        Args:
            title1: 첫 번째 제목
            title2: 두 번째 제목

        Returns:
            {
                "score": float,           # 최종 유사도 점수
                "groupable": bool,        # 그룹핑 가능 여부
                "reason": str,            # 판정 사유
                "details": {              # 상세 정보
                    "stage": str,         # 최종 판정 단계
                    "location_check": dict,
                    "canonical_check": dict,
                    "keyword_score": float,
                    "location_penalty": float,
                    "base_score": float
                }
            }
        """
        if not title1 or not title2:
            return {
                "score": 0,
                "groupable": False,
                "reason": "빈 제목",
                "details": {
                    "stage": "입력 검증 실패",
                    "location_check": None,
                    "canonical_check": None,
                    "keyword_score": 0,
                    "location_penalty": 0,
                    "base_score": 0
                }
            }

        # Stage 0: 지역명 호환성 검사
        location_check = self._check_location_compatibility(title1, title2)

        if not location_check["compatible"]:
            return {
                "score": 0,
                "groupable": False,
                "reason": location_check["reason"],
                "details": {
                    "stage": "Stage 0: 지역 불일치로 차단",
                    "location_check": location_check,
                    "canonical_check": None,
                    "keyword_score": 0,
                    "location_penalty": 1.0,
                    "base_score": 0
                }
            }

        # 핵심어 발산 여부(캐노니컬/키워드 전 단계에서 1회 계산).
        # 발산 시 공유 차별 토큰이 없으므로 캐노니컬 고득점을 부여하지 않는다.
        diverged = self._core_divergence(title1, title2)

        # Stage 1: 캐노니컬 키 완전 일치
        canonical_check = check_canonical_match(title1, title2)

        # 캐노니컬 키 매칭 시에도 최소 텍스트 유사도 검증 (오매칭 방지)
        if canonical_check["match"] or canonical_check.get("partial_match"):
            # 지역명 제거 후 텍스트 유사도 계산
            loc1 = extract_location(title1)
            loc2 = extract_location(title2)
            clean1 = remove_location(title1, loc1)
            clean2 = remove_location(title2, loc2)
            text_similarity = self.calculate_text_similarity(clean1, clean2)

            # 텍스트 유사도가 최소 임계값(75%) 이상이어야 캐노니컬 키 매칭 인정
            min_text_threshold = 75.0

            if canonical_check["match"] and text_similarity >= min_text_threshold and not diverged:
                # 완전 일치: 텍스트 유사도와 100점 중 높은 값 사용
                final_score = max(text_similarity, 95.0)
                return {
                    "score": round(final_score, 2),
                    "groupable": True,
                    "reason": f"캐노니컬 키 완전 일치: {canonical_check['key1']}",
                    "details": {
                        "stage": "Stage 1: 캐노니컬 키 일치",
                        "location_check": location_check,
                        "canonical_check": canonical_check,
                        "keyword_score": round(text_similarity, 2),
                        "location_penalty": 0,
                        "base_score": round(final_score, 2)
                    }
                }

            # Stage 1.5: 캐노니컬 키 부분 일치 (지역+장소)
            if canonical_check.get("partial_match") and text_similarity >= min_text_threshold and not diverged:
                # 부분 일치: 텍스트 유사도와 90점 중 높은 값 사용
                final_score = max(text_similarity, 85.0)
                return {
                    "score": round(final_score, 2),
                    "groupable": True,
                    "reason": f"캐노니컬 키 부분 일치 (지역+장소): {canonical_check['key1']}",
                    "details": {
                        "stage": "Stage 1.5: 캐노니컬 키 부분 일치",
                        "location_check": location_check,
                        "canonical_check": canonical_check,
                        "keyword_score": round(text_similarity, 2),
                        "location_penalty": 0,
                        "base_score": round(final_score, 2)
                    }
                }

            # 텍스트 유사도가 너무 낮으면 캐노니컬 키 매칭 무시하고 일반 유사도로 진행
            logger.debug(
                f"[SIMILARITY] 캐노니컬 키 매칭되었으나 텍스트 유사도 부족: "
                f"{text_similarity:.1f}% < {min_text_threshold}%"
            )

        # Stage 2: 키워드 기반 유사도 (기존 로직 활용)
        loc1 = extract_location(title1)
        loc2 = extract_location(title2)
        clean1 = remove_location(title1, loc1)
        clean2 = remove_location(title2, loc2)

        keyword_score = self.calculate_text_similarity(clean1, clean2)

        # Stage 4: 최종 점수 계산 (지역 패널티 적용)
        penalty = location_check["penalty"]
        final_score = keyword_score * (1 - penalty)

        # Stage 4.5: 핵심어 발산 가드
        # 지명 사전에 없는 destination 등 핵심어가 완전히 다른데도 골격어
        # 공유로 점수가 높은 경우, 상한(CAP)으로 눌러 자동 그룹을 차단한다.
        stage = "Stage 2: 키워드 유사도"
        reason = location_check["reason"]
        if final_score > CORE_DIVERGENCE_CAP and diverged:
            logger.info(
                "[SIMILARITY] 핵심어 발산 가드 발동 | %.1f→%.1f | '%s' ↔ '%s'",
                final_score, CORE_DIVERGENCE_CAP, title1[:20], title2[:20],
            )
            final_score = CORE_DIVERGENCE_CAP
            stage = "Stage 4.5: 핵심어 발산으로 분리"
            reason = "핵심 키워드 불일치(발산 가드)"

        return {
            "score": round(final_score, 2),
            "groupable": final_score >= self.threshold,
            "reason": reason,
            "details": {
                "stage": stage,
                "location_check": location_check,
                "canonical_check": canonical_check,
                "keyword_score": round(keyword_score, 2),
                "location_penalty": penalty,
                "base_score": round(keyword_score, 2)
            }
        }

    def _check_location_compatibility(
        self,
        title1: str,
        title2: str
    ) -> Dict:
        """
        두 제목 간 지역 호환성 검사

        Returns:
            {
                "compatible": bool,      # 그룹핑 가능 여부
                "penalty": float,        # 유사도 감점 비율 (0 ~ 1)
                "reason": str,           # 판정 사유
                "locations1": dict,      # 제목1의 지역명
                "locations2": dict       # 제목2의 지역명
            }
        """
        loc1 = extract_location(title1)
        loc2 = extract_location(title2)

        has_loc1 = loc1 is not None
        has_loc2 = loc2 is not None

        # Case 4: 둘 다 지역명 없음 → 정상 진행
        if not has_loc1 and not has_loc2:
            return {
                "compatible": True,
                "penalty": 0.0,
                "reason": "지역명 미사용 제목",
                "locations1": loc1,
                "locations2": loc2
            }

        # Case 1 & 2: 둘 다 지역명 있음
        if has_loc1 and has_loc2:
            if is_same_location(loc1, loc2):
                return {
                    "compatible": True,
                    "penalty": 0.0,
                    "reason": f"지역 일치: {loc1.get('city') or loc1.get('province')}",
                    "locations1": loc1,
                    "locations2": loc2
                }
            else:
                # Case 2: 불일치 → 그룹핑 불가
                loc1_str = loc1.get('city') or loc1.get('province') or "알수없음"
                loc2_str = loc2.get('city') or loc2.get('province') or "알수없음"
                return {
                    "compatible": False,
                    "penalty": 1.0,
                    "reason": f"지역 불일치: {loc1_str} vs {loc2_str}",
                    "locations1": loc1,
                    "locations2": loc2
                }

        # Case 3: 한쪽만 지역명 있음 → 진행하되 강화된 패널티
        return {
            "compatible": True,
            "penalty": 0.30,  # 30% 감점 (15% → 30%로 강화)
            "reason": "한쪽만 지역명 존재 - 불확실성 패널티 적용",
            "locations1": loc1,
            "locations2": loc2
        }

    def find_best_match(
        self,
        target_title: str,
        candidate_titles: List[str],
        min_threshold: Optional[float] = None
    ) -> Optional[Tuple[str, float]]:
        """
        후보 제목들 중 가장 유사한 제목 찾기

        Args:
            target_title: 대상 제목
            candidate_titles: 후보 제목 리스트
            min_threshold: 최소 임계값 (None이면 self.threshold 사용)

        Returns:
            (가장 유사한 제목, 유사도) 또는 None
        """
        threshold = min_threshold if min_threshold is not None else self.threshold
        best_match: Optional[Tuple[str, float]] = None

        for candidate in candidate_titles:
            score = self.calculate_similarity_v2(target_title, candidate)
            if score >= threshold:
                if best_match is None or score > best_match[1]:
                    best_match = (candidate, score)

        return best_match

    def find_similar_group(
        self,
        title: str,
        groups: List[Dict],
        category_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        제목이 속할 수 있는 그룹 찾기

        Args:
            title: 대상 제목
            groups: 그룹 리스트 [{"id": 1, "representative_title": "...", "category_id": 1}, ...]
            category_id: 카테고리 필터 (None이면 전체)

        Returns:
            매칭된 그룹 정보 {"group": {...}, "score": float} 또는 None
        """
        best_group: Optional[Dict] = None
        best_score = 0.0

        for group in groups:
            # 카테고리 필터링
            if category_id is not None and group.get("category_id") != category_id:
                continue

            rep_title = group.get("representative_title", "")
            if not rep_title:
                continue

            score = self.calculate_similarity_v2(title, rep_title)
            if score >= self.threshold and score > best_score:
                best_score = score
                best_group = {"group": group, "score": score}

        return best_group

    def batch_group_titles(
        self,
        titles: List[Dict],
        existing_groups: Optional[List[Dict]] = None
    ) -> Dict[str, List]:
        """
        제목들을 배치로 그룹화

        Args:
            titles: 제목 리스트 [{"id": 1, "title": "...", "category_id": 1}, ...]
            existing_groups: 기존 그룹 리스트 (None이면 새로 그룹화)

        Returns:
            {
                "new_groups": [{"representative": {...}, "members": [...], "score": float}],
                "added_to_existing": [{"group_id": int, "titles": [...], "scores": [...]}],
                "ungrouped": [...]
            }
        """
        result: Dict[str, List] = {
            "new_groups": [],
            "added_to_existing": [],
            "ungrouped": []
        }

        remaining = list(titles)
        existing_groups = existing_groups or []

        # 1단계: 기존 그룹에 매칭 시도
        for group in existing_groups:
            matched_titles = []
            matched_scores = []
            still_remaining = []

            for item in remaining:
                title = item.get("title", "")
                cat_id = item.get("category_id")
                group_cat = group.get("category_id")

                # 카테고리가 다르면 패스
                if cat_id is not None and group_cat is not None and cat_id != group_cat:
                    still_remaining.append(item)
                    continue

                rep_title = group.get("representative_title", "")
                score = self.calculate_similarity_v2(title, rep_title)

                if score >= self.threshold:
                    matched_titles.append(item)
                    matched_scores.append(score)
                else:
                    still_remaining.append(item)

            if matched_titles:
                result["added_to_existing"].append({
                    "group_id": group.get("id"),
                    "titles": matched_titles,
                    "scores": matched_scores
                })

            remaining = still_remaining

        # 2단계: 남은 것들끼리 새 그룹 생성
        while remaining:
            current = remaining.pop(0)
            current_title = current.get("title", "")
            current_cat = current.get("category_id")

            members = []
            still_remaining = []

            for item in remaining:
                title = item.get("title", "")
                cat_id = item.get("category_id")

                # 카테고리가 다르면 패스
                if current_cat is not None and cat_id is not None and current_cat != cat_id:
                    still_remaining.append(item)
                    continue

                score = self.calculate_similarity_v2(current_title, title)
                if score >= self.threshold:
                    members.append({"item": item, "score": score})
                else:
                    still_remaining.append(item)

            if members:
                result["new_groups"].append({
                    "representative": current,
                    "members": [m["item"] for m in members],
                    "scores": [m["score"] for m in members]
                })
            else:
                result["ungrouped"].append(current)

            remaining = still_remaining

        return result


# 편의 함수
def calculate_similarity(
    title1: str,
    title2: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> float:
    """제목 유사도 계산 (편의 함수)"""
    return SimilarityService(threshold).calculate_similarity_v2(title1, title2)


def find_best_match(
    target: str,
    candidates: List[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Optional[Tuple[str, float]]:
    """가장 유사한 제목 찾기 (편의 함수)"""
    return SimilarityService(threshold).find_best_match(target, candidates)


def batch_group_titles(
    titles: List[Dict],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict[str, List]:
    """제목 배치 그룹화 (편의 함수)"""
    return SimilarityService(threshold).batch_group_titles(titles)
