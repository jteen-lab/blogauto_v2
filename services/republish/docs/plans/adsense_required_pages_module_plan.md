# 애드센스 필수구성 모듈 통합 계획서 (필수페이지 모듈화)

> 작성 2026-08-20 | 상태: 구현 완료(1~3단계) · 배포 진행 | 관련 [[adsense_contact_form_module_plan]]

## 1. 배경 / 문제

- 현재 **문의폼 생성 경로가 두 곳**이다.
  1. 블로그 설정 → 애드센스 탭 `필수 페이지 4종 생성` 버튼 →
     `RequiredPagesService.generate_all()` → 4페이지 생성 + 내부 `ensure_contact_form()`.
  2. 새 `contact_form` 모듈 → Tally 문의폼만 생성(페이지 없음).
- 결과: 애드센스 탭 버튼이 페이지+문의폼을 다 만들어 **모듈이 반쪽**으로 보인다.

## 2. 결정 (사용자 확정 2026-08-20)

1. **애드센스 탭의 필수페이지 생성/삭제 버튼 제거 → 모듈로 일원화.**
2. **`contact_form` 모듈을 '애드센스 필수구성'으로 확장**(코드값 `contact_form` 유지,
   표시명·아이콘만 변경). 문의폼 + 필수 4페이지를 한 모듈이 생성.
3. **필수페이지 문체 프리셋 몇 종 선택 + 페이지별 본문 직접 편집** 지원.

## 3. 설계

### 3.1 페이지 프리셋 + 편집 모델 (토큰 기반)
- `required_pages_templates.py`를 프리셋 구조로 리팩터링.
- 프리셋 3종: `standard`(표준·공식체), `friendly`(친근체), `concise`(간결체).
- 각 프리셋 = `{code, name, description, pages: {privacy|terms|about|contact: {title, body}}}`.
  `body`는 **토큰 HTML**: `{{blog_name}} {{blog_url}} {{operator}} {{today}}
  {{author_bio}} {{author_expertise}} {{contact}}`.
  `{{contact}}` → 문의 폼 임베드(있으면) 또는 mailto(폴백).
- 편집: 모듈 UI가 선택 프리셋의 기본 body를 4개 편집창에 로드 → 사용자가 수정 시
  `pages_overrides[page_type]`에 저장. 생성 시 override 있으면 그걸, 없으면 프리셋 기본.
- 토큰 치환은 순수 함수(`render_page_body`). 사용자 편집 본문도 동일 치환 → 변수 유지.

### 3.2 서비스
- `build_required_pages(blog, owner_email, preset_code=None, overrides=None)`.
- `RequiredPagesService.generate_all(blog, owner_email, *, preset_code=None,
  overrides=None, contact_template=None, contact_design=None)` — 내부에서
  `ensure_contact_form(template, design)` 1회 호출 후 4페이지 생성(문의폼 중복 방지).

### 3.3 모듈 설정(JSONB) 스키마 확장
```
{
  template_code,        # 문의폼 필드 템플릿
  design_code,          # 문의폼 디자인 프리셋
  generate_pages: bool, # 필수 4페이지 생성 여부(기본 true)
  pages_preset_code,    # 페이지 문체 프리셋
  pages_overrides: { privacy, terms, about, contact }  # 사용자 편집 본문(선택)
}
```

### 3.4 디스패치
- `flows_execute.py` contact_form 분기 + `flow_scheduler._execute_contact_form_module`:
  블로그마다 `generate_all(...)` 호출(문의폼+페이지 멱등). `generate_pages=false`면
  기존처럼 `ensure_contact_form`만.

### 3.5 모듈 타입 리네임
- `get_default_types`: contact_form name "문의폼"→"애드센스 필수구성", icon 📨→📋.
- `main.seed_module_types`: 기존 행의 name/icon/display_order **동기화**(현재는 누락 코드만
  add). 배포 시 자동 리네임.
- `flows/form.js` getModuleTypeName/Icon도 "애드센스 필수구성"/📋로.

### 3.6 애드센스 탭 정리
- `_tab_adsense.html`: 필수페이지 `생성/갱신`·`삭제` 버튼 + generating/deleting JS 제거.
- 상태 readout(F9 준비도 요약의 '필수 페이지 O/X')는 유지(모듈 실행이 상태 갱신).
- 안내 문구: "필수 페이지는 '애드센스 필수구성' 모듈로 생성합니다".
- 백엔드 `POST/DELETE /required-pages*`는 즉시 삭제하지 않고 **유지**.
- **삭제 버튼은 유지(2026-08-20 사용자 요청)** — 생성만 모듈로 일원화하고, 모듈로
  만든 페이지를 되돌릴 경로가 필요하므로 탭의 `필수 페이지 삭제`는 남긴다.
  삭제 시 원격 4종 삭제 + `required_page_ids` 초기화 → 모듈 재실행하면 신규 생성.

## 4. UI
- 신규 `contact-form-pages.js`: 필수페이지 섹션 템플릿(토글 + 프리셋 선택 + 4 편집창).
  `getContactFormModuleFormTemplate()`가 이어붙여 렌더.
- `form.js`: `generate_pages/pages_preset_code/pages_overrides` 상태·직렬화·프리셋 로드.
- `GET /settings/required-page-presets`: 프리셋 목록 + 페이지별 기본 body(편집창 프리필용).
- `list.html` ?v= bump.

## 5. 단계
1. ✅ 백엔드: 프리셋/템플릿 리팩터 + 서비스 시그니처 + 디스패치 + 리네임/시드 동기화 + 프리셋 API.
   (9e02d0d, e1817d5, cc9bcde, b27057a)
2. ✅ 프론트: 모듈 페이지 섹션 UI + form.js 배선 + 애드센스 탭 버튼 제거 + ?v=.
   (326820c, 24e10e2, 3118d31) — 모듈 목록/선택기 라벨·아이콘도 함께 통일.
3. ✅ 로컬 검증: 프리셋 3종 렌더(잔여 토큰 0) · override 치환 · 문의폼 iframe 임베드 ·
   list_presets 구조 · py/js 문법 · 라우터 import 스모크.
4. 🔄 배포: push(3118d31)→빌드→서버 데이터 보존 배포→SHA 3값 일치 확인.

### 구현 시 계획과 달라진 점
- 토큰명: 계획의 `{{author_bio}}/{{author_expertise}}`는 단일 `{{author_block}}`로 통합
  (bio/expertise 유무에 따라 소개 블록 전체를 렌더 — 빈 값일 때 빈 제목이 남지 않게).
- 구 템플릿의 블로그별 문구 변주(`_variant_index`)는 제거. 대신 프리셋 3종 선택 +
  페이지별 직접 편집이 그 역할을 대신한다(동일 문구 노출을 사용자가 통제).
- 애드센스 탭의 미사용 `generatePages/deletePages` JS도 함께 제거(버튼만 지우면 사장 코드).

### 갱신(재실행) 동작 — 2026-08-20 검증
모듈 설정을 바꾼 뒤 재실행하면 **기존 페이지를 덮어쓴다**(중복 생성 없음).
- 페이지: `required_page_ids`에 id가 있으면 `_update_one`(Blogger PUT / WP POST)로 갱신.
  시뮬레이션 결과 2회차 실행에서 update 4 / create 0, 프리셋 변경(standard→friendly)
  문구·override 본문·새 문의폼 URL이 모두 반영됨.
- 문의폼: `ensure_contact_form`이 (title/fields/styles) 해시 비교 → 변경 시 Tally PATCH,
  동일하면 no-op. 모듈의 template_code/design_code 변경이 그대로 전달된다.
- 보완: WP 갱신이 404(원격에서 페이지 삭제됨)면 재생성으로 폴백(553cc0c).
  Blogger는 퍼블리셔가 이미 동일 폴백 보유.
- 보완: 페이지 생성 토글을 꺼도 편집본(override)을 보존(02d951d).

## 6. 리스크
- 페이지 멱등: `required_page_ids`로 기존 페이지 update, 신규만 create(기존 로직 유지).
- 문의폼 중복 방지: 페이지 서비스가 form 생성을 소유(모듈 디스패치는 generate_all만 호출).
- 리네임 시드 동기화가 다른 필드 덮어쓰지 않도록 name/icon/display_order만 갱신.
- 사용자 편집 본문의 안전성: 토큰 치환만, 스크립트 삽입은 사용자 책임(운영자 전용 UI).
