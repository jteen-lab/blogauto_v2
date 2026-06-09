# 내부링크 서론 매칭 개선 계획서

> 작성: 2026-06-09 | 순서도: `docs/flowcharts/internal_link_intro_matching.md`

## 1. 문제

서론 내부링크가 발행 포스트 수백 개인 블로그에서도 거의 달리지 않음.

**원인(점검 확정):**
- 서론은 `_find_similar_by_score(current_title, ...)` 로 **글 제목 전체 vs 포스트 제목 전체**
  유사도 ≥ 75% 인 것만 추출.
- 블로그 제목은 길고 고유 → 긴 제목 간 `token_sort_ratio`가 75%를 넘기 매우 어려움
  (시뮬레이션: 같은 주제 변형글 51.8점).
- 본론은 **짧은 섹션 제목**이라 긴 포스트 제목에 "포함 관계 보너스(85~95)"로 매칭됨 → 됨.
- 결론은 랜덤 → 항상 됨.
- 추가 악화: 운영 서버 **rapidfuzz 미설치 → difflib 폴백**(문자 단위)으로 점수가 더 낮음.

## 2. 해결 (승인된 방향)

### A. 서론 = 키워드 매칭 + fallback
- 현재 글 제목과 각 포스트 제목의 **공통 핵심 키워드 1개 이상**이면 후보, 겹침 많은 순 정렬.
- 부족분은 **최신 발행순 → 랜덤**으로 보충하여 `intro_count` 채움.
- 본론(섹션 유사도)·결론(랜덤)은 변경 없음.

### B. rapidfuzz 설치
- `requirements.txt`에 `rapidfuzz` 추가. `similarity_service.py`는 이미 자동 폴백 구조라
  코드 변경 불필요. 본론·서론·전체 제목 매칭 품질 동반 향상.

## 3. 변경 파일

| 파일 | 변경 |
|------|------|
| `app/services/generation/internal_linker.py` | 서론 단계 교체 + `_extract_keywords`, `_find_intro_posts` 추가 |
| `requirements.txt` | `rapidfuzz` 추가 |

- 무변경: SimilarityService, substitution_processor, UI/템플릿, 스키마, DB(마이그레이션 없음)

## 4. 구현 세부

- `_extract_keywords(text)`: `sim_service.normalize_text` → split → `len>1 and not in KOREAN_STOPWORDS`.
  KoNLPy 미사용(1GB RAM 부담 회피).
- `_find_intro_posts(current_title, posts, used_urls, count, sim_service)`:
  1. 타깃 키워드 추출, 각 포스트 공통 키워드 수 계산, ≥1 후보를 겹침 내림차순 정렬 → 상위 count
  2. count 미만이면 남은 포스트(중복 제외)를 `published_at` 내림차순(없으면 뒤) 보충 → 부족 시 그대로
- `insert_links` 서론 단계만 위 메서드 사용하도록 교체.

## 5. 검증 (로컬, 배포 보류)

- 유사도/키워드 매칭 시뮬레이션으로 서론 매칭 0건 → N건 전환 확인.
- 현실적 제목 세트로 키워드 매칭·fallback 동작 단위 확인.
- 기존 동작 회귀 없음 확인(본론/결론 경로 불변).

## 6. 배포 (보류 — 별도 승인 시)

- rapidfuzz 포함 이미지 재빌드 필요(GitHub Actions) → 데이터 보존 배포.
