# 붙여넣기 추출 — iframe computed(동적 샘플) 방식

> 선택자 파싱(우측 끝 태그+클래스 수집)으로 우리 구조에 맞춘 샘플 HTML을 짓고,
> 붙여넣은 CSS와 함께 숨긴 iframe에 렌더해 각 요소의 computed(최종 계산) 스타일을
> 읽어 추출한다. 캐스케이드·명시도·CSS변수·단축속성을 브라우저가 해결.
> 우리 자체 생성 CSS를 그대로 재현하는 것을 보장하며, 서버 불필요·단발성.

## 순서도

```mermaid
flowchart TD
    A[스타일 탭: CSS 붙여넣기 → 추출] --> B[CSS 파싱 rule/selector 수집<br/>&lt;style&gt;·주석 제거, @media 재귀]
    B --> C[선택자별 우측 끝 태그+클래스, 조상 클래스 수집]
    C --> D[동적 샘플 HTML 생성<br/>.entry-content 래퍼 + h1~h5·p·목록·표·인용·링크·버튼<br/>선택자에 나온 클래스를 해당 요소/조상에 부여]
    D --> E[iframe 2개 렌더<br/>styled: 샘플+붙여넣은 CSS / base: 샘플만]
    E --> F[각 요소 getComputedStyle<br/>styled vs base diff → 의도된 속성만]
    F --> G[지원 속성 추출·정규화<br/>px 숫자화, 테두리 사이드 통합(비활성 0)]
    G --> H[hover는 computed 불가 → 선택자 파싱으로 보완<br/>a:hover / a.button:hover]
    H --> I[styleConfig 병합 + 미리보기 갱신 + 요약]
    I --> J[사용자 검토·보정]
    J --> K{저장?}
    K -->|예| L[POST /settings/style]
    K -->|아니오/탭 이동| M[미저장 폐기]
```

## 설계 원칙
- **두 방식 결합**: ①선택자 파싱(우측 끝 태그+클래스)으로 샘플을 짓고, ②computed로 최종값을 읽음.
- **우리 CSS 보장**: 샘플이 `.entry-content h1`·`.button-link a` 구조라 우리 CSS가 그대로 적용→재현.
- **baseline diff**: CSS 없는 동일 샘플(base iframe)과 비교해 UA 기본값 노이즈 제거, 의도된 속성만.
- **테두리 사이드 통합**: computed의 면별 값을 활성 면 기준 generic style/color+면별 폭(비활성 0)으로.
- **hover 보완**: getComputedStyle은 hover 상태 불가 → :hover 규칙만 선택자 파싱으로 추출.
- **단발성**: 클릭 시 1회 iframe 렌더. 서버(Chromium) 불필요.
- **폴백**: iframe 실패 시 기존 선택자 파싱 추출로 폴백.
- **한계**: 우리 태그 집합에 없는 요소·JS로 입힌 스타일·클래스-only 선택자(태그 미상)는 제한.

## 대상 파일
- `app/static/js/blogs/style-tab-css-import.js` — buildSampleHtml, iframe computed 추출, extractAndApplyCss(async) 재구성
- `app/templates/blogs/list.html` — JS 캐시버전 bump
