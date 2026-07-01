# 치환값 블로그 간 복사 (다른 블로그에서 가져오기)

> 관리 중인 다른 블로그의 치환자 설정(placeholders)을 현재 블로그로 선택 복사.
> 파일 다운로드/업로드 없이 인앱으로 바로 적용. 저장해야 반영(미저장 시 초기화).

## 순서도

```mermaid
flowchart TD
    A[치환자 탭: "다른 블로그에서 가져오기" 클릭] --> B[GET /api/v1/blogs 목록 로드<br/>현재 블로그 제외]
    B --> C[모달: 소스 블로그 선택 + 복사 항목 체크박스<br/>CSS클래스/링크/텍스트/HTML태그]
    C --> D{소스 블로그 선택됨?}
    D -->|아니오| C
    D -->|가져오기 클릭| E[GET /blogs/&#123;sourceId&#125;/settings/placeholders]
    E --> F[체크된 항목만 현재 placeholders에 교체]
    F --> F1[css_classes 체크 → 교체]
    F --> F2[link_styles 체크 → 교체]
    F --> F3[text_replace 체크 → 교체]
    F --> F4[html_tags 체크 → 교체]
    F1 & F2 & F3 & F4 --> G[syncToRows: 편집 배열/미리보기 갱신]
    G --> H[사용자 검토]
    H --> I{저장 클릭?}
    I -->|예| J[POST /settings/placeholders 저장 → 반영]
    I -->|아니오 / 탭 이동| K[미저장 폐기 → 초기화<br/>blog-tab-changed 재로드]
```

## 설계 원칙
- **선택 복사**: 항목별 체크박스(기본 CSS클래스·링크 ON, 텍스트·HTML태그 OFF) — 블로그별로 다를 수 있는 텍스트/태그 치환은 기본 제외.
- **저장 필요**: 가져오기는 편집 상태만 갱신. 저장해야 서버 반영(기존 미저장-초기화 원칙 유지).
- **백엔드 변경 없음**: 기존 `GET /api/v1/blogs`(목록), `GET /settings/placeholders`(조회), `POST /settings/placeholders`(저장) 재사용.
- **현재 블로그 제외**: 소스 목록에서 자기 자신 제외.

## 대상 파일
- `app/static/js/blogs/replace-tab.js` — 상태/메서드(openImportModal, loadImportBlogs, importFromBlog)
- `app/templates/blogs/settings/_tab_replace.html` — 버튼 + 모달
