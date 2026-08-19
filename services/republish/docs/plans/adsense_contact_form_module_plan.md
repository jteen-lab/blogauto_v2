# 문의폼 커스텀 모듈 작업계획서 (F10 확장)

> **상태**: 설계 확정, 구현 착수 전 · **작성일**: 2026-08-18 · **작성**: Claude
> **근거**: `docs/plans/adsense_f10_contact_form_plan.md`(F10 Tally 통합), 사용자 확정
> (2026-08-18): 블로그별 문의폼을 **모듈로 획일화**하되 **멱등** 실행으로 기존
> 워크플로우(모듈→플로우→수동/오토런)를 그대로 재사용.

## 1. 배경 / 목적
- 현재 문의폼은 **고정 3필드**(이름·이메일·문의내용)로 블로그마다 동일. 블로그별로
  다른 폼(연락처·문의유형 등)을 적용하려면 블로그마다 수작업은 비현실적(수백 개).
- **재사용 가능한 폼 구성(모듈)** 몇 개를 만들어 **다수 블로그에 일괄 적용**한다.
- 폼 생성은 1회성이지만, **멱등 실행**(이미 있으면 스킵/변경시 수정)으로 만들어
  별도 1회성 시스템 없이 기존 모듈 실행 흐름에 자연스럽게 편입한다.

## 2. 핵심 설계 — 멱등 `contact_form` 모듈
- **신규 모듈 타입 `contact_form`**: 모듈 = 문의폼 필드 구성 템플릿.
- **모듈 실행(링크된 블로그마다)**:
  1. 폼 없음 → Tally 폼 **생성**(create).
  2. 폼 있음 + 구성 변경(해시 불일치) → Tally **PATCH** `/forms/{id}`로 필드 수정.
  3. 폼 있음 + 구성 동일 → **no-op**(Tally 호출 없음, 즉시 스킵).
- → 수동 1회 실행이면 그때 세팅되고, 오토런에 있어도 2회차부터 전부 스킵(무해·저부하).

## 3. 데이터 / 설정
- `ModuleType.get_default_types()`에 `contact_form` 추가(code/name/icon).
- **Module.settings**(JSONB) 스키마:
  ```
  {
    "title_template": "{blog} 문의",        // 폼 제목(블로그명 치환)
    "fields": [
      {"label":"이름","type":"INPUT_TEXT","required":true},
      {"label":"이메일","type":"INPUT_EMAIL","required":true},
      {"label":"문의 유형","type":"DROPDOWN","required":false,
       "options":["광고","제휴","기타"]},
      {"label":"문의 내용","type":"TEXTAREA","required":true}
    ],
    "blogs": [...],                          // 대상 블로그(기존 링크 재사용)
    "blog_category_map": [...]               // 필요 시
  }
  ```
- **블로그별 상태**(author_profile JSONB, 기존 재사용): `contact_form_id`,
  `contact_form_url`, **`contact_form_config_hash`**(변경 감지용, 신규).
- 지원 필드 타입(Tally 블록 매핑): INPUT_TEXT / INPUT_EMAIL / INPUT_NUMBER /
  INPUT_LINK / TEXTAREA / DROPDOWN / MULTIPLE_CHOICE / CHECKBOXES.

## 4. 실행 통합 지점
- **플로우 타입별 디스패치**: `app/routers/flows_execute.py`(모듈 type_code별 처리,
  현재 growth_profile/prompt/generate 분기 `:1958`,`:1962`)에 **`contact_form` 분기 추가**
  → 링크 블로그마다 `ensure_contact_form(blog, module_settings)` 멱등 실행.
  (오토런 경로 `flow_scheduler.py`도 동일 엔진을 타므로 자동 포함.)
- **서비스 재사용/확장**: `tally_forms_service.build_contact_blocks(title)` →
  `build_blocks_from_fields(title, fields)`로 일반화(필드 config → Tally 블록).
  폼 수정용 `update_contact_form(api_key, form_id, ...)`(PATCH) 신규.
- **provisioner**: `ensure_contact_form`이 모듈 config를 받아 생성/PATCH/스킵 판정
  (config_hash 비교). 배정 모듈 없으면 **기본 3필드로 폴백**(현행 유지).
- **F1 필수페이지 훅**: 기존 `required_pages_service` 훅은 유지하되, 블로그에 배정된
  contact_form 모듈 config를 우선 사용(없으면 기본).

## 5. UI
- 신규 폼 템플릿 JS `contact-form-module-template.js`: **필드 편집기**(행 추가/삭제,
  타입 드롭다운, 필수 토글, DROPDOWN/CHOICE는 옵션 입력) + 대상 블로그 연동(기존
  prompt 모듈 연동 UI 재사용).
- `app/static/js/modules/list.js` `getFullFormTemplate()`에 `contact_form` 분기 추가
  (현재 prompt/generate/growth_profile 분기 패턴, `:1048~1057`).
- `templates/modules/list.html` `?v=` bump.

## 6. 단계 (Phase)
1. **P1 백엔드**: ModuleType 시드 + `build_blocks_from_fields` + `update_contact_form`
   (PATCH) + provisioner config/해시 판정 + flows_execute `contact_form` 디스패치.
2. **P2 프론트**: 필드 편집기 UI + list.js 배선 + ?v=.
3. **P3 검증**: 단위테스트(블록 생성·해시 판정) + 서버 실호출 검증(생성/PATCH/스킵).

## 7. 리스크 / 고려
- 필드 타입별 Tally 블록 스키마(옵션형 DROPDOWN 등)는 **서버 실호출로 실측 검증**
  (F10에서 groupType 등 스키마 함정 경험 → 동일 방식으로 확인).
- PATCH 시 "전체 블록 포함" 규칙(Tally는 업데이트 시 모든 블록 전송 요구) 준수.
- 멱등 판정용 config_hash에 title_template·fields·옵션까지 포함.
- 오토런 편입 시 저부하 유지(해시 동일 → Tally 호출 0).

## 8. 미결정 (사용자 확인)
- 기본 제공 템플릿 종류·필드(예: 기본/연락처/문의유형 3종)?
- 폼 구성 변경 시 **PATCH 수정**(권장) vs 재생성?
- 대상 연동을 prompt 모듈과 동일하게 blogs/카테고리로 할지.

> 연계: 문의 수신 확인은 `docs/plans/adsense_inquiry_dashboard_plan.md` 참조(함께 진행).

## 9. 디자인 프리셋 축 추가 (2026-08-19, A안 완료)

필드 템플릿과 **독립된 디자인 축**(A안)을 추가. 같은 필드에 색/테마만 바꾸는
자유 조합이 가능하다. 디자인은 Tally `settings.styles`로 전달(DARK·CUSTOM 실호출
201 검증). 모듈 설정은 `{template_code, design_code}` 두 값을 저장한다.

- `app/services/publishing/contact_form_designs.py`(신규): 6종 프리셋
  (default/dark/brand_blue/brand_green/warm_orange/minimal_mono). `default`는
  styles=None → Tally 기본 외형(기존 폼 config_hash 불변 → 불필요 PATCH 없음).
- `tally_forms_service.py`: create/update에 `styles` 인자, `config_hash(...,styles)`.
- `contact_form_provisioner.py`: `ensure_contact_form(..., design=None)`.
- 디스패치(flows_execute/flow_scheduler): `settings.design_code` → `get_design`.
- `GET /settings/contact-form-designs` + UI 디자인 드롭다운(form.js/contact-form-template.js).
- 배포: f2edddb.
