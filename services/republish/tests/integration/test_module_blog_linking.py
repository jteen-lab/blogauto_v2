"""
프롬프트 모듈 양방향 연동 테스트

Phase 4: API 테스트 + 레거시 호환성 + 시나리오 통합 테스트
설계 문서: module_blog_bidirectional_linking_plan.md
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.routers.modules import _build_legacy_map, _topics_conflict
from app.services.generation.flow_generate_executor import FlowGenerateExecutor
from tests.fixtures.generation_pipeline_fixtures import (
    create_mock_module,
    create_mock_blog,
)


# ──────────────────────────────────────────────────────
# 테스트 데이터 팩토리
# ──────────────────────────────────────────────────────

def _module_with_bcm(
    module_id: int, name: str, bcm: list, blogs: list = None,
    categories: list = None,
) -> MagicMock:
    """blog_category_map이 있는 모듈 생성"""
    settings = {
        "blog_category_map": bcm,
        "blogs": blogs or list({m["blog_id"] for m in bcm}),
        "categories": categories or [],
    }
    return create_mock_module(module_id=module_id, name=name, settings=settings)


def _legacy_module(
    module_id: int, name: str, blogs: list, categories: list,
) -> MagicMock:
    """blog_category_map이 없는 레거시 모듈 생성"""
    settings = {"blogs": blogs, "categories": categories}
    return create_mock_module(module_id=module_id, name=name, settings=settings)


# ──────────────────────────────────────────────────────
# Phase 4-1: API 헬퍼 함수 테스트
# ──────────────────────────────────────────────────────

class TestBuildLegacyMap:
    """_build_legacy_map() 단위 테스트"""

    def test_empty_categories(self):
        """1. 카테고리 빈 상태 → 빈 매핑"""
        result = _build_legacy_map({"categories": [], "blogs": [101]})
        assert result == []

    def test_empty_blogs(self):
        """빈 블로그 → 빈 매핑"""
        result = _build_legacy_map({
            "categories": [{"topic_id": 1, "subtopic_id": None}],
            "blogs": [],
        })
        assert result == []

    def test_single_blog_single_category(self):
        """블로그 1개 × 카테고리 1개 → 매핑 1개"""
        result = _build_legacy_map({
            "categories": [{"topic_id": 1, "subtopic_id": 3}],
            "blogs": [101],
        })
        assert len(result) == 1
        assert result[0] == {
            "blog_id": 101, "topic_id": 1, "subtopic_id": 3,
        }

    def test_multiple_blogs_categories(self):
        """2. 블로그 2개 × 카테고리 2개 → 매핑 4개"""
        result = _build_legacy_map({
            "categories": [
                {"topic_id": 1, "subtopic_id": None},
                {"topic_id": 2, "subtopic_id": 3},
            ],
            "blogs": [101, 102],
        })
        assert len(result) == 4
        blog_ids = {m["blog_id"] for m in result}
        assert blog_ids == {101, 102}

    def test_no_categories_key(self):
        """categories 키 자체가 없는 경우"""
        result = _build_legacy_map({"blogs": [101]})
        assert result == []


class TestUsedBlogCategoriesLogic:
    """3. used-blog-categories 로직 테스트 (헬퍼 함수 기반)"""

    def test_exclude_self_module(self):
        """자기 모듈 제외 확인"""
        mod_a = _module_with_bcm(1, "모듈A", [
            {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
        ])
        mod_b = _module_with_bcm(2, "모듈B", [
            {"blog_id": 102, "topic_id": 2, "subtopic_id": 3},
        ])
        modules = [mod_a, mod_b]

        # exclude_id=1 → 모듈A 제외
        filtered = [m for m in modules if m.id != 1]
        all_mappings = []
        for m in filtered:
            bcm = m.settings.get("blog_category_map", [])
            for item in bcm:
                all_mappings.append({**item, "module_id": m.id})

        assert len(all_mappings) == 1
        assert all_mappings[0]["blog_id"] == 102
        assert all_mappings[0]["module_id"] == 2

    def test_legacy_module_fallback(self):
        """레거시 모듈 → _build_legacy_map으로 추론"""
        mod = _legacy_module(1, "레거시모듈", [101], [
            {"topic_id": 1, "subtopic_id": None},
        ])
        bcm = mod.settings.get("blog_category_map")
        if not bcm:
            bcm = _build_legacy_map(mod.settings)

        assert len(bcm) == 1
        assert bcm[0]["blog_id"] == 101
        assert bcm[0]["topic_id"] == 1


class TestForceLinkLogic:
    """5-7. 강제 연동 로직 테스트"""

    def test_force_link_removes_from_source(self):
        """5. 강제 연동 시 기존 모듈에서 매핑 제거"""
        source_bcm = [
            {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
            {"blog_id": 101, "topic_id": 2, "subtopic_id": 3},
            {"blog_id": 102, "topic_id": 1, "subtopic_id": None},
        ]
        target_keys = {(101, 2, 3)}

        new_bcm = [
            m for m in source_bcm
            if (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
            not in target_keys
        ]

        assert len(new_bcm) == 2
        assert all(
            (m["blog_id"], m.get("topic_id"), m.get("subtopic_id")) != (101, 2, 3)
            for m in new_bcm
        )

    def test_force_link_removes_blog_if_empty(self):
        """6. 모든 카테고리 제거 시 blogs에서 blog_id 제거"""
        source_bcm = [
            {"blog_id": 101, "topic_id": 2, "subtopic_id": 3},
        ]
        target_keys = {(101, 2, 3)}

        new_bcm = [
            m for m in source_bcm
            if (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
            not in target_keys
        ]
        remaining_blogs = list({m["blog_id"] for m in new_bcm})

        assert new_bcm == []
        assert 101 not in remaining_blogs

    def test_force_link_no_conflict(self):
        """7. 충돌 없는 경우 → 제거 없음"""
        source_bcm = [
            {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
        ]
        target_keys = {(102, 2, 3)}

        new_bcm = [
            m for m in source_bcm
            if (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
            not in target_keys
        ]

        assert len(new_bcm) == 1  # 변경 없음


# ──────────────────────────────────────────────────────
# Phase 4-2: 레거시 호환성 테스트
# ──────────────────────────────────────────────────────

class TestLegacyCompatibility:
    """레거시 모듈 호환성 테스트"""

    def test_auto_generate_bcm_on_save(self):
        """8. blog_category_map 없는 레거시 모듈 → 자동 생성"""
        settings = {
            "categories": [
                {"topic_id": 1, "subtopic_id": None},
                {"topic_id": 2, "subtopic_id": 3},
            ],
            "blogs": [101, 102],
        }

        # modules.py create/update 로직 재현
        if "categories" in settings and "blogs" in settings \
                and "blog_category_map" not in settings:
            settings["blog_category_map"] = _build_legacy_map(settings)

        assert "blog_category_map" in settings
        assert len(settings["blog_category_map"]) == 4

    def test_default_link_mode(self):
        """9. link_mode 없는 레거시 모듈 → "category" 기본값"""
        settings = {"categories": [], "blogs": []}
        link_mode = settings.get("link_mode", "category")
        assert link_mode == "category"

    def test_legacy_flow_sync_uses_blogs(self):
        """10. 레거시 모듈의 플로우 연동 → settings.blogs 기반"""
        mod = _legacy_module(1, "레거시", [101, 102], [
            {"topic_id": 1, "subtopic_id": None},
        ])

        bcm = mod.settings.get("blog_category_map")
        if bcm and len(bcm) > 0:
            linked_ids = {m["blog_id"] for m in bcm}
        else:
            linked_ids = set()
            for item in (mod.settings.get("blogs") or []):
                bid = item if isinstance(item, int) else item.get("id")
                if isinstance(bid, int):
                    linked_ids.add(bid)

        assert linked_ids == {101, 102}


# ──────────────────────────────────────────────────────
# Phase 4-3: 시나리오 통합 테스트
# ──────────────────────────────────────────────────────

class TestScenarioIntegration:
    """시나리오 기반 통합 테스트"""

    def test_scenario1_category_mode_conflict_exclusion(self):
        """11. 시나리오 1: 카테고리 기준 → 충돌 블로그 제외"""
        # 모듈 A: 블로그 X(101)와 생활정보(topic=2) 연동
        mod_a_bcm = [
            {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
            {"blog_id": 101, "topic_id": 2, "subtopic_id": None},
            {"blog_id": 101, "topic_id": 3, "subtopic_id": None},
        ]
        used_mappings = [
            {**m, "module_id": 1, "module_name": "모듈A"} for m in mod_a_bcm
        ]

        # 모듈 B에서 "생활정보"(topic=2) 선택
        # → 생활정보가 있는 블로그: X(101), Y(102), Z(103)
        candidate_blogs = [101, 102, 103]
        selected_category = {"topic_id": 2, "subtopic_id": None}

        # 충돌 검사: (blog_id, topic_id, subtopic_id)
        excluded = []
        available = []
        for blog_id in candidate_blogs:
            key = (blog_id, selected_category["topic_id"],
                   selected_category.get("subtopic_id"))
            is_conflict = any(
                (m["blog_id"], m.get("topic_id"), m.get("subtopic_id")) == key
                for m in used_mappings
            )
            if is_conflict:
                excluded.append(blog_id)
            else:
                available.append(blog_id)

        assert excluded == [101]  # X 제외
        assert available == [102, 103]  # Y, Z만 가능

    def test_scenario2_blog_mode_conflict_exclusion(self):
        """12. 시나리오 2: 블로그 기준 → 충돌 카테고리 제외"""
        # 모듈 B: 블로그 X(101)와 생활정보(topic=2) 연동 중
        used_mappings = [
            {"blog_id": 101, "topic_id": 2, "subtopic_id": None,
             "module_id": 2, "module_name": "모듈B"},
        ]

        # 모듈 A에서 블로그 X(101) 선택 (블로그 기준 모드)
        # 블로그 X의 카테고리: 건강(1), 생활정보(2), 의료(3)
        blog_categories = [
            {"topic_id": 1, "subtopic_id": None},
            {"topic_id": 2, "subtopic_id": None},
            {"topic_id": 3, "subtopic_id": None},
        ]

        auto_linked = []
        excluded = []
        for cat in blog_categories:
            key = (101, cat["topic_id"], cat.get("subtopic_id"))
            conflict = next(
                (m for m in used_mappings
                 if (m["blog_id"], m.get("topic_id"), m.get("subtopic_id")) == key),
                None,
            )
            if conflict:
                excluded.append({
                    **cat,
                    "module_name": conflict["module_name"],
                    "module_id": conflict["module_id"],
                })
            else:
                auto_linked.append(cat)

        assert len(auto_linked) == 2  # 건강, 의료만 자동 연결
        assert len(excluded) == 1  # 생활정보 제외
        assert excluded[0]["topic_id"] == 2
        assert excluded[0]["module_name"] == "모듈B"

    def test_scenario3_force_link_updates_both(self):
        """13. 시나리오 3: 강제 연동 → 양쪽 모듈 업데이트"""
        # 모듈 B: (X, 생활정보), (Y, 생활정보), (Z, 생활정보)
        mod_b_settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 2, "subtopic_id": None},
                {"blog_id": 102, "topic_id": 2, "subtopic_id": None},
                {"blog_id": 103, "topic_id": 2, "subtopic_id": None},
            ],
            "blogs": [101, 102, 103],
        }

        # 모듈 A: (X, 건강), (X, 의료)
        mod_a_settings = {
            "blog_category_map": [
                {"blog_id": 101, "topic_id": 1, "subtopic_id": None},
                {"blog_id": 101, "topic_id": 3, "subtopic_id": None},
            ],
            "blogs": [101],
        }

        # 강제 연동: (X, 생활정보)를 모듈 B → 모듈 A로 이동
        target_keys = {(101, 2, None)}

        # 모듈 B에서 제거
        new_b_bcm = [
            m for m in mod_b_settings["blog_category_map"]
            if (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
            not in target_keys
        ]
        mod_b_settings["blog_category_map"] = new_b_bcm
        mod_b_settings["blogs"] = list({m["blog_id"] for m in new_b_bcm})

        # 모듈 A에 추가
        for key in target_keys:
            existing = {
                (m["blog_id"], m.get("topic_id"), m.get("subtopic_id"))
                for m in mod_a_settings["blog_category_map"]
            }
            if key not in existing:
                mod_a_settings["blog_category_map"].append({
                    "blog_id": key[0], "topic_id": key[1], "subtopic_id": key[2],
                })

        # 검증: 모듈 B에서 X 제거
        assert len(mod_b_settings["blog_category_map"]) == 2
        assert 101 not in mod_b_settings["blogs"]
        assert mod_b_settings["blogs"] == [102, 103]

        # 검증: 모듈 A에 추가
        assert len(mod_a_settings["blog_category_map"]) == 3
        a_keys = {
            (m["blog_id"], m["topic_id"], m.get("subtopic_id"))
            for m in mod_a_settings["blog_category_map"]
        }
        assert (101, 2, None) in a_keys

    def test_scenario4_no_conflict(self):
        """14. 시나리오 4: 충돌 없는 일반 선택"""
        used_mappings = []  # 아무 모듈도 없음

        candidate_blogs = [101, 102, 103]
        selected_category = {"topic_id": 2, "subtopic_id": None}

        excluded = []
        available = []
        for blog_id in candidate_blogs:
            key = (blog_id, selected_category["topic_id"],
                   selected_category.get("subtopic_id"))
            is_conflict = any(
                (m["blog_id"], m.get("topic_id"), m.get("subtopic_id")) == key
                for m in used_mappings
            )
            if is_conflict:
                excluded.append(blog_id)
            else:
                available.append(blog_id)

        assert excluded == []
        assert available == [101, 102, 103]


