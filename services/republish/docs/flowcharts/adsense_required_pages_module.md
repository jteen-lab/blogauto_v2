# 애드센스 필수구성 모듈 순서도

문의폼 + 필수 4페이지를 한 모듈이 멱등 생성. 애드센스 탭 버튼은 제거(모듈 일원화).

```mermaid
flowchart TD
    A[플로우 실행: 애드센스 필수구성 모듈] --> B{연결 블로그 순회}
    B --> C[모듈 설정 로드]
    C --> C1[template_code / design_code<br/>generate_pages / pages_preset_code / pages_overrides]
    C1 --> D[RequiredPagesService.generate_all]

    D --> E[ensure_contact_form<br/>template+design 반영, 멱등]
    E --> F{generate_pages?}
    F -- false --> Z[문의폼만 보장하고 종료]
    F -- true --> G[build_required_pages<br/>preset_code + overrides]

    G --> H0{about 페이지 &<br/>author_profile.about_body 있음?}
    H0 -- 예 --> H1[블로그별 소개 본문 사용<br/>평문→HTML 변환·이스케이프<br/>문의 섹션 없으면 자동 추가]
    H0 -- 아니오 --> H[페이지별 body 결정<br/>override 있으면 사용, 없으면 프리셋 기본]
    H1 --> I
    H --> I[토큰 치환<br/>blog_name/url/operator/today/author/contact]
    I --> J{required_page_ids에 기존 id?}
    J -- 있음 --> K[플랫폼 update_page<br/>최신 내용 덮어쓰기]
    J -- 없음 --> L[플랫폼 create_page]
    K --> M[required_page_ids/status 갱신]
    L --> M
    M --> N[결과 집계]
    Z --> N
    N --> B
    B -- 완료 --> O[모듈 실행 결과 반환]
```

## 편집/프리셋 흐름 (UI)

```mermaid
flowchart LR
    P[모듈 편집 화면] --> Q[GET /settings/required-page-presets]
    Q --> R[프리셋 선택 드롭다운]
    R --> S[선택 프리셋 기본 body를<br/>4개 편집창에 프리필]
    S --> T{사용자 편집?}
    T -- 예 --> U[pages_overrides에 저장]
    T -- 아니오 --> V[override 없음<br/>= 프리셋 기본 사용]
    U --> W[모듈 settings 저장]
    V --> W
```

## 블로그별 소개 본문 (author_profile.about_body)

모듈 pages_overrides는 여러 블로그가 공유하므로, 블로그마다 다른 소개 본문은
블로그 설정 > 애드센스 탭 > 저자 프로필의 "소개 페이지 본문" 칸에 저장한다.

```mermaid
flowchart TD
    A[애드센스 탭 저자 프로필 저장] --> B[POST /settings/author-profile<br/>about_body 최대 5000자로 자름]
    B --> C[blog.author_profile.about_body]
    C --> D[필수 페이지 생성/갱신 실행]
    D --> E{about_body 비어있음?}
    E -- 예 --> F[overrides.about > 프리셋 기본]
    E -- 아니오 --> G{HTML 태그로 시작?}
    G -- 예 --> H[HTML 그대로 사용]
    G -- 아니오 --> I[평문 변환<br/>빈 줄=문단, '- '=목록, '## '=소제목<br/>HTML 이스케이프]
    H --> J{'{{contact}}' 포함?}
    I --> J
    J -- 아니오 --> K[h3 문의 + contact 블록 추가]
    J -- 예 --> L[토큰 치환 후 기존 페이지 id로 update]
    K --> L
```
