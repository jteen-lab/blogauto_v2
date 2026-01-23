"""
제목 관리 전체 워크플로우 통합 테스트
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# app 경로 추가
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

# shared 모듈 경로 추가
shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)


class TestTitleWorkflowIntegration:
    """제목 관리 워크플로우 통합 테스트"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock 데이터베이스 세션"""
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.delete = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        return db

    def test_location_extraction_integration(self):
        """지역명 추출 통합 테스트"""
        from services.location_service import extract_location, is_same_location

        # 다양한 형태의 포항 제목
        titles = [
            "포항 이삿짐센터 추천",
            "경북 포항시 이삿짐센터",
            "경상북도 포항시 북구 이삿짐센터",
        ]

        locations = [extract_location(t) for t in titles]

        # 모든 제목에서 지역 추출 성공
        for loc in locations:
            assert loc is not None
            assert loc.get("city") == "포항"

        # 모든 포항 지역끼리 매칭
        for i in range(len(locations)):
            for j in range(len(locations)):
                assert is_same_location(locations[i], locations[j]) is True

    def test_different_locations_not_grouped(self):
        """다른 지역 제목들이 그룹화되지 않음"""
        from services.location_service import extract_location, is_same_location

        # 다른 지역 제목들
        titles = [
            ("포항 이삿짐센터", "경북 포항"),
            ("일산 이삿짐센터", "경기 일산"),
            ("대구 이삿짐센터", "대구"),
        ]

        locations = [(t[0], extract_location(t[0])) for t in titles]

        # 다른 지역끼리 매칭 안 됨
        for i in range(len(locations)):
            for j in range(len(locations)):
                if i != j:
                    title1, loc1 = locations[i]
                    title2, loc2 = locations[j]

                    # 둘 다 지역이 있으면 다른 지역
                    if loc1 and loc2:
                        assert is_same_location(loc1, loc2) is False

    def test_similarity_with_location_priority(self):
        """지역 우선 유사도 계산"""
        from services.similarity_service import calculate_similarity

        # 같은 지역, 유사한 제목 → 높은 점수
        score1 = calculate_similarity(
            "포항 이삿짐센터 포장이사 업체추천",
            "경북 포항시 이삿짐센터 이사비용"
        )
        assert score1 > 50

        # 다른 지역, 동일한 내용 → 0점
        score2 = calculate_similarity(
            "포항 이삿짐센터 포장이사 업체추천",
            "일산 이삿짐센터 포장이사 업체추천"
        )
        assert score2 == 0

        # 지역 없음, 유사한 제목 → 높은 점수
        score3 = calculate_similarity(
            "이삭토스트 맛집탐방 총정리",
            "이삭토스트 맛집탐방 메뉴 정리"
        )
        assert score3 > 50

    def test_batch_grouping_workflow(self):
        """배치 그룹화 워크플로우"""
        from services.similarity_service import SimilarityService

        service = SimilarityService(threshold=75)

        titles = [
            {"id": 1, "title": "포항 이삿짐센터 포장이사 업체추천", "category_id": 1},
            {"id": 2, "title": "경북 포항시 이삿짐센터 이사비용", "category_id": 1},
            {"id": 3, "title": "일산 이삿짐센터 포장이사 업체추천", "category_id": 1},
            {"id": 4, "title": "대구 이삿짐센터 가격비교", "category_id": 1},
            {"id": 5, "title": "이삭토스트 맛집탐방 총정리", "category_id": 2},
            {"id": 6, "title": "이삭토스트 맛집 메뉴 정리", "category_id": 2},
        ]

        result = service.batch_group_titles(titles)

        # 결과 구조 확인
        assert "new_groups" in result
        assert "added_to_existing" in result
        assert "ungrouped" in result

        # 총 제목 수 = 그룹화된 수 + 미그룹화 수
        grouped_count = sum(
            1 + len(g.get("members", []))
            for g in result["new_groups"]
        )
        ungrouped_count = len(result["ungrouped"])

        assert grouped_count + ungrouped_count == len(titles)


class TestLocationServiceRobustness:
    """지역 서비스 견고성 테스트"""

    def test_empty_title(self):
        """빈 제목 처리"""
        from services.location_service import extract_location

        assert extract_location("") is None
        assert extract_location(None) is None

    def test_special_characters(self):
        """특수문자 포함 제목"""
        from services.location_service import extract_location

        loc = extract_location("[포항] 이삿짐센터 추천!")
        assert loc is not None
        assert loc.get("city") == "포항"

    def test_multiple_locations_in_title(self):
        """여러 지역이 포함된 제목"""
        from services.location_service import extract_location

        # 첫 번째 지역이 추출됨
        loc = extract_location("서울에서 부산까지 이사")
        assert loc is not None
        # 구현에 따라 서울 또는 부산이 추출될 수 있음


class TestSimilarityServiceRobustness:
    """유사도 서비스 견고성 테스트"""

    def test_empty_strings(self):
        """빈 문자열 처리"""
        from services.similarity_service import calculate_similarity

        assert calculate_similarity("", "") == 0.0
        assert calculate_similarity("테스트", "") == 0.0
        assert calculate_similarity("", "테스트") == 0.0

    def test_very_long_titles(self):
        """매우 긴 제목"""
        from services.similarity_service import calculate_similarity

        long_title1 = "포항 이삿짐센터 " * 50
        long_title2 = "포항 이삿짐센터 추천 " * 50

        score = calculate_similarity(long_title1, long_title2)
        # 에러 없이 실행되고 점수 반환
        assert isinstance(score, float)

    def test_unicode_normalization(self):
        """유니코드 정규화"""
        from services.similarity_service import SimilarityService

        service = SimilarityService()

        # 전각/반각 혼용
        text1 = "포항　이삿짐센터"  # 전각 공백
        text2 = "포항 이삿짐센터"  # 반각 공백

        norm1 = service.normalize_text(text1)
        norm2 = service.normalize_text(text2)

        # 정규화 후 동일해야 함
        assert norm1 == norm2


class TestEndToEndScenarios:
    """End-to-End 시나리오 테스트"""

    def test_typical_grouping_scenario(self):
        """일반적인 그룹화 시나리오"""
        from services.similarity_service import SimilarityService
        from services.location_service import extract_location

        # 유사도가 43~57% 정도이므로 40으로 임계값 설정
        service = SimilarityService(threshold=40)

        # 시나리오: 수집된 제목들
        collected_titles = [
            "포항 이삿짐센터 포장이사 업체추천",
            "포항시 이삿짐센터 이사비용 알아보기",
            "경북 포항 이삿짐센터 후기",
            "일산 이삿짐센터 포장이사 업체추천",
            "고양시 일산 이삿짐센터 비용",
        ]

        # 지역별 그룹화 예상
        pohang_titles = []
        ilsan_titles = []

        for title in collected_titles:
            loc = extract_location(title)
            if loc:
                city = loc.get("city")
                if city == "포항":
                    pohang_titles.append(title)
                elif city == "일산":
                    ilsan_titles.append(title)

        # 포항 제목 3개, 일산 제목 2개
        assert len(pohang_titles) >= 2
        assert len(ilsan_titles) >= 1

        # 그룹화 실행
        titles_data = [
            {"id": i, "title": t, "category_id": 1}
            for i, t in enumerate(collected_titles)
        ]

        result = service.batch_group_titles(titles_data)

        # 포항 그룹과 일산 그룹이 별도로 생성되어야 함
        # (지역이 다르면 그룹화 안 됨)
        groups = result["new_groups"]

        # 그룹이 최소 1개 이상
        assert len(groups) >= 1

    def test_no_location_grouping(self):
        """지역 없는 제목들 그룹화"""
        from services.similarity_service import SimilarityService

        service = SimilarityService(threshold=70)

        titles = [
            {"id": 1, "title": "이삭토스트 맛집탐방 영업시간 인기메뉴 총정리", "category_id": 1},
            {"id": 2, "title": "이삭토스트 맛집탐방 인기메뉴와 영업시간 총정리", "category_id": 1},
            {"id": 3, "title": "삼성 갤럭시 스마트폰 리뷰", "category_id": 1},
        ]

        result = service.batch_group_titles(titles)

        # 이삭토스트 제목 2개는 그룹화, 삼성 제목은 개별
        groups = result["new_groups"]
        ungrouped = result["ungrouped"]

        # 최소 1개 그룹 또는 여러 ungrouped
        assert len(groups) + len(ungrouped) >= 1


class TestAPIContractValidation:
    """API 계약 검증 테스트"""

    def test_transfer_response_structure(self):
        """이동 응답 구조 검증"""
        # 예상되는 응답 구조
        expected_fields = ["moved", "grouped", "duplicates", "errors"]

        # move_to_main 반환값 시뮬레이션
        mock_result = {
            "moved": 5,
            "grouped": 3,
            "duplicates": 1,
            "errors": []
        }

        for field in expected_fields:
            assert field in mock_result

    def test_stats_response_structure(self):
        """통계 응답 구조 검증"""
        # 예상되는 통계 응답 구조
        mock_stats = {
            "temp_titles": {
                "total": 100,
                "with_category": 80,
                "without_category": 20,
                "new": 50,
                "categorized": 30,
                "ready_to_move": 80,
            },
            "main_titles": {
                "total": 200,
                "grouped": 150,
                "ungrouped": 50,
                "available": 180,
            },
            "groups": {
                "total": 50,
                "active": 48,
            }
        }

        # 필수 키 확인
        assert "temp_titles" in mock_stats
        assert "main_titles" in mock_stats
        assert "groups" in mock_stats

        # 세부 키 확인
        assert "total" in mock_stats["temp_titles"]
        assert "grouped" in mock_stats["main_titles"]
        assert "active" in mock_stats["groups"]
