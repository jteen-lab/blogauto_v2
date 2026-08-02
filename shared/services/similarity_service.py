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

import logging
from typing import List, Dict, Optional, Tuple

from .location_service import extract_location, is_same_location, remove_location, LocationService
from .canonical_key_service import CanonicalKeyService, check_canonical_match
from .similarity_text import (
    TextSimilarityMixin,
    KOREAN_STOPWORDS,
    GENERIC_KEYWORDS,
    PARTICLE_SUFFIXES,
    HAS_RAPIDFUZZ,
)
from .similarity_grouping_ops import GroupingOpsMixin

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_SIMILARITY_THRESHOLD = 75.0  # 데이터 모듈 설정과 통일
AUTO_MATCH_THRESHOLD = 94.0


class SimilarityService(TextSimilarityMixin, GroupingOpsMixin):
    """유사도 매칭 서비스 V3 (텍스트/그룹 믹스인 상속)."""

    def __init__(
        self,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        token_df: Optional[Dict[str, int]] = None,
        n_docs: int = 0,
        rare_df_ratio: Optional[float] = None,
    ):
        """
        Args:
            threshold: 유사도 임계값 (0-100, 기본 75)
            token_df: 코퍼스 토큰 문서빈도(주어 발산 게이트용). 미주입 시
                기존 핵심어 발산 가드(_core_divergence)로 폴백.
            n_docs: 코퍼스 문서(제목) 수.
            rare_df_ratio: 희소 주어 판정 비율(기본 RARE_DF_RATIO).
        """
        self.threshold = threshold
        self.token_df = token_df or {}
        self.n_docs = n_docs or 0
        if rare_df_ratio is not None:
            self.rare_df_ratio = rare_df_ratio


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

        # 식별자 발산 여부(캐노니컬/키워드 전 단계에서 1회 계산).
        # 지명 불일치는 Stage 0에서 이미 차단됨. 여기서는 '주어(핵심어)' 발산을 본다.
        # DF 주입 시 주어 발산 게이트 사용, 미주입 시 기존 핵심어 발산 가드로 폴백.
        subj_div = self._subject_divergence(title1, title2)
        diverged = subj_div if subj_div is not None else self._core_divergence(title1, title2)

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

        # Stage 4.5: 식별자 발산 게이트
        # 핵심 식별자가 다른데 골격어 공유로 점수가 높은 경우, 회색지대 상한
        # (threshold-1)으로 눌러 자동 그룹을 막고, 회색지대 AI가 최종 판정하도록
        # 한다. (DF만으로는 '희소 수식어'와 '주어'를 못 가르는 잔여 오탐을 AI가 구제)
        stage = "Stage 2: 키워드 유사도"
        reason = location_check["reason"]
        gray_cap = self.threshold - 1.0
        if final_score > gray_cap and diverged:
            logger.info(
                "[SIMILARITY] 식별자 발산 게이트 발동 | %.1f→%.1f | '%s' ↔ '%s'",
                final_score, gray_cap, title1[:20], title2[:20],
            )
            final_score = gray_cap
            stage = "Stage 4.5: 식별자 발산(회색지대 하향)"
            reason = "핵심 식별자 불일치(발산 게이트)"

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
