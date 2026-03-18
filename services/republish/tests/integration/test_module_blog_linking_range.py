"""
프롬프트 모듈 양방향 연동 - 범위 기반 충돌 감지 테스트

전체 토픽(subtopic_id=None) ↔ 개별 서브토픽 간 충돌 감지 및 분해(explode) 로직
"""
import pytest
from unittest.mock import MagicMock

from app.routers.modules import _topics_conflict
from app.services.generation.flow_generate_executor import FlowGenerateExecutor
from tests.fixtures.generation_pipeline_fixtures import create_mock_module


# ──────────────────────────────────────────────────────
# _topics_conflict() 범위 기반 충돌 판정 테스트
# ──────────────────────────────────────────────────────

class TestTopicsConflict:
    """_topics_conflict() 범위 기반 충돌 판정"""

    def test_different_topics_no_conflict(self):
        """서로 다른 토픽 → 충돌 아님"""
        assert _topics_conflict(1, None, 2, None) is False
        assert _topics_conflict(1, 10, 2, 10) is False

    def test_same_topic_both_null(self):
        """같은 토픽, 둘 다 전체 → 충돌"""
        assert _topics_conflict(1, None, 1, None) is True

    def test_same_topic_same_subtopic(self):
        """같은 토픽, 같은 서브토픽 → 충돌"""
        assert _topics_conflict(1, 10, 1, 10) is True

    def test_same_topic_different_subtopics(self):
        """같은 토픽, 다른 서브토픽 → 충돌 아님"""
        assert _topics_conflict(1, 10, 1, 20) is False

    def test_whole_topic_vs_subtopic(self):
        """전체 토픽 vs 개별 서브토픽 → 충돌"""
        assert _topics_conflict(1, None, 1, 10) is True
        assert _topics_conflict(1, 10, 1, None) is True

    def test_whole_topic_covers_all_subtopics(self):
        """전체 토픽은 모든 서브토픽과 충돌"""
        for sub_id in [1, 2, 3, 100, 999]:
            assert _topics_conflict(5, None, 5, sub_id) is True
            assert _topics_conflict(5, sub_id, 5, None) is True


# ──────────────────────────────────────────────────────
# 전체 토픽 분해(explode) 시나리오 테스트
# ──────────────────────────────────────────────────────

class TestForceLinkExplode:
    """force-link 시 전체 토픽 분해 로직 테스트"""

    def test_whole_topic_exploded_when_subtopic_taken(self):
        """
        소스: AI 전체(subtopic=None)
        타겟: AI > ML(subtopic=101)
        → 소스에서 전체 토픽 제거, 나머지 서브토픽(102,103) 재추가
        """
        source_bcm = [
            {"blog_id": 1, "topic_id": 10, "subtopic_id": None},
        ]
        target_cats = [(10, 101)]

        removed = []
        new_bcm = []
        for m in source_bcm:
            is_conflict = any(
                _topics_conflict(m.get("topic_id"), m.get("subtopic_id"), t, s)
                for t, s in target_cats
            )
            if is_conflict:
                removed.append(m)
            else:
                new_bcm.append(m)

        assert len(removed) == 1
        assert removed[0]["subtopic_id"] is None

        # 분해: 나머지 서브토픽 추가
        all_subtopics = [101, 102, 103]
        taken = {s for _, s in target_cats if s is not None}
        exploded = [
            {"blog_id": 1, "topic_id": 10, "subtopic_id": sid}
            for sid in all_subtopics if sid not in taken
        ]
        new_bcm.extend(exploded)

        assert len(new_bcm) == 2
        sub_ids = {m["subtopic_id"] for m in new_bcm}
        assert sub_ids == {102, 103}

    def test_subtopics_removed_when_whole_topic_taken(self):
        """
        소스: AI > ML(101), AI > DL(102)
        타겟: AI 전체(subtopic=None)
        → 소스에서 해당 서브토픽 모두 제거
        """
        source_bcm = [
            {"blog_id": 1, "topic_id": 10, "subtopic_id": 101},
            {"blog_id": 1, "topic_id": 10, "subtopic_id": 102},
            {"blog_id": 1, "topic_id": 20, "subtopic_id": 201},
        ]
        target_cats = [(10, None)]

        new_bcm = []
        removed = []
        for m in source_bcm:
            is_conflict = any(
                _topics_conflict(m.get("topic_id"), m.get("subtopic_id"), t, s)
                for t, s in target_cats
            )
            if is_conflict:
                removed.append(m)
            else:
                new_bcm.append(m)

        assert len(removed) == 2
        assert len(new_bcm) == 1
        assert new_bcm[0]["topic_id"] == 20

    def test_mixed_scenario_partial_overlap(self):
        """
        소스: AI 전체 + 의료 > 병원
        타겟: AI > DL(102) + 의료 > 약국(202)
        → AI 전체 분해 + 의료 > 병원은 유지 (다른 서브토픽이므로)
        """
        source_bcm = [
            {"blog_id": 1, "topic_id": 10, "subtopic_id": None},
            {"blog_id": 1, "topic_id": 20, "subtopic_id": 201},  # 병원
        ]
        target_cats = [(10, 102), (20, 202)]  # DL, 약국

        removed = []
        new_bcm = []
        for m in source_bcm:
            is_conflict = any(
                _topics_conflict(m.get("topic_id"), m.get("subtopic_id"), t, s)
                for t, s in target_cats
            )
            if is_conflict:
                removed.append(m)
            else:
                new_bcm.append(m)

        # AI 전체만 충돌로 제거됨 (의료>병원은 의료>약국과 다른 서브토픽)
        assert len(removed) == 1
        assert removed[0] == {"blog_id": 1, "topic_id": 10, "subtopic_id": None}
        assert len(new_bcm) == 1
        assert new_bcm[0]["subtopic_id"] == 201


# ──────────────────────────────────────────────────────
# _filter_categories_for_blog 테스트
# ──────────────────────────────────────────────────────

class TestFilterCategoriesForBlog:
    """FlowGenerateExecutor._filter_categories_for_blog() 테스트"""

    def setup_method(self):
        mock_db = MagicMock()
        self.executor = FlowGenerateExecutor(mock_db, user_id=1)

    def test_with_bcm_filters_by_blog(self):
        """blog_category_map에서 해당 블로그 카테고리만 필터"""
        settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
                {"blog_id": 101, "topic_id": 2, "subtopic_id": 3},
                {"blog_id": 102, "topic_id": 2, "subtopic_id": 3},
            ],
            "categories": [
                {"topic_id": 1, "subtopic_id": None},
                {"topic_id": 2, "subtopic_id": 3},
            ],
        }

        result = self.executor._filter_categories_for_blog(settings, 101)

        assert len(result["categories"]) == 2
        assert result["categories"][0]["topic_id"] == 1
        assert result["categories"][1]["topic_id"] == 2

    def test_with_bcm_different_blog(self):
        """다른 블로그 ID → 해당 블로그 카테고리만"""
        settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
                {"blog_id": 102, "topic_id": 2, "subtopic_id": 3},
            ],
            "categories": [],
        }

        result = self.executor._filter_categories_for_blog(settings, 102)

        assert len(result["categories"]) == 1
        assert result["categories"][0]["topic_id"] == 2

    def test_without_bcm_legacy(self):
        """blog_category_map 없는 레거시 → 원본 반환"""
        settings = {
            "categories": [
                {"topic_id": 1, "subtopic_id": None},
                {"topic_id": 2, "subtopic_id": 3},
            ],
        }

        result = self.executor._filter_categories_for_blog(settings, 101)

        assert result is settings

    def test_bcm_no_match_for_blog(self):
        """blog_category_map에 해당 블로그 없음 → 원본 반환"""
        settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
            ],
            "categories": [{"topic_id": 1, "subtopic_id": None}],
        }

        result = self.executor._filter_categories_for_blog(settings, 999)

        assert result is settings

    def test_does_not_mutate_original(self):
        """원본 settings 변경하지 않음"""
        settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
            ],
            "categories": [
                {"topic_id": 1, "subtopic_id": None},
                {"topic_id": 2, "subtopic_id": 3},
            ],
        }

        result = self.executor._filter_categories_for_blog(settings, 101)

        assert result is not settings
        assert len(settings["categories"]) == 2
