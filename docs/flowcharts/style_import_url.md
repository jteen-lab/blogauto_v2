# URL 자동 스타일 추출 (헤드리스 computed 스타일)

> 벤치마킹할 블로그 글 URL을 입력하면, 서버가 헤드리스 Chromium으로 렌더해
> 본문 요소의 computed(최종 계산) 스타일을 읽어 우리 style_config로 매핑한다.
> @media·CSS변수·캐스케이드가 이미 최종값이라 붙여넣기 방식보다 정확·일관.

## 순서도

```mermaid
flowchart TD
    A[스타일 탭: 'URL에서 추출' → URL 입력] --> B[POST /settings/style/extract-url]
    B --> C[백엔드: Playwright Chromium 실행<br/>--no-sandbox, headless]
    C --> D[page.goto(url) 렌더 대기]
    D --> D2[사이트 CSS 원문 수집<br/>인라인=cssText, 외부=Playwright 네트워크 fetch(CORS 우회)<br/>태그별 클래스 관례 파싱: table.foo/h2.bar + class-only]
    D2 --> E[page.evaluate: 본문 컨테이너 탐지<br/>.entry-content/티스토리/네이버/article/main...]
    E --> F[대상 태그별 대표 요소의 getComputedStyle 수집<br/>h1~h5,p,ul,ol,li,table,th,td,blockquote<br/>h1 본문에 없으면 문서 제목 h1 폴백<br/>링크는 배경 유무로 일반 a / 버튼 a.button 분리<br/>+ 4면 테두리 style/width/color + 본문 기준폰트]
    F --> F2[본문에 없는 지원 태그는 숨긴 샘플을 본문에 주입<br/>사이트 CSS 상속 상태로 computed 읽고 제거<br/>→ 글 내용과 무관하게 전 태그 추출]
    F2 --> G[브라우저 종료 → 태그별 computed props 반환]
    G --> H[Python: 지원 속성 매핑·정규화·기본값 노이즈 제거<br/>px 숫자화, none/normal/transparent 스킵]
    H --> H2[테두리 통합: 활성 면 기준 style/color 대표값<br/>+ 4면 폭 명시(비활성=0) → 단측 테두리 보존]
    H2 --> H3[list-style는 ul/ol에만, border-collapse는 collapse만<br/>→ computed 초기값 노이즈 제거]
    H3 --> I[style_config + 리포트 반환]
    I --> J[프런트: styleConfig 병합 + 미리보기 갱신 + 요약]
    J --> K[사용자 검토·보정]
    K --> L{저장?}
    L -->|예| M[POST /settings/style 저장 → 반영]
    L -->|아니오 / 탭 이동| N[미저장 폐기 → 초기화]
```

## 설계 원칙
- **헤드리스 computed 스타일**: 렌더된 최종값을 읽어 @media·변수·다중 시트 캐스케이드를 원천 해결.
- **본문 컨테이너 탐지**: 흔한 본문 셀렉터 우선순위로 탐지, 없으면 body 폴백. 본문 내 대표 요소 샘플링.
- **지원 속성만 + 노이즈 제거**: 글꼴/색/정렬/장식/여백/패딩/테두리/반경/list-style. none/normal/transparent/0-border/기본정렬 등 no-op은 제외.
- **단측 테두리 보존(붙여넣기 추출과 동일 로직)**: `border-top-*`만 읽으면 `border-left`만 있는 h3/h4의 테두리가 소실된다. 4면 style/width/color를 모두 읽어, 활성 면(style≠none & width>0) 기준으로 generic `border-style`/`border-color`를 잡고 4면 폭을 명시(비활성=0)해 한 면 테두리도 재현.
- **버튼형 링크 구분**: 배경색 유무 + 버튼 셀렉터(`.button-link a`/`a.button`/`.wp-block-button a` 등)로 판별해, 배경 있는 링크는 `a.button`, 없는 링크는 일반 `a`로 분리(본문 첫 링크가 버튼이어도 일반 링크 스타일이 오염되지 않게).
- **h1 폴백**: h1은 보통 글 제목이라 본문 컨테이너 밖. 본문에 없으면 문서 전체 h1을 대표값으로 사용(블로그 CSS의 h1 규칙은 제목 h1에도 적용되므로 유효).
- **font-family 노이즈 제거**: 요소 computed font-family가 본문 상속 기본값과 같으면 제외(링크 Arial처럼 의도적으로 다른 폰트만 남김).
- **태그별 관련 속성만**: `list-style`은 목록(ul/ol)에만, `border-collapse`는 `collapse`일 때만 반영(모든 태그 computed 초기값 `disc`/`separate` 노이즈 제거).
- **미사용 태그 보강(동적 샘플 주입)**: computed는 실물 요소가 있어야 측정 가능 → 글에 없는 태그는 추출 불가. 본문 실물 수집 후, 없는 지원 태그를 숨긴 샘플(off-screen·visibility:hidden)로 본문 컨테이너에 주입해 사이트 CSS를 상속받은 computed를 읽고 제거. 글 내용과 무관하게 전 지원 태그 추출.
- **클래스 관례 자동 학습(하드코딩 없음)**: 사이트가 `table.wp-block-table`·`h2.wp-block-heading`·`.se-text-paragraph`처럼 요소에 클래스를 달아 스타일을 걸면 맨 태그 주입은 미매치. → 페이지 CSS 원문(외부 CSS는 Playwright 네트워크로 받아 CORS 우회)에서 태그별 클래스를 파싱하고, class-only 선택자(`.wp-block-heading`)는 DOM에서 그 클래스를 가진 요소의 태그로 해석해, 주입 샘플 요소에 그 클래스를 입혀 class 기반 규칙까지 매칭. 사이트별 수동 등록 불필요. 잔여 한계: 스타일이 특정 클래스에만 걸렸는데 그 클래스가 문서 어디에도 안 쓰이면(class-only + 예시요소 부재) 태그 해석 불가.
- **온디맨드 실행**: 추출 클릭 시에만 Chromium 프로세스 기동→종료(상시 메모리 부담 없음).
- **저장 필요**: 추출은 편집 상태만 갱신. 저장해야 반영(미저장 초기화 원칙).
- **보안/견고성**: http(s) URL만 허용, 타임아웃, 실패 시 명확한 오류 반환.

## 대상 파일
- `services/republish/requirements.txt` — playwright 추가
- `services/republish/docker/Dockerfile` — chromium 설치(`playwright install --with-deps chromium`), PLAYWRIGHT_BROWSERS_PATH
- `app/services/style/style_url_extractor.py` (신규) — 렌더+추출+매핑
- `app/routers/blog_settings.py` — `POST /style/extract-url` 엔드포인트
- `app/static/js/blogs/style-tab-css-import.js` — URL 입력/호출/적용
- `app/templates/blogs/settings/_tab_style.html` — 모달에 URL 입력 추가
```
