#!/usr/bin/env python3
"""
유사도 임계값 튜닝 스크립트

다양한 임계값으로 테스트하여 최적값을 찾습니다.
핵심 원칙: "지역명이 다르면 절대 그룹화하지 않음"

Usage:
    cd ~/blogauto_v2/services/republish
    python scripts/similarity_tuning.py
"""

import sys
import os
from typing import List, Dict, Tuple

# shared 모듈 경로 추가
shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from services.similarity_service import SimilarityService
from services.location_service import extract_location


# 테스트 데이터셋
# (제목1, 제목2, 그룹화되어야 함?)
TEST_CASES: List[Tuple[str, str, bool]] = [
    # ===== 같은 지역 - 그룹화 O =====
    (
        "포항 이삿짐센터 포장이사 업체추천",
        "경북 포항시 북구 이삿짐센터 이사비용",
        True
    ),
    (
        "경북 칠곡 포항 세명기독병원 장례식장 근조화환",
        "경상북도 포항시 포항 세명기독병원 장례식장 근조화환 조문",
        True
    ),
    (
        "서울 강남역 맛집 추천",
        "서울특별시 강남구 맛집 베스트",
        True
    ),
    (
        "부산 해운대 카페 추천",
        "부산광역시 해운대구 카페 투어",
        True
    ),

    # ===== 다른 지역 - 그룹화 X =====
    (
        "포항 이삿짐센터 포장이사 업체추천",
        "일산 이삿짐센터 포장이사 업체추천",
        False
    ),
    (
        "포항 이삿짐센터 포장이사 업체추천",
        "대구 이삿짐센터 포장이사 업체추천",
        False
    ),
    (
        "서울 맛집 추천",
        "부산 맛집 추천",
        False
    ),
    (
        "경기 일산 이삿짐센터",
        "경북 포항 이삿짐센터",
        False
    ),

    # ===== 지역 없음 - 유사하면 그룹화 O =====
    (
        "이삭토스트 맛집탐방 영업시간 인기메뉴 총정리",
        "이삭토스트 맛집탐방 인기메뉴와 영업시간 총정리",
        True
    ),
    (
        "이삭토스트 맛집탐방 영업시간",
        "이삭토스트 맛집 정복 운영시간",
        True
    ),
    (
        "삼성 갤럭시 스마트폰 리뷰 총정리",
        "삼성 갤럭시 스마트폰 후기 정리",
        True
    ),

    # ===== 지역 없음 - 다른 주제 =====
    (
        "이삭토스트 맛집탐방",
        "삼성 갤럭시 스마트폰 리뷰",
        False
    ),
    (
        "아이폰 케이스 추천",
        "맥북 프로 사용기",
        False
    ),

    # ===== 한쪽만 지역 있음 - 유사하면 그룹화 O =====
    (
        "이삭토스트 맛집탐방 총정리",
        "서울 이삭토스트 맛집탐방 총정리",
        True
    ),

    # ===== 경계 케이스 =====
    (
        "포항 맛집",
        "포항 맛집 추천",
        True
    ),
    (
        "맛집 추천",
        "카페 추천",
        False
    ),
]


def evaluate_threshold(threshold: float) -> Dict:
    """
    특정 임계값으로 테스트 케이스 평가

    Args:
        threshold: 평가할 임계값 (0-100)

    Returns:
        평가 결과 딕셔너리
    """
    service = SimilarityService(threshold=threshold)

    true_positive = 0   # 그룹화해야 하는데 그룹화함 (정답)
    true_negative = 0   # 그룹화하면 안되는데 안함 (정답)
    false_positive = 0  # 그룹화하면 안되는데 함 (오답)
    false_negative = 0  # 그룹화해야 하는데 안함 (오답)

    details = []

    for title1, title2, should_group in TEST_CASES:
        score = service.calculate_similarity_v2(title1, title2)
        is_grouped = score >= threshold

        if should_group and is_grouped:
            true_positive += 1
            result = "TP"
        elif not should_group and not is_grouped:
            true_negative += 1
            result = "TN"
        elif not should_group and is_grouped:
            false_positive += 1
            result = "FP"
        else:
            false_negative += 1
            result = "FN"

        details.append({
            "title1": title1[:35] + "..." if len(title1) > 35 else title1,
            "title2": title2[:35] + "..." if len(title2) > 35 else title2,
            "should_group": should_group,
            "score": round(score, 2),
            "is_grouped": is_grouped,
            "result": result
        })

    total = len(TEST_CASES)
    accuracy = (true_positive + true_negative) / total if total > 0 else 0
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "threshold": threshold,
        "accuracy": round(accuracy * 100, 2),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "f1_score": round(f1 * 100, 2),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "details": details
    }


def find_optimal_threshold() -> Dict:
    """최적 임계값 찾기"""
    thresholds = [60, 65, 70, 75, 80, 85, 90]
    results = []

    print("=" * 70)
    print("🔍 유사도 임계값 튜닝")
    print("=" * 70)
    print(f"테스트 케이스 수: {len(TEST_CASES)}")
    print("핵심 원칙: 지역명이 다르면 절대 그룹화하지 않음")
    print("=" * 70)

    for threshold in thresholds:
        result = evaluate_threshold(threshold)
        results.append(result)

        print(f"\n📊 임계값: {threshold}")
        print(f"   정확도(Accuracy): {result['accuracy']:5.1f}%")
        print(f"   정밀도(Precision): {result['precision']:5.1f}%")
        print(f"   재현율(Recall): {result['recall']:5.1f}%")
        print(f"   F1 점수: {result['f1_score']:5.1f}%")
        print(f"   TP={result['true_positive']}, TN={result['true_negative']}, "
              f"FP={result['false_positive']}, FN={result['false_negative']}")

    # 최적 임계값 선택 (F1 점수 기준)
    best = max(results, key=lambda x: x["f1_score"])

    print("\n" + "=" * 70)
    print(f"✅ 최적 임계값: {best['threshold']} (F1 점수: {best['f1_score']}%)")
    print("=" * 70)

    return best


def show_detailed_results(threshold: float) -> None:
    """상세 결과 출력"""
    result = evaluate_threshold(threshold)

    print(f"\n📋 임계값 {threshold} 상세 결과:")
    print("-" * 90)

    for detail in result["details"]:
        status = "✅" if detail["result"] in ["TP", "TN"] else "❌"
        expected = "그룹" if detail["should_group"] else "개별"
        actual = "그룹" if detail["is_grouped"] else "개별"

        print(f"{status} {detail['result']} | 점수: {detail['score']:5.1f} | "
              f"예상: {expected} | 결과: {actual}")
        print(f"   제목1: {detail['title1']}")
        print(f"   제목2: {detail['title2']}")
        print()


def print_summary_table(results: List[Dict]) -> None:
    """요약 테이블 출력"""
    print("\n" + "=" * 70)
    print("📊 임계값별 결과 요약")
    print("=" * 70)
    print(f"{'임계값':^8} | {'정확도':^8} | {'정밀도':^8} | {'재현율':^8} | {'F1점수':^8}")
    print("-" * 70)

    for r in results:
        marker = " ← 최적" if r["f1_score"] == max(x["f1_score"] for x in results) else ""
        print(f"{r['threshold']:^8} | {r['accuracy']:^7.1f}% | {r['precision']:^7.1f}% | "
              f"{r['recall']:^7.1f}% | {r['f1_score']:^7.1f}%{marker}")

    print("=" * 70)


def run_location_check() -> None:
    """지역명 추출 확인"""
    print("\n🗺️ 지역명 추출 테스트")
    print("-" * 50)

    test_titles = [
        "포항 이삿짐센터 추천",
        "경북 포항시 북구 이삿짐센터",
        "일산 이삿짐센터 포장이사",
        "서울 강남역 맛집",
        "이삭토스트 맛집탐방",
    ]

    for title in test_titles:
        loc = extract_location(title)
        if loc:
            parts = []
            if loc.get("province"):
                parts.append(f"도/시:{loc['province']}")
            if loc.get("city"):
                parts.append(f"시/군:{loc['city']}")
            if loc.get("district"):
                parts.append(f"구:{loc['district']}")
            loc_str = ", ".join(parts)
        else:
            loc_str = "지역 없음"

        print(f"  {title[:30]:<30} → {loc_str}")


def main():
    """메인 실행"""
    print("\n" + "🚀" * 35)
    print("유사도 임계값 튜닝 스크립트")
    print("🚀" * 35)

    # 지역명 추출 확인
    run_location_check()

    # 최적 임계값 찾기
    best = find_optimal_threshold()

    # 요약 테이블 출력
    thresholds = [60, 65, 70, 75, 80, 85, 90]
    results = [evaluate_threshold(t) for t in thresholds]
    print_summary_table(results)

    # 최적 임계값 상세 결과
    show_detailed_results(best["threshold"])

    # 권장 설정
    print("\n" + "=" * 70)
    print("📌 권장 설정")
    print("=" * 70)
    print(f"  DEFAULT_SIMILARITY_THRESHOLD = {best['threshold']}")
    print(f"  # 정확도: {best['accuracy']}%, F1 점수: {best['f1_score']}%")
    print("=" * 70)

    return best


if __name__ == "__main__":
    main()
