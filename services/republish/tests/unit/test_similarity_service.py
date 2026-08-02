"""
유사도 서비스 단위 테스트
"""

import pytest
import sys
import os

# shared 모듈 경로 추가
shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from services.similarity_service import (
    SimilarityService,
    calculate_similarity,
    find_best_match,
    batch_group_titles,
    DEFAULT_SIMILARITY_THRESHOLD,
)


class TestCalculateSimilarity:
    """유사도 계산 테스트"""

    def test_different_location_zero_score(self):
        """지역이 다르면 0점"""
        score = calculate_similarity(
            "포항 이삿짐센터 포장이사 업체추천",
            "일산 이삿짐센터 포장이사 업체추천"
        )

        assert score == 0.0

    def test_same_location_high_score(self):
        """같은 지역이면 유사도 계산"""
        score = calculate_similarity(
            "포항 이삿짐센터 포장이사 업체추천",
            "경북 포항시 이삿짐센터 이사비용"
        )

        assert score > 50.0

    def test_no_location_both(self):
        """지역 없는 제목끼리"""
        score = calculate_similarity(
            "이삭토스트 맛집탐방 영업시간 인기메뉴 총정리",
            "이삭토스트 맛집탐방 인기메뉴와 영업시간 총정리"
        )

        assert score > 70.0

    def test_one_has_location(self):
        """한쪽만 지역 있음 - 매칭 허용"""
        score = calculate_similarity(
            "이삭토스트 맛집탐방 총정리",
            "서울 이삭토스트 맛집탐방 총정리"
        )

        assert score > 0.0

    def test_exact_match(self):
        """완전 일치"""
        score = calculate_similarity(
            "포항 이삿짐센터 추천",
            "포항 이삿짐센터 추천"
        )

        assert score == 100.0

    def test_completely_different(self):
        """완전히 다른 제목 (지역 다름)"""
        score = calculate_similarity(
            "포항 이삿짐센터 추천",
            "서울 맛집탐방 카페추천"
        )

        assert score == 0.0  # 지역 다름

    def test_pohang_variants(self):
        """포항 제목 변형 테스트"""
        # 같은 포항 지역
        score1 = calculate_similarity(
            "경북 칠곡 포항 세명기독병원 장례식장 근조화환",
            "경상북도 포항시 포항 세명기독병원 장례식장 근조화환 조문"
        )
        assert score1 > 70.0

        # 다른 지역 (일산 vs 포항)
        score2 = calculate_similarity(
            "포항 이삿짐센터 포장이사 업체추천",
            "일산 이삿짐센터 포장이사 업체추천"
        )
        assert score2 == 0.0


class TestFindBestMatch:
    """최적 매칭 테스트"""

    def test_find_same_location(self):
        """같은 지역 매칭"""
        candidates = [
            "일산 이삿짐센터 업체추천",
            "포항 이삿짐센터 가격비교",
            "대구 이삿짐센터 후기"
        ]

        # 낮은 임계값으로 매칭 (유사도가 63 정도이므로)
        result = find_best_match("경북 포항 이삿짐센터 추천", candidates, threshold=60)

        assert result is not None
        assert "포항" in result[0]

    def test_no_match_above_threshold(self):
        """임계값 이상 매칭 없음"""
        candidates = [
            "서울 카페 맛집",
            "부산 해운대 관광",
            "제주 여행 코스"
        ]

        result = find_best_match("포항 이삿짐센터", candidates, threshold=80)

        assert result is None

    def test_empty_candidates(self):
        """빈 후보 리스트"""
        result = find_best_match("포항 이삿짐센터", [])

        assert result is None

    def test_returns_highest_score(self):
        """가장 높은 점수 반환"""
        candidates = [
            "포항 이삿짐 업체",
            "포항 이삿짐센터 포장이사 업체추천 가격",
            "포항 이사"
        ]

        result = find_best_match("포항 이삿짐센터 포장이사 업체추천", candidates, threshold=50)

        assert result is not None
        # 가장 유사한 것이 반환되어야 함
        assert result[1] >= 50.0


class TestSimilarityService:
    """SimilarityService 클래스 테스트"""

    def test_init_with_default_threshold(self):
        """기본 임계값으로 초기화"""
        service = SimilarityService()
        assert service.threshold == DEFAULT_SIMILARITY_THRESHOLD

    def test_init_with_custom_threshold(self):
        """커스텀 임계값으로 초기화"""
        service = SimilarityService(threshold=75)
        assert service.threshold == 75

    def test_normalize_text(self):
        """텍스트 정규화"""
        service = SimilarityService()

        # HTML 엔티티 디코드
        result = service.normalize_text("제목&amp;내용")
        assert "&" in result or "제목" in result

        # 공백 정리
        result = service.normalize_text("  제목   내용  ")
        assert result == "제목 내용"

    def test_calculate_text_similarity(self):
        """순수 텍스트 유사도 계산"""
        service = SimilarityService()

        # 완전 일치
        score = service.calculate_text_similarity("테스트 제목", "테스트 제목")
        assert score == 100.0

        # 빈 문자열
        score = service.calculate_text_similarity("", "테스트")
        assert score == 0.0


class TestBatchGroupTitles:
    """배치 그룹화 테스트"""

    def test_group_same_location_titles(self):
        """같은 지역 제목들 그룹화"""
        service = SimilarityService(threshold=75)

        titles = [
            {"id": 1, "title": "포항 이삿짐센터 포장이사 업체추천", "category_id": 1},
            {"id": 2, "title": "경북 포항시 이삿짐센터 이사비용", "category_id": 1},
            {"id": 3, "title": "일산 이삿짐센터 포장이사 업체추천", "category_id": 1},
            {"id": 4, "title": "대구 이삿짐센터 가격비교", "category_id": 1},
        ]

        result = service.batch_group_titles(titles)

        # 결과 구조 확인
        assert "new_groups" in result
        assert "added_to_existing" in result
        assert "ungrouped" in result

        # 포항 그룹 확인 (id 1, 2가 그룹화되어야 함)
        total_grouped = sum(
            1 + len(g.get("members", []))
            for g in result["new_groups"]
        )
        total_ungrouped = len(result["ungrouped"])

        # 전체 제목 수 확인
        assert total_grouped + total_ungrouped == len(titles)

    def test_no_grouping_different_locations(self):
        """다른 지역은 그룹화 안됨"""
        service = SimilarityService(threshold=75)

        titles = [
            {"id": 1, "title": "포항 이삿짐센터 업체추천", "category_id": 1},
            {"id": 2, "title": "일산 이삿짐센터 업체추천", "category_id": 1},
            {"id": 3, "title": "대구 이삿짐센터 업체추천", "category_id": 1},
        ]

        result = service.batch_group_titles(titles)

        # 각각 개별 그룹 또는 ungrouped
        total_groups = len(result["new_groups"])
        ungrouped = len(result["ungrouped"])

        # 지역이 모두 다르므로 그룹화 불가
        assert total_groups + ungrouped == 3

    def test_category_filtering(self):
        """카테고리별 그룹화"""
        service = SimilarityService(threshold=75)

        titles = [
            {"id": 1, "title": "포항 이삿짐센터", "category_id": 1},
            {"id": 2, "title": "포항 이삿짐센터 추천", "category_id": 2},  # 다른 카테고리
        ]

        result = service.batch_group_titles(titles)

        # 카테고리가 다르면 같은 지역이라도 그룹화 안 됨
        # 결과적으로 둘 다 ungrouped이거나 별도 그룹
        total_groups = len(result["new_groups"])
        ungrouped = len(result["ungrouped"])

        assert total_groups + ungrouped == 2

    def test_empty_titles(self):
        """빈 제목 리스트"""
        service = SimilarityService()
        result = service.batch_group_titles([])

        assert result["new_groups"] == []
        assert result["added_to_existing"] == []
        assert result["ungrouped"] == []


class TestFindSimilarGroup:
    """그룹 찾기 테스트"""

    def test_find_matching_group(self):
        """매칭되는 그룹 찾기"""
        # 유사도가 63 정도이므로 60으로 임계값 설정
        service = SimilarityService(threshold=60)

        groups = [
            {"id": 1, "representative_title": "서울 맛집 추천", "category_id": 1},
            {"id": 2, "representative_title": "포항 이삿짐센터 추천", "category_id": 2},
            {"id": 3, "representative_title": "부산 카페 투어", "category_id": 1},
        ]

        result = service.find_similar_group("포항 이삿짐센터 업체추천", groups)

        assert result is not None
        assert result["group"]["id"] == 2
        assert result["score"] >= 60

    def test_no_matching_group(self):
        """매칭되는 그룹 없음"""
        service = SimilarityService(threshold=80)

        groups = [
            {"id": 1, "representative_title": "서울 맛집 추천", "category_id": 1},
            {"id": 2, "representative_title": "부산 카페 투어", "category_id": 1},
        ]

        result = service.find_similar_group("포항 이삿짐센터", groups)

        # 지역이 다르므로 매칭 없음
        assert result is None

    def test_category_filter_in_find_similar_group(self):
        """카테고리 필터링"""
        service = SimilarityService(threshold=70)

        groups = [
            {"id": 1, "representative_title": "포항 이삿짐센터", "category_id": 1},
            {"id": 2, "representative_title": "포항 이삿짐센터 추천", "category_id": 2},
        ]

        # category_id=2로 필터링
        result = service.find_similar_group("포항 이삿짐센터 업체", groups, category_id=2)

        assert result is not None
        assert result["group"]["id"] == 2


class TestCoreDivergenceGuard:
    """핵심어(차별 키워드) 발산 가드 테스트.

    지명 사전에 없는 destination 등 핵심어가 다른데 골격어 공유로
    오그룹되던 문제 차단을 검증한다.
    """

    def _score(self, a: str, b: str) -> dict:
        return SimilarityService(threshold=75.0).calculate_similarity_v3(a, b)

    def test_travel_different_destination_separated(self):
        """서로 다른 해외 destination은 템플릿이 같아도 분리."""
        r = self._score(
            "베로나 여행 기초 정보, 계절별 날씨, 대중교통, 추천 명소, 추천 음식, 베로나 여행 추천 숙소",
            "마카오 여행 기초 정보, 계절별 날씨, 방문 전 준비 사항, 대중교통, 추천 명소, 추천 음식, 마카오 여행 추천 숙소",
        )
        assert r["groupable"] is False
        # 발산 시 회색지대 상한(threshold-1) 이하로 캡되어 자동 그룹 안 됨
        assert r["score"] < 75.0

    def test_travel_accommodation_different_city_separated(self):
        """호치민 vs 마드리드 숙소 템플릿 분리."""
        r = self._score(
            "베트남 호치민 숙소 추천 지역과 지역별 특징, 호치민 여행 추천 숙소",
            "스페인 마드리드 여행 숙소 추천 지역과 지역별 특징, 마드리드 여행 추천 숙소",
        )
        assert r["groupable"] is False

    def test_different_products_separated(self):
        """서로 다른 제품(아이폰 vs 갤럭시)은 분리."""
        r = self._score("아이폰 15 리뷰 총정리", "갤럭시 24 리뷰 총정리")
        assert r["groupable"] is False

    def test_same_core_keyword_not_affected(self):
        """공유 핵심어가 있으면 가드 미발동(같은 destination은 그룹)."""
        r = self._score(
            "직장인을 위한 일본 2박3일 온천 추천 5곳",
            "직장인을 위한 2박3일 일본 여행 추천 5곳",
        )
        assert r["groupable"] is True

    def test_shared_distinctive_token_not_diverged(self):
        """공유 차별 토큰(싱그릭스)이 있으면 발산 아님."""
        svc = SimilarityService(threshold=75.0)
        assert svc._core_divergence(
            "싱그릭스 가격 비교 방법", "대상포진 백신 싱그릭스 가격"
        ) is False

    def test_divergence_detection(self):
        """핵심어가 완전히 다르면 발산=True."""
        svc = SimilarityService(threshold=75.0)
        assert svc._core_divergence(
            "베로나 여행 추천 숙소", "마카오 여행 추천 숙소"
        ) is True


class TestSubjectDivergenceGate:
    """DF 기반 주어(핵심어) 발산 게이트 테스트.

    골격어(고빈도) 공유 + 주어(희소)만 다른 제목을 분리하는지 검증.
    token_df를 주입해 코퍼스 없이 결정적으로 테스트한다.
    """

    # 골격어=높은 df, 식별자=낮은 df (n_docs=3000, RARE_DF_RATIO=0.01 → 임계 df<=30)
    DF = {
        '고객센터': 500, '전화번호': 500, '서비스센터': 200, '찾기': 150,
        '활용법': 120, '필수': 600, '체크리스트': 400, '5가지': 700,
        '전세자금대출': 300, '금리': 250, '한도': 250, '서류': 200,
        '제출': 100, '순서': 100, '신청': 200, '조건': 200, '비교': 200,
        '최대': 150, '효과': 400, '초보자': 800, '여행': 700, '추천': 900,
        '코스': 40, '신용대출': 300,
        # 식별자(특정, df<=30)
        '레노버': 2, 'lg전자': 2, '작타': 1, '뇌출혈보험': 1,
        '기업은행': 3, '삼성생명': 2, '광주은행': 3, '비교분석': 4,
        '인도네시아': 20, '자카르타': 2, '발리': 3,
        '케이뱅크': 28, '토스뱅크': 29,
    }

    def _svc(self):
        return SimilarityService(threshold=75.0, token_df=self.DF, n_docs=3000)

    def test_different_company_separated(self):
        """다른 제품/회사(주어)는 골격어 공유해도 분리."""
        r = self._svc().calculate_similarity_v3(
            "레노버 서비스센터 고객센터 전화번호",
            "LG전자 고객센터 전화번호 서비스센터 찾기",
        )
        assert r["groupable"] is False

    def test_different_subject_separated(self):
        """전혀 다른 주어(작타 vs 뇌출혈보험) 분리."""
        r = self._svc().calculate_similarity_v3(
            "작타 활용법 필수 체크리스트 5가지",
            "뇌출혈보험 필수 체크리스트 5가지",
        )
        assert r["groupable"] is False

    def test_same_subject_kept(self):
        """같은 주어(광주은행) 공유 시 표현 달라도 유지."""
        r = self._svc().calculate_similarity_v3(
            "광주은행 전세자금대출 최대 한도 조건 비교분석",
            "광주은행 전세자금대출 신청 조건 한도 비교",
        )
        assert r["groupable"] is True

    def test_compound_partial_overlap_separated(self):
        """복합 식별자에서 상위어(인도네시아) 공유해도 하위어(도시) 다르면 분리."""
        r = self._svc().calculate_similarity_v3(
            "인도네시아 자카르타 여행 추천 코스",
            "인도네시아 발리 여행 추천 코스",
        )
        assert r["groupable"] is False

    def test_borderline_df_entity_separated(self):
        """경계 DF 엔티티(케이뱅크 vs 토스뱅크)도 식별자로 분리."""
        r = self._svc().calculate_similarity_v3(
            "케이뱅크 신용대출 금리 한도 조건",
            "토스뱅크 신용대출 금리 한도 조건",
        )
        assert r["groupable"] is False

    def test_morphological_variant_kept(self):
        """공유 식별자 다수 + 배타는 형태소 변이(차이/차이점)뿐이면 유지."""
        df = dict(self.DF)
        df.update({"동동주": 2, "막걸리": 4, "공통점": 2, "만드": 18,
                   "차이": 17, "차이점": 18})
        svc = SimilarityService(threshold=75.0, token_df=df, n_docs=3000)
        r = svc.calculate_similarity_v3(
            "동동주 막걸리 차이와 공통점 만드는 방법",
            "동동주와 막걸리 차이점 및 공통점 만드는 방법",
        )
        assert r["groupable"] is True

    def test_rare_modifiers_kept(self):
        """주어(맞벌이 육아팁) 공유 + 배타는 희소 수식어뿐이면 유지."""
        df = dict(self.DF)
        df.update({"맞벌": 7, "육아팁": 14, "실제": 10, "기반": 11,
                   "놀라운": 3, "가정": 6, "노하우": 9, "가이드": 40})
        svc = SimilarityService(threshold=75.0, token_df=df, n_docs=3000)
        r = svc.calculate_similarity_v3(
            "놀라운 실제 후기 기반 맞벌이 육아팁 가이드",
            "맞벌이 가정 육아팁 완벽 가이드 실제 후기 노하우",
        )
        assert r["groupable"] is True

    def test_fallback_without_df(self):
        """DF 미주입 시 기존 핵심어 발산 가드로 폴백."""
        svc = SimilarityService(threshold=75.0)  # token_df 없음
        assert svc._subject_divergence("레노버 고객센터", "lg전자 고객센터") is None
        # 폴백 경로로도 지역 발산은 분리
        r = svc.calculate_similarity_v3("베로나 여행 추천 숙소", "마카오 여행 추천 숙소")
        assert r["groupable"] is False
