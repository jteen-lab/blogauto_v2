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
    D --> E[page.evaluate: 본문 컨테이너 탐지<br/>.entry-content/.post-content/article/main...]
    E --> F[대상 태그별 대표 요소의 getComputedStyle 수집<br/>h1~h5,p,ul,ol,li,table,th,td,blockquote,a]
    F --> G[브라우저 종료 → 태그별 computed props 반환]
    G --> H[Python: 지원 속성 매핑·정규화·기본값 노이즈 제거<br/>px 숫자화, none/normal/transparent 스킵]
    H --> I[style_config + 리포트 반환]
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
