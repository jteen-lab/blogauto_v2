# AI 이미지 생성 + 폰트 오버레이 흐름 (2026-06-12 개편)

## 배경
- AI(gpt-image-1)가 프롬프트의 제목을 이미지에 직접 렌더 → 한글 깨짐·할루시네이션(가짜 전화번호 등).
- 오버레이 한글이 □(tofu): 시스템 한글 폰트 미설치 + 커스텀 폰트 미업로드.
- 모듈 "이미지 생성 활성화"를 꺼도 blog.image_mode가 설정돼 있으면 생성됨(혼란).

## 개편 원칙
1. AI는 **텍스트 없는 배경**만 생성한다.
2. 제목은 **블로그에 업로드한 폰트로 오버레이**한다(폰트 필수).
3. 이미지 생성 여부는 **blog.image_mode**가 결정(모듈 토글 제거 → 자동 활성).

## 생성 파이프라인

```mermaid
flowchart TD
    A[글 생성: working_title = 재조합 제목] --> B{blog.image_mode}
    B -->|none/미설정| Z[이미지 생성 안 함]
    B -->|template| T[템플릿 이미지 + 폰트 오버레이]
    B -->|ai| C[AI 배경 생성]
    B -->|both| C

    C --> D[프롬프트 빌드]
    D --> D1["제목 텍스트 제거<br/>+ no-text 가드 강제<br/>(no text/letters/words/numbers)"]
    D1 --> E[gpt-image-1 호출 → 텍스트 없는 배경 b64]
    E --> F{title_overlay?}
    F -->|OFF| G[배경 그대로 반환<br/>제목 없음]
    F -->|ON| H{blog.overlay_config.font_file 존재?}
    H -->|없음| H1[명확 실패: 폰트 필수 안내]
    H -->|있음| I[업로드 폰트로 재조합 제목 오버레이<br/>overlay_title_on_image]
    I --> J[최종 이미지 반환]

    T --> J
```

## 폰트 필수 검증 흐름

```mermaid
flowchart TD
    S[블로그 이미지 탭 저장] --> S1{폰트 파일 업로드됨?}
    S1 -->|아니오| S2[저장 차단 + 안내: 폰트 파일은 필수]
    S1 -->|예| S3[overlay_config.font_file 저장]
    S3 --> S4[template/ai/both 공통 적용]
```

## 변경 요약
| 영역 | 변경 |
|------|------|
| ai_image_service | 프롬프트에 no-text 가드 강제, 제목 텍스트 미포함 |
| image_generator | title_overlay ON + 폰트 있을 때만 오버레이, 폰트 없으면 명확 실패 |
| 기본 프롬프트 | 텍스트 비유발형(배경 묘사)로 변경 |
| _tab_image.html | 폰트/오버레이 섹션 전 모드 공통, 폰트 필수, 모델 목록 정리 |
| blog_image_settings.js | 모델 목록(gpt-image), 폰트 필수 검증 |
| 모듈 폼 | 이미지 생성 "활성화" 토글 제거(자동), 오버레이 토글 유지 |
| _tab_ai.html | 이미지 모델 목록 정리 |
