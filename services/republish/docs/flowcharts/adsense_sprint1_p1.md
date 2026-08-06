# 애드센스 승인 지원 — Sprint 1 (P1: F1~F3) 순서도

> 근거 계획서: `docs/plans/adsense_approval_features_plan.md` §3 Phase 1
> 착수 전 필수 작성(CLAUDE.md 규칙 4). 코드 착수는 별도 세션에서 본 문서 기준으로 진행.

## F1. 필수 페이지 4종 자동 생성

```mermaid
flowchart TD
    A[블로그 등록/설정 저장] --> B{필수 페이지\n이미 발행됨?}
    B -- 예 --> Z[스킵]
    B -- 아니오 --> C[페이지 템플릿 로드\n개인정보처리방침/이용약관/소개/문의]
    C --> D[변수 치환\n블로그명·도메인·운영자·연락처]
    D --> E{플랫폼}
    E -- Blogger --> F1[Pages API pages.insert]
    E -- WordPress --> F2[REST wp/v2/pages]
    F1 --> G[생성된 page id 저장]
    F2 --> G
    G --> H[플랫폼별 메뉴/위젯에 링크 노출]
    H --> I[Blog.required_pages_status = complete]
```

## F2. 저자성(E-E-A-T) 신호 주입

```mermaid
flowchart TD
    A[블로그 설정: author_profile\n이름/소개/전문분야 입력] --> B[저장]
    B --> C{저자 소개 페이지\n존재?}
    C -- 아니오 --> D[F1 파이프라인 재사용\n저자소개 페이지 발행]
    C -- 예 --> E
    D --> E[글 생성 파이프라인]
    E --> F[본문 조립 시\n글 상단/하단 바이라인 주입]
    F --> G[템플릿 푸터에\n편집감독 문구 주입]
    G --> H[발행]
```

## F3. 카테고리/내비게이션 메뉴 자동 구성

```mermaid
flowchart TD
    A[블로그 카테고리 목록 변경 감지] --> B[활성 카테고리 집계]
    B --> C{플랫폼}
    C -- Blogger --> D1[HTML 위젯/링크 리스트\ntemplate PATCH]
    C -- WordPress --> D2[wp/v2/menus + menu-items\n또는 nav 위젯 REST]
    D1 --> E[메뉴 항목 = 카테고리\n월별 아카이브 대체/병행]
    D2 --> E
```

## 데이터 모델 변경 (F1~F3 공통)

- `Blog.author_profile` (JSON: name, bio, expertise) — nullable
- `Blog.required_pages_status` (enum: none/partial/complete)
- `Blog.required_page_ids` (JSON: {privacy, terms, about, contact} → 플랫폼 page id)
- 마이그레이션: 로컬 alembic upgrade 먼저 검증 후 배포 ([[feedback_local_migration_first]])

## 영향 파일 (예상, 500줄/50줄 규칙 준수 위해 신규 파일 분리 권장)

- `app/models/blog.py` — 컬럼 3종 추가
- `app/services/publish/blogger_adapter.py`, `app/services/publish/wordpress_adapter.py` (또는 실제 경로) — 페이지 생성 메서드 추가
- `app/services/publish/required_pages_templates.py` (신규) — 4종 템플릿
- `app/services/generation/...` — 바이라인/편집감독 문구 주입 지점
- `alembic/versions/xxxx_add_blog_adsense_p1_fields.py` (신규)

## 미해결 설계 질문 (착수 세션에서 확정)

1. Blogger Pages API 인증 스코프가 기존 google_credential으로 충분한지 확인 필요.
2. WordPress 사이트 중 REST pages 엔드포인트가 막힌 곳(플러그인 mu-plugin 필요, [[project_wordpress_seo_autoinput]] 유사 케이스) 존재 가능 — 사전 조사 필요.
3. 기존 블로그(운영 중) 소급 적용 범위 — 신규 등록만 vs 전체 백필.
