# 문의 수신함(대시보드) 작업계획서 (F10 Phase 2)

> **상태**: 구현 완료·배포(폴링 방식, 2026-08-18) · **작성일**: 2026-08-18 · **작성**: Claude
> ⚠️ blogauto가 바레IP/HTTP라 webhook 인바운드 부적합 → **폴링(동기화 버튼)** 채택.
> contact_submissions(mig 049) + /contact-inbox 페이지 + sync API. webhook은 HTTPS
> 도메인 확보 후 후속. 실동기화 검증 완료.
> **근거**: `docs/plans/adsense_f10_contact_form_plan.md` Phase 2, 사용자 확정
> (2026-08-18): Tally 대시보드가 아닌 **blogauto 대시보드에서 문의 확인**.
> 문의폼 커스텀 모듈(`adsense_contact_form_module_plan.md`)과 **함께 진행**.

## 1. 배경 / 목적
- 현재 문의 제출은 Tally 대시보드(https://tally.so/dashboard)에서만 확인 가능.
- 수백 블로그 운영 시 **blogauto 한 화면에서 통합 확인**이 필요.
- 폼이 모듈별로 다르므로(가변 필드) 수신함은 **가변 필드 표시** 대응.

## 2. 수집 방식 — Webhook(권장) + 폴링(백필/폴백)
- **Webhook(push, 실시간·저부하·권장)**: Tally webhook(무료·무제한)이 새 제출을
  blogauto 공개 엔드포인트로 POST → 저장. 폴링 불필요.
- **폴링/백필(pull)**: `GET /forms/{formId}/submissions`로 기존/누락 제출 수집
  (rate limit 100/분 → throttling). 초기 백필·webhook 유실 보완용.

## 3. 데이터
- 신규 테이블 **`contact_submissions`**(마이그레이션 동반):
  ```
  id, blog_id(FK), form_id, submission_id(UNIQUE),
  submitted_at, payload(JSONB, 필드값 원본), is_read(bool), created_at
  ```
  - `submission_id` UNIQUE로 **중복 저장 방지**(webhook·폴링 이중 수집 대비).
  - `payload`에 Tally 제출 원본(필드 라벨→값) 저장 → 가변 필드 표시 대응.
- 블로그 연결: `form_id`(→ author_profile.contact_form_id) 또는 blog_id 매핑.

## 4. 컴포넌트
- **Webhook 수신 라우터** `POST /api/v1/tally/webhook`(공개):
  - **서명 검증**(Tally webhook signing secret) → 위조 차단.
  - payload에서 form_id·submission_id·필드값 파싱 → `contact_submissions` upsert.
  - blog 매핑(form_id → blog).
- **Webhook 등록**: 폼 생성 시(contact_form 모듈 실행) Tally webhook 등록
  (폼별 또는 워크스페이스 단위 — Tally API 확인 후 결정). 실패 시 폴링으로 폴백.
- **폴링/백필 서비스**: `GET /forms/{id}/submissions` 순회 저장(스케줄 or 수동 버튼).
- **대시보드 UI**: 문의 수신함
  - 목록: 블로그별 필터 + 통합 보기, 미읽음 뱃지, 제출일 정렬.
  - 상세: 가변 필드(payload) 표시, 읽음 처리.
  - 위치: 대시보드에 "문의" 섹션/탭 신규.

## 5. 실행 통합 지점
- 라우터 등록: `app/main.py` include_router(신규 tally_webhook_router).
- 저장 서비스: `app/services/publishing/` 또는 신규 `contact_inbox_service.py`.
- 폼 생성 시 webhook 등록: `tally_forms_service.create_contact_form` 확장(webhook API).
- UI: `app/templates/dashboard.html` + 신규 JS, 조회 API `/api/v1/contact-submissions`.

## 6. 단계 (Phase)
1. **P1 저장·수집**: `contact_submissions` 모델+마이그레이션 + webhook 수신 라우터
   (서명검증·upsert) + 폼 생성 시 webhook 등록 + 폴링/백필 서비스.
2. **P2 대시보드 UI**: 조회 API + 수신함 목록/상세/읽음 + 가변 필드 표시.
3. **P3 검증**: webhook 서명·중복 upsert 단위테스트 + 서버 실호출(제출→수신 확인).

## 7. 리스크 / 고려
- **공개 엔드포인트 보안**: 서명 검증 필수(무검증 시 스팸/위조 저장). rate limit 권장.
- **Tally webhook 스키마**: 실제 payload 형식은 서버 실측(로그)으로 확인 후 파서 확정.
- **가변 필드**: 모듈별 폼이 달라 payload 필드가 다름 → UI는 key-value 범용 렌더.
- **유실 대비**: webhook 단독 의존 금지 → 폴링 백필 병행(submission_id로 dedupe).
- 마이그레이션 동반([[feedback_local_migration_first]] — 로컬 먼저 검증).

## 8. 미결정 (사용자 확인)
- 수집: **webhook 우선 + 폴링 백필**(권장) vs 폴링만(단순)?
- 수신함 위치: 대시보드 탭 vs 별도 메뉴?
- 알림: blogauto 화면 미읽음 뱃지만 vs 추가 알림(후속).

> 연계: 폼 커스텀 모듈 `docs/plans/adsense_contact_form_module_plan.md`와 함께 착수.
