"""그룹 매칭 편의 메서드 믹스인.

SimilarityService에서 분리(파일 크기 규칙). calculate_similarity_v2를
self로 호출하므로 SimilarityService와 함께 상속되어야 한다.
"""
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class GroupingOpsMixin:
    """후보/그룹 매칭 편의 메서드 모음."""

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
