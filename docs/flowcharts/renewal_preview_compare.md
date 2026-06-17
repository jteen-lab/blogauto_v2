# 리뉴얼 미리보기/비교 (#3, 설정용) (2026-06-17)

전체 설계 [[project-republish-renewal]]. 사용자 요구: 설정 시 리뉴얼 결과를
원본과 비교해 스타일을 튜닝. 수시가 아니라 설정 시에만 → 영구 저장 불필요.

## 동작
```mermaid
flowchart TD
    A[블로그 설정>재발행 탭: 리뉴얼 미리보기] --> B[POST /settings/renewal/preview]
    B --> C[가장 오래된 리뉴얼 가능 글 자동 선택]
    C --> D[RenewalService.renew_post dry_run=True include_content=True]
    D --> E[원본(라이브) vs 재생성 본문 반환]
    E --> F[모달: 좌=기존글 우=리뉴얼 결과 나란히 iframe 비교]
    F --> G[스타일은 그 블로그 생성 프롬프트 모듈로 튜닝 후 재미리보기]
```

## 핵심
- 비교는 **dry-run 기반**(라이브 글/DB 미변경). 생성 호출 발생(~수십 초).
- 생성 스타일 = **그 블로그에 연동된 생성(prompt) 모듈** 사용(현재 양식 일치).
  - 결정: FlowBlog→FlowModule→Module(type code "prompt"). 없으면 원본 생성
    모듈(GenerationHistory.prompt_module_id) 폴백. (향후 카테고리별 분기 여지)
- 영구 비교 저장 없음. 실제 리뉴얼은 적용 후 P4 유예기간 지나면 삭제(원본 보존 안 함).

## 변경
- `renewal_service`: _resolve_module(블로그 연동 생성 모듈 우선) + renew_post(include_content).
- `blog_settings_renewal`: POST /renewal/preview.
- `_tab_renewal.html`: 미리보기 버튼 + 원본↔리뉴얼 비교 모달.
- 스키마 변경 없음.
