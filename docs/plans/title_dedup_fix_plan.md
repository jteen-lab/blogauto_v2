# 제목 수집 중복 필터링 + 이동 시 중복 삭제 수정 계획

> 작성: 2026-06-10

## 문제

1. **수집 중복 필터링 결함(1차)**: 모든 TempTitle 저장 경로가 중복 체크 시
   **TempTitle 만 비교하고 MainTitle(정식제목)은 비교하지 않는다.** 그 결과
   정식제목과 완전히 같은 임시제목이 유입된다(서버 실측 87건).
   요구사항: "이미 수집된 제목과 중복이면 수집 안 함. 대상은 임시+정식 모두."

2. **이동 시 중복 처리**: 임시→정식 이동 시 동일 제목이 정식에 이미 있으면
   현재는 `status="duplicate"` 로만 바꾸고 임시제목을 **남긴다**. 요구사항은
   이동 조치한 임시제목을 **삭제**하는 것.

## 영향 경로 (TempTitle 저장)

| 경로 | 파일 | 기존 중복 체크 |
|------|------|----------------|
| 뉴스/웹문서 자동수집 | `keyword_collector_service._save_title` | TempTitle(lower)만 |
| bulk_collect 사이트맵 | `bulk_collect/chunk_processor._persist_temp_titles` | TempTitle(lower)만 |
| 수동 대량등록 API | `data_titles.create_temp_titles_bulk` | TempTitle(완전일치)만 |
| 엑셀 업로드 | `data_titles.upload_titles_excel` | TempTitle(완전일치)만 |

(bulk_title_collector 는 URL(CollectedUrl) 단계라 제목 저장 없음 — 제외)

## 수정

### A. 공통 중복 판정 유틸 신설 — `app/services/title_dedup.py`
- `title_exists(db, title) -> bool`: 임시 또는 정식에 존재(대소문자 무시), 단건용
- `existing_title_keys(db, titles) -> set[str]`: 배치용 정규화 키 집합
- 정규화: `strip().lower()` (기존 lower 비교와 일관, 완전일치 경로도 대소문자 무시로 통일)

### B. 4개 수집 경로에 적용
- 기존 "TempTitle 만 조회" → `title_exists`(임시+정식) 로 교체

### C. 이동 시 중복 → 임시제목 삭제 — `title_transfer_service.move_to_main`
- 사전 중복(`existing_titles`) 및 DB IntegrityError 중복 모두 **삭제 대상에 포함**
- `status="duplicate"` 잔존 로직 제거
- `result["duplicates"]` 카운트는 유지(응답·로그용)

## 검증 (로컬)
- 유틸 단위 검증: 임시/정식 각각 존재 시 중복 판정
- 이동 시 중복 제목이 임시에서 삭제되는지(로직) 확인
- 회귀: 정상(비중복) 수집·이동 경로 불변
