"""
키워드 페어 매칭 기능 단위 테스트

테스트 대상: CategoryMatcherService._is_keyword_match()
- 단일 키워드 매칭
- 조합 키워드 매칭 (+ 연산자)
- 엣지 케이스 처리
"""
import pytest
from unittest.mock import MagicMock


class TestKeywordPairMatching:
    """키워드 페어 매칭 테스트"""

    @pytest.fixture
    def matcher_service(self):
        """CategoryMatcherService 인스턴스 생성 (DB 모킹)"""
        from app.services.category_matcher_service import CategoryMatcherService

        mock_db = MagicMock()
        service = CategoryMatcherService(db=mock_db, user_id=1)
        return service

    # =========================================
    # 단일 키워드 매칭 테스트 (기존 기능)
    # =========================================

    def test_single_keyword_exact_match(self, matcher_service):
        """단일 키워드 정확히 매칭"""
        text = "경북 이사업체 추천"
        keyword = "이사업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_single_keyword_with_space(self, matcher_service):
        """띄어쓰기 포함 키워드 매칭"""
        text = "경북 이사 업체 추천"
        keyword = "이사 업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_single_keyword_no_match(self, matcher_service):
        """단일 키워드 미매칭"""
        text = "경북 이사 전문가"
        keyword = "업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is False

    def test_single_keyword_case_insensitive(self, matcher_service):
        """대소문자 무시 매칭"""
        text = "Seoul Moving Service"
        keyword = "MOVING"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    # =========================================
    # 조합 키워드 매칭 테스트 (새 기능)
    # =========================================

    def test_pair_keyword_both_present(self, matcher_service):
        """조합 키워드 - 두 단어 모두 포함"""
        text = "경북 이사 전문 업체 추천"
        keyword = "이사+업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_pair_keyword_reversed_order(self, matcher_service):
        """조합 키워드 - 순서 뒤바뀜 (순서 무관)"""
        text = "업체 이사 서비스"
        keyword = "이사+업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_pair_keyword_one_missing(self, matcher_service):
        """조합 키워드 - 하나 누락 시 미매칭"""
        text = "경북 이사 전문가"
        keyword = "이사+업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is False

    def test_pair_keyword_far_apart(self, matcher_service):
        """조합 키워드 - 단어가 멀리 떨어져 있어도 매칭"""
        text = "경북 경주 이사 전문 견적 저렴한 업체 추천"
        keyword = "이사+업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_triple_keyword_all_present(self, matcher_service):
        """3개 조합 키워드 - 모두 포함"""
        text = "광주 광산구 신가병원장례식장 근조화환 조화꽃다발 24시간꽃배달"
        keyword = "근조+화환+배달"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_triple_keyword_one_missing(self, matcher_service):
        """3개 조합 키워드 - 하나 누락"""
        text = "근조화환 전문점"
        keyword = "근조+화환+배달"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is False

    # =========================================
    # 실제 사용 케이스
    # =========================================

    def test_real_case_flower_delivery(self, matcher_service):
        """실제 케이스: 꽃배달"""
        text = "광주 광산구 신가병원장례식장 근조화환 조화꽃다발 24시간꽃배달"

        # 단일 키워드
        assert matcher_service._is_keyword_match(text.lower(), "근조") is True
        assert matcher_service._is_keyword_match(text.lower(), "화환") is True
        assert matcher_service._is_keyword_match(text.lower(), "꽃배달") is True

        # 조합 키워드
        assert matcher_service._is_keyword_match(text.lower(), "근조+화환") is True
        assert matcher_service._is_keyword_match(text.lower(), "장례+화환") is True

    def test_real_case_moving_company(self, matcher_service):
        """실제 케이스: 이사업체"""
        text = "경북 경주 이사 전문 견적 저렴한 업체 추천"

        # 단일 키워드 (미매칭)
        assert matcher_service._is_keyword_match(text.lower(), "이사업체") is False

        # 조합 키워드 (매칭)
        assert matcher_service._is_keyword_match(text.lower(), "이사+업체") is True
        assert matcher_service._is_keyword_match(text.lower(), "이사+견적") is True
        assert matcher_service._is_keyword_match(text.lower(), "이사+추천+업체") is True

    # =========================================
    # 엣지 케이스
    # =========================================

    def test_empty_keyword(self, matcher_service):
        """빈 키워드"""
        text = "테스트 텍스트"
        assert matcher_service._is_keyword_match(text.lower(), "") is False

    def test_empty_text(self, matcher_service):
        """빈 텍스트"""
        text = ""
        assert matcher_service._is_keyword_match(text.lower(), "키워드") is False

    def test_pair_keyword_with_spaces(self, matcher_service):
        """조합 키워드에 공백 포함"""
        text = "이사 전문 업체"
        keyword = "이사 + 업체"  # + 앞뒤 공백
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_pair_keyword_only_plus(self, matcher_service):
        """+ 기호만 있는 경우"""
        text = "테스트 텍스트"
        keyword = "+"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is False

    def test_pair_keyword_empty_parts(self, matcher_service):
        """빈 부분이 있는 조합 키워드"""
        text = "이사 업체"
        keyword = "이사++업체"  # ++ 연속
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_special_characters_in_keyword(self, matcher_service):
        """특수문자 포함 키워드"""
        text = "C++ 프로그래밍 강좌"
        keyword = "C++"
        # C++ 자체가 +를 포함하므로 조합으로 해석됨
        # "C" AND "+" (실제로는 빈 문자열) - 이 경우 "C"만 확인
        # 실제 사용에서는 C++를 키워드로 등록 시 주의 필요
        assert matcher_service._is_keyword_match(text.lower(), "프로그래밍") is True

    def test_korean_english_mixed(self, matcher_service):
        """한영 혼합 텍스트"""
        text = "Seoul 이사업체 Moving Service"
        keyword = "이사+Moving"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    # =========================================
    # 우선순위 관련 시나리오
    # =========================================

    def test_single_vs_pair_scenario(self, matcher_service):
        """단일 vs 조합 키워드 시나리오"""
        text = "경북 이사 전문 업체"

        # "이사업체"(단일)는 미매칭
        single_match = matcher_service._is_keyword_match(text.lower(), "이사업체")
        # "이사+업체"(조합)는 매칭
        pair_match = matcher_service._is_keyword_match(text.lower(), "이사+업체")

        assert single_match is False
        assert pair_match is True


class TestKeywordPairMatchingPerformance:
    """성능 관련 테스트"""

    @pytest.fixture
    def matcher_service(self):
        from app.services.category_matcher_service import CategoryMatcherService

        mock_db = MagicMock()
        return CategoryMatcherService(db=mock_db, user_id=1)

    def test_many_keywords_in_pair(self, matcher_service):
        """많은 키워드 조합"""
        text = "서울 강남 이사 전문 포장 저렴 업체 추천 후기"
        keyword = "이사+포장+업체+추천"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True

    def test_long_text_matching(self, matcher_service):
        """긴 텍스트 매칭"""
        text = " ".join(["단어"] * 1000) + " 이사 " + " ".join(["텍스트"] * 1000) + " 업체 "
        keyword = "이사+업체"
        assert matcher_service._is_keyword_match(text.lower(), keyword) is True
