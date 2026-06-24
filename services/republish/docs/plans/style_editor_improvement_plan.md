# 블로그 스타일 편집기 개선 계획 (2026-06-24)

목표: CSS를 모르는 사용자도 Blogger/WordPress 양식을 정확히 구현하는 스타일 편집기.
배경 분석: 현재 스타일 탭은 선택자별 속성 편집 + 테이블 모드. 버튼 구조 불일치,
미리보기≠실제, 속성/hover/구조선택자 누락, 플랫폼 미인지, 편집 UX 불편.

## 우선순위(사용자 승인)
- **P1 버튼 구조 수정 + 미리보기 일치 (A·B)** ← 진행
  - 버튼 CSS를 `.button-link a`(래퍼 div 안 앵커) + 래퍼 `.button-link{display:block;margin-bottom}` 생성
  - 미리보기 샘플을 실제 발행 구조 `<div class="button-link"><a></div>` 로 교체
  - 영향: `style-tab-css-utils.js`(buildCssSelector/generateCssFromConfig/buttonWrapperSelector),
    `style-tab-presets.js`(SAMPLE_CONTENT), `style-tab.js`(fallback sample), `blogs/list.html`(?v= bump)
  - (후속 정리) 백엔드 `blog_settings_service.generate_css`도 동일 매핑(현재는 API 응답용·복사 비권위)
- **P2 누락 속성 + hover (C·D)**
  - text-align/text-decoration/text-shadow/text-transform/font-family/display/width/box-sizing/cursor/list-style
  - :hover 상태(버튼·링크) 편집
- **P3 테마 갤러리 + 요소별 쉬운 옵션 (제안1·2)**
  - 완성 테마 프리셋 + 메인컬러 1~2개로 일괄 변경, 요소별 시각 컨트롤(속성명 숨김)
- **P4 플랫폼별 출력 + 표 고급 (F·G, 제안4)**
  - Blogger(.post-body 접두)/WordPress 자동 변환, 둥근표(separate+overflow)·첫열너비 등

## 원칙
- 단계별 완성·검증·배포 후 다음 단계. 기존 동작 보존, 회귀 최소화.
- 미리보기는 실제 발행 HTML 구조와 1:1 일치 유지.
