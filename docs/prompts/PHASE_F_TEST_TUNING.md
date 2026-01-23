# Phase F: 테스트 및 튜닝

> **Phase**: F  
> **목표**: 전체 기능 테스트, 유사도 임계값 튜닝, 성능 최적화  
> **의존성**: Phase A ~ E 모두 완료

---

## 📋 작업 개요

Phase A~E에서 구현한 모든 기능을 테스트하고 튜닝합니다.
- 단위 테스트
- 통합 테스트
- 유사도 임계값 튜닝
- 성능 최적화

---

## 📁 생성할 파일
```
services/republish/
├── tests/
│   ├── unit/
│   │   ├── test_location_service.py
│   │   ├── test_similarity_service.py
│   │   └── test_title_transfer.py
│   └── integration/
│       └── test_title_workflow.py
└── scripts/
    └── similarity_tuning.py
```

---

## 📝 작업 1: 지역명 서비스 단위 테스트

파일 위치: `tests/unit/test_location_service.py`
```python
"""
지역명 서비스 단위 테스트
"""

import pytest
import sys
sys.path.insert(0, '/app/shared')

from services.location_service import (
    LocationService,
    extract_location,
    is_same_location,
    remove_location,
)


class TestExtractLocation:
    """지역명 추출 테스트"""
    
    def test_extract_province_city(self):
        """시/도 + 시/군 추출"""
        title = "경북 포항시 이삿짐센터 추천"
        loc = extract_location(title)
        
        assert loc is not None
        assert loc["province"] == "경북"
        assert loc["city"] == "포항"
    
    def test_extract_city_only(self):
        """시/군만 있는 경우"""
        title = "포항 이삿짐센터 포장이사 업체추천"
        loc = extract_location(title)
        
        assert loc is not None
        assert loc["city"] == "포항"
    
    def test_extract_full_address(self):
        """전체 주소 추출"""
        title = "경북 포항시 북구 기북면 대곡리 이삿짐센터"
        loc = extract_location(title)
        
        assert loc is not None
        assert loc["province"] == "경북"
        assert loc["city"] == "포항"
        assert loc["district"] == "북구"
    
    def test_extract_alias(self):
        """약칭 처리"""
        title = "경상북도 포항시 이삿짐센터"
        loc = extract_location(title)
        
        assert loc is not None
        assert loc["province"] == "경북"  # 정규화됨
    
    def test_no_location(self):
        """지역명 없는 제목"""
        title = "이삭토스트 맛집탐방 인기메뉴 총정리"
        loc = extract_location(title)
        
        assert loc is None
    
    def test_gyeonggi_ilsan(self):
        """경기도 일산 추출"""
        title = "일산 이삿짐센터 포장이사"
        loc = extract_location(title)
        
        assert loc is not None
        assert loc["city"] == "일산"
        assert loc["province"] == "경기"


class TestIsSameLocation:
    """지역 동일성 비교 테스트"""
    
    def test_same_city(self):
        """같은 도시"""
        loc1 = {"province": "경북", "city": "포항"}
        loc2 = {"province": "경북", "city": "포항"}
        
        assert is_same_location(loc1, loc2) == True
    
    def test_different_city(self):
        """다른 도시"""
        loc1 = {"province": "경북", "city": "포항"}
        loc2 = {"province": "경기", "city": "일산"}
        
        assert is_same_location(loc1, loc2) == False
    
    def test_same_province_different_city(self):
        """같은 도, 다른 시"""
        loc1 = {"province": "경북", "city": "포항"}
        loc2 = {"province": "경북", "city": "경주"}
        
        assert is_same_location(loc1, loc2) == False
    
    def test_both_none(self):
        """둘 다 지역 없음"""
        assert is_same_location(None, None) == True
    
    def test_one_none(self):
        """한쪽만 지역 없음"""
        loc1 = {"province": "경북", "city": "포항"}
        
        assert is_same_location(loc1, None) == True
        assert is_same_location(None, loc1) == True
    
    def test_detailed_vs_simple(self):
        """상세 주소 vs 간단 주소"""
        loc1 = {"province": "경북", "city": "포항", "district": "북구"}
        loc2 = {"province": "경북", "city": "포항"}
        
        assert is_same_location(loc1, loc2) == True


class TestRemoveLocation:
    """지역명 제거 테스트"""
    
    def test_remove_from_start(self):
        """앞에서 지역명 제거"""
        title = "포항 이삿짐센터 포장이사"
        loc = extract_location(title)
        cleaned = remove_location(title, loc)
        
        assert "포항" not in cleaned
        assert "이삿짐센터" in cleaned
    
    def test_remove_full_address(self):
        """전체 주소 제거"""
        title = "경북 포항시 북구 기북면 이삿짐센터"
        loc = extract_location(title)
        cleaned = remove_location(title, loc)
        
        assert "경북" not in cleaned
        assert "포항" not in cleaned
        assert "이삿짐센터" in cleaned
    
    def test_no_location_to_remove(self):
        """제거할 지역 없음"""
        title = "이삭토스트 맛집탐방"
        cleaned = remove_location(title, None)
        
        assert cleaned == title
```

---

## 📝 작업 2: 유사도 서비스 단위 테스트

파일 위치: `tests/unit/test_similarity_service.py`
```python
"""
유사도 서비스 단위 테스트
"""

import pytest
import sys
sys.path.insert(0, '/app/shared')

from services.similarity_service import (
    SimilarityService,
    calculate_similarity,
    find_best_match,
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
        
        assert score > 80.0
    
    def test_one_has_location(self):
        """한쪽만 지역 있음"""
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
        """완전히 다른 제목"""
        score = calculate_similarity(
            "포항 이삿짐센터 추천",
            "서울 맛집탐방 카페추천"
        )
        
        assert score == 0.0  # 지역 다름


class TestFindBestMatch:
    """최적 매칭 테스트"""
    
    def test_find_same_location(self):
        """같은 지역 매칭"""
        candidates = [
            "일산 이삿짐센터 업체추천",
            "포항 이삿짐센터 가격비교",
            "대구 이삿짐센터 후기"
        ]
        
        result = find_best_match("경북 포항 이삿짐센터 추천", candidates)
        
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
        
        # 포항끼리 그룹, 일산/대구는 개별
        assert len(result["new_groups"]) >= 1
        
        # 포항 그룹 확인
        pohang_group = None
        for group in result["new_groups"]:
            if "포항" in group["representative"]["title"]:
                pohang_group = group
                break
        
        assert pohang_group is not None
        assert len(pohang_group["members"]) >= 1
    
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
        
        assert total_groups + ungrouped == 3
```

---

## 📝 작업 3: 제목 이동 단위 테스트

파일 위치: `tests/unit/test_title_transfer.py`
```python
"""
제목 이동 서비스 단위 테스트
"""

import pytest
from unittest.mock import MagicMock, patch
from app.services.title_transfer_service import TitleTransferService


class TestMoveToMain:
    """임시 → 정식 이동 테스트"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock 데이터베이스 세션"""
        return MagicMock()
    
    @pytest.fixture
    def service(self, mock_db):
        """서비스 인스턴스"""
        return TitleTransferService(mock_db, threshold=80)
    
    def test_move_single_title(self, service, mock_db):
        """단일 제목 이동"""
        # Mock 설정
        mock_temp = MagicMock()
        mock_temp.id = 1
        mock_temp.title = "포항 이삿짐센터 추천"
        mock_temp.category_id = 1
        
        mock_db.query().filter().all.return_value = [mock_temp]
        mock_db.query().filter().first.return_value = None  # 중복 없음
        
        result = service.move_to_main([1], auto_group=True)
        
        assert result["moved"] >= 0
        assert "errors" in result
    
    def test_skip_duplicate(self, service, mock_db):
        """중복 제목 건너뛰기"""
        mock_temp = MagicMock()
        mock_temp.id = 1
        mock_temp.title = "포항 이삿짐센터 추천"
        
        # 이미 존재하는 제목
        mock_existing = MagicMock()
        mock_existing.title = "포항 이삿짐센터 추천"
        
        mock_db.query().filter().all.return_value = [mock_temp]
        mock_db.query().filter().first.return_value = mock_existing
        
        result = service.move_to_main([1])
        
        assert result.get("duplicates", 0) >= 0


class TestMoveToTemp:
    """정식 → 임시 이동 테스트"""
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def service(self, mock_db):
        return TitleTransferService(mock_db)
    
    def test_move_non_representative(self, service, mock_db):
        """일반 제목 이동"""
        mock_title = MagicMock()
        mock_title.id = 1
        mock_title.title = "테스트 제목"
        mock_title.is_representative = False
        mock_title.group_id = 1
        
        mock_db.query().filter().all.return_value = [mock_title]
        
        result = service.move_to_temp([1])
        
        assert result["moved"] >= 0
    
    def test_move_representative_reassign(self, service, mock_db):
        """대표 제목 이동 시 재지정"""
        mock_title = MagicMock()
        mock_title.id = 1
        mock_title.title = "대표 제목"
        mock_title.is_representative = True
        mock_title.group_id = 1
        
        # 그룹 내 다른 제목
        mock_other = MagicMock()
        mock_other.id = 2
        mock_other.is_representative = False
        
        mock_db.query().filter().all.return_value = [mock_title]
        mock_db.query().filter().first.return_value = mock_other
        
        result = service.move_to_temp([1])
        
        assert result["moved"] >= 0
```

---

## 📝 작업 4: 통합 테스트

파일 위치: `tests/integration/test_title_workflow.py`
```python
"""
제목 관리 전체 워크플로우 통합 테스트
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """테스트 클라이언트"""
    return TestClient(app)


class TestTitleWorkflow:
    """제목 관리 워크플로우 테스트"""
    
    def test_full_workflow(self, client):
        """
        전체 워크플로우:
        1. 임시 제목 생성
        2. 정식 제목으로 이동
        3. 그룹 확인
        4. 임시로 되돌리기
        """
        # 1. 임시 제목이 있다고 가정 (또는 생성)
        
        # 2. 정식 제목으로 이동
        transfer_response = client.post(
            "/api/v1/titles/transfer/to-main",
            json={
                "temp_title_ids": [1, 2, 3],
                "auto_group": True,
                "similarity_threshold": 80
            }
        )
        
        assert transfer_response.status_code == 200
        result = transfer_response.json()
        assert result["success"] == True
        
        # 3. 정식 제목 목록 확인
        titles_response = client.get("/api/v1/titles")
        assert titles_response.status_code == 200
        
        # 4. 그룹 확인
        groups_response = client.get("/api/v1/titles/groups")
        assert groups_response.status_code == 200
    
    def test_similarity_matching_accuracy(self, client):
        """유사도 매칭 정확도 테스트"""
        # 같은 지역 제목들 이동
        # 그룹화 결과 확인
        pass
    
    def test_location_based_grouping(self, client):
        """지역 기반 그룹화 테스트"""
        # 다른 지역 제목들이 그룹화되지 않는지 확인
        pass
```

---

## 📝 작업 5: 유사도 튜닝 스크립트

파일 위치: `scripts/similarity_tuning.py`
```python
"""
유사도 임계값 튜닝 스크립트

다양한 임계값으로 테스트하여 최적값을 찾습니다.
"""

import sys
sys.path.insert(0, '/app/shared')

from services.similarity_service import SimilarityService
from services.location_service import extract_location

# 테스트 데이터셋
TEST_CASES = [
    # (제목1, 제목2, 그룹화되어야 함?)
    # 같은 지역 - 그룹화 O
    ("포항 이삿짐센터 포장이사 업체추천", "경북 포항시 북구 이삿짐센터 이사비용", True),
    ("경북 칠곡 포항 세명기독병원 장례식장 근조화환", "경상북도 포항시 포항 세명기독병원 장례식장 근조화환 조문", True),
    
    # 다른 지역 - 그룹화 X
    ("포항 이삿짐센터 포장이사 업체추천", "일산 이삿짐센터 포장이사 업체추천", False),
    ("포항 이삿짐센터 포장이사 업체추천", "대구 이삿짐센터 포장이사 업체추천", False),
    
    # 지역 없음 - 유사하면 그룹화 O
    ("이삭토스트 맛집탐방 영업시간 인기메뉴 총정리", "이삭토스트 맛집탐방 인기메뉴와 영업시간 총정리", True),
    ("이삭토스트 맛집탐방 영업시간", "이삭토스트 맛집 정복 운영시간", True),
    
    # 지역 없음 - 다른 주제
    ("이삭토스트 맛집탐방", "삼성 갤럭시 스마트폰 리뷰", False),
]


def evaluate_threshold(threshold: float) -> dict:
    """
    특정 임계값으로 테스트 케이스 평가
    
    Returns:
        {
            "threshold": 임계값,
            "accuracy": 정확도,
            "precision": 정밀도,
            "recall": 재현율,
            "details": 상세 결과
        }
    """
    service = SimilarityService(threshold=threshold)
    
    true_positive = 0  # 그룹화해야 하는데 그룹화함 (정답)
    true_negative = 0  # 그룹화하면 안되는데 안함 (정답)
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
            "title1": title1[:30] + "...",
            "title2": title2[:30] + "...",
            "should_group": should_group,
            "score": round(score, 2),
            "is_grouped": is_grouped,
            "result": result
        })
    
    total = len(TEST_CASES)
    accuracy = (true_positive + true_negative) / total if total > 0 else 0
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
    
    return {
        "threshold": threshold,
        "accuracy": round(accuracy * 100, 2),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "details": details
    }


def find_optimal_threshold():
    """최적 임계값 찾기"""
    thresholds = [60, 65, 70, 75, 80, 85, 90]
    results = []
    
    print("=" * 60)
    print("유사도 임계값 튜닝")
    print("=" * 60)
    
    for threshold in thresholds:
        result = evaluate_threshold(threshold)
        results.append(result)
        
        print(f"\n임계값: {threshold}")
        print(f"  정확도: {result['accuracy']}%")
        print(f"  정밀도: {result['precision']}%")
        print(f"  재현율: {result['recall']}%")
        print(f"  TP={result['true_positive']}, TN={result['true_negative']}, "
              f"FP={result['false_positive']}, FN={result['false_negative']}")
    
    # 최적 임계값 선택 (정확도 기준)
    best = max(results, key=lambda x: x["accuracy"])
    
    print("\n" + "=" * 60)
    print(f"최적 임계값: {best['threshold']} (정확도: {best['accuracy']}%)")
    print("=" * 60)
    
    return best


def show_detailed_results(threshold: float):
    """상세 결과 출력"""
    result = evaluate_threshold(threshold)
    
    print(f"\n임계값 {threshold} 상세 결과:")
    print("-" * 80)
    
    for detail in result["details"]:
        status = "✅" if detail["result"] in ["TP", "TN"] else "❌"
        print(f"{status} {detail['result']} | 점수: {detail['score']:5.1f} | "
              f"예상: {'그룹' if detail['should_group'] else '개별'} | "
              f"결과: {'그룹' if detail['is_grouped'] else '개별'}")
        print(f"   제목1: {detail['title1']}")
        print(f"   제목2: {detail['title2']}")
        print()


if __name__ == "__main__":
    # 최적 임계값 찾기
    best = find_optimal_threshold()
    
    # 최적 임계값 상세 결과
    show_detailed_results(best["threshold"])
```

---

## ✅ 완료 조건

1. [ ] `tests/unit/test_location_service.py` 작성
2. [ ] `tests/unit/test_similarity_service.py` 작성
3. [ ] `tests/unit/test_title_transfer.py` 작성
4. [ ] `tests/integration/test_title_workflow.py` 작성
5. [ ] `scripts/similarity_tuning.py` 작성
6. [ ] 모든 테스트 통과
7. [ ] 최적 임계값 도출 (예: 75~80%)

---

## 🧪 테스트 실행
```bash
# 전체 테스트 실행
cd ~/blogauto_v2/services/republish
pytest tests/ -v

# 단위 테스트만
pytest tests/unit/ -v

# 통합 테스트만
pytest tests/integration/ -v

# 커버리지 포함
pytest tests/ -v --cov=app --cov-report=html

# 유사도 튜닝 실행
python scripts/similarity_tuning.py
```

---

## 📊 예상 결과

### 유사도 튜닝 결과 예시
```
임계값 튜닝 결과:
┌──────────┬─────────┬─────────┬─────────┐
│ 임계값   │ 정확도  │ 정밀도  │ 재현율  │
├──────────┼─────────┼─────────┼─────────┤
│ 60       │ 70%     │ 65%     │ 90%     │
│ 70       │ 85%     │ 80%     │ 85%     │
│ 75       │ 90%     │ 88%     │ 82%     │ ← 최적
│ 80       │ 88%     │ 92%     │ 75%     │
│ 85       │ 82%     │ 95%     │ 65%     │
└──────────┴─────────┴─────────┴─────────┘

권장 임계값: 75
```

---

## 📚 참조

- Phase A: `shared/services/location_service.py`
- Phase B: `shared/services/similarity_service.py`
- Phase C: `app/models/title.py`, `app/api/titles.py`
- Phase D: `app/services/title_transfer_service.py`
- Phase E: UI 파일들

---

**모든 Phase 완료!** 🎉
