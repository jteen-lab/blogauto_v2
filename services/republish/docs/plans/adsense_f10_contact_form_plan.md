# F10 — 문의 폼 자동 생성 작업계획서 (Google Forms 통합)

> **상태**: 설계 확정·구현 착수 전(사전 준비물 대기) · **확정일**: 2026-08-18 · **작성**: Claude
> **근거**: `docs/plans/adsense_approval_features_plan.md` F10, 순서도 `docs/flowcharts/adsense_f10_contact_form.md`

## 1. 배경 / 목적
- blogauto는 수백 개 블로그를 자동 관리한다. 필수 페이지·문의 페이지에 **동일한
  이메일**이 노출되면 "동일 운영자 묶음"으로 추정될 위험이 크다.
- 문의 폼으로 **이메일 노출을 없애고**, 운영자 수작업 없이 블로그별로 폼을 자동
  제공한다.

## 2. 확정 방향 (사용자, 2026-08-18)
- **블로거·워드프레스 통합 — 양 플랫폼 모두 Google Forms 임베드.**
- 근거: Google Forms 임베드는 iframe이라 양 플랫폼 공통 적용 가능. 범용
  `docs.google.com` 도메인이라 **공개 지문 없음**. 도메인 무구매·자체호스팅 없음·
  이메일 발송 인프라 불필요 → 구축/유지보수 최소.
- 검토 경위: 자체호스팅(공유 도메인 지문)·네이티브 블로거 가젯(API 자동화 불가)·
  WP 전용 플러그인(비통합)과 비교 후 통합 채택. 상세 대화 근거는 순서도 참조.

## 3. 아키텍처
- 블로그별 Google Form(이름·이메일·메시지)을 **Forms API**로 자동 생성(단일 계정 A).
- embed URL을 `contact_form_url`에 자동 채움 → 기존 `_contact_section`이 iframe+링크
  출력(WP iframe 제거 시 링크 폴백 내장). **템플릿 변경 불필요**(이미 폼 대응).
- `contact_form_id` 저장으로 멱등(재생성 방지).
- **인증(중요 정정)**: blogauto에 표준 OAuth authorize 흐름이 없음(블로거도 수동
  refresh token). 따라서 **계정 A의 Forms refresh token을 OAuth Playground에서 1회
  발급**받아 입력 → `system_settings`에 암호화 저장 → `google_oauth_helper.
  refresh_access_token`으로 access token 획득 → Forms API를 **httpx Bearer**로 호출
  (google-api-python-client 미도입, 코드베이스 관례 준수).
  - 스코프: `forms.body`(생성) + `forms.responses.readonly`(Phase 2 응답).
  - client_id/secret은 기존 Blogger OAuth(user_settings) 재사용.
  - 단일 계정 A라 수동 토큰 1회 입력으로 충분(전면 OAuth 흐름 구축 불요).

## 4. 단계 (Phase)
- **Phase 0 (사전 준비물, 운영자)**: §6.
- **Phase 1 (핵심)**: Forms API 클라이언트 + 프로비저닝(자동 생성·`contact_form_url`
  채움) + 문의 페이지 임베드 + **필수 페이지 mailto 제거**.
- **Phase 2 (후속)**: 통합 수신함 — `forms.responses.list` polling → DB 저장·UI.
  (초기엔 네이티브 수신: Google Forms 응답 탭.)

## 5. 영향 영역
- 신규: `services/publishing/google_forms_service.py`(폼 생성·URL 조립), 프로비저닝 훅.
- 수정: `required_pages_templates.py`(mailto 제거·링크 폴백 확인), 블로그 등록/설정 API,
  `google_credential` 스코프 처리.
- 데이터: `contact_form_id`(우선 `author_profile` JSONB, 필요 시 신규 컬럼+마이그레이션).

## 6. 사전 준비물 (운영자)
1. ✅ **GCP 프로젝트에 Google Forms API 활성화**(2026-08-18 완료).
2. ✅ **OAuth 동의 화면에 Forms 스코프 2종 등록**(2026-08-18 완료).
3. ✅ **게시 상태 프로덕션 확인**(테스트 사용자 불필요). 폼 전용 단일 계정 A 확정.
4. ⬜ **(코드 준비 후) OAuth Playground로 계정 A의 Forms refresh token 발급 → 입력.**
   - Playground에서 "Use your own OAuth credentials"에 blogauto의 client_id/secret 입력,
     계정 A로 forms 스코프 인증, refresh token 획득 → blogauto 설정에 붙여넣기.
> 4번은 blogauto에 입력 UI/저장이 구현된 뒤 진행(순서: 코드 → 토큰 입력 → 실호출 검증).

## 7. 리스크 / 한계
- Forms API 쿼터 → 대량 생성 throttling.
- 기존 블로거 자격 재동의 마찰(스코프 확대).
- 일부 WP(멀티사이트·보안 플러그인)에서 iframe 제거 → 링크 폴백으로 대응.
- WP 폼의 비공개 계정 연결(공개 미노출, 수용). 지배적 클러스터링 요인 아님.
- **정직**: 문의 폼은 "연락처" 벡터 한 가지만 개선. 애드센스 "동일 소유주" 판정의
  지배 요인(애드센스 계정·Search Console·서버 IP·콘텐츠 패턴)은 별도.

## 8. 미결정 (사용자 확인)
- 통합 수신함(Phase 2)을 언제 붙일지(초기 네이티브로 시작 권장).
- WP 폼용 구글 계정 로테이션 개수(1개 vs 2~3개).
- 착수 시점: 위 사전 준비물(§6) 완료 후.
