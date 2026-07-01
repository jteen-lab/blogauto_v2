# 외부 CSS 붙여넣기 → 스타일 추출 (벤치마킹)

> 벤치마킹할 외부 블로그의 CSS를 붙여넣으면, 우리 스타일 모델(선택자·속성)에
> 맞게 추출해 style_config 초안을 만든다. 추출은 '시작점' — 미리보기·보정 후 저장.

## 순서도

```mermaid
flowchart TD
    A[스타일 탭: "CSS 붙여넣어 추출" 클릭] --> B[모달: CSS 텍스트 붙여넣기]
    B --> C[추출 클릭]
    C --> D[브라우저 CSS 파서로 파싱<br/>style media=not all → sheet.cssRules]
    D --> E[각 규칙의 subject 판별<br/>rightmost simple selector의 태그/hover]
    E --> F{지원 선택자?<br/>h1~h5,p,ul,ol,li,table,th,td,blockquote,a,a:hover}
    F -->|아니오| G[무시 규칙 카운트++]
    F -->|예| H[명시도 계산 + 선택자별 규칙 수집]
    H --> I[명시도·소스순서 정렬 후 병합<br/>지원 속성만 추출·정규화<br/>px는 숫자화, border 단축→분해]
    I --> J[styleConfig 초안 + 요약 리포트<br/>가져온 선택자/무시 규칙 수]
    J --> K[styleConfig에 병합 + 미리보기 갱신 + 요약 표시]
    K --> L[사용자 검토·보정]
    L --> M{저장?}
    M -->|예| N[POST /settings/style 저장 → 반영]
    M -->|아니오 / 탭 이동| O[미저장 폐기 → 초기화]
```

## 설계 원칙
- **브라우저 CSS 파서 사용**: `<style media="not all">`로 파싱만(페이지에 미적용) → `sheet.cssRules`.
  단축속성(margin/padding/border/font)은 CSSOM이 롱핸드로 확장해 안전 추출.
- **subject 매핑**: 규칙의 rightmost 심플 선택자에서 태그·hover 판별.
  콤마 분리 선택자 각각 처리. 'button' 힌트가 있는 a는 모호하므로 제외.
- **명시도 병합**: 선택자별로 명시도→소스순서로 정렬 후 좌→우 병합(더 구체적/나중 규칙 우선).
  → 보통 본문 스코프 규칙(.entry-content h1)이 전역 규칙(h1)보다 우선.
- **지원 속성만**: font/색/정렬/장식/여백/패딩/테두리(폭·스타일·색·반경)/list-style.
  flex/grid/의사요소/애니메이션 등은 무시. px 값은 숫자로 정규화.
- **본문 스코프는 재적용 안 함**: 태그별 '속성'만 추출. 스코프(.entry-content)는
  기존 치환자 css_classes로 자동 적용되므로 추출은 속성값에만 집중.
- **저장 필요**: 추출은 편집 상태만 갱신. 저장해야 반영(미저장 초기화 원칙).

## 대상 파일
- `app/static/js/blogs/style-tab-css-import.js` (신규) — 파싱/추출 순수 함수 + 믹스인
- `app/static/js/blogs/style-tab.js` — 믹스인 합성
- `app/templates/blogs/settings/_tab_style.html` — 버튼 + 모달
- `app/templates/blogs/list.html` — 신규 JS 로드
