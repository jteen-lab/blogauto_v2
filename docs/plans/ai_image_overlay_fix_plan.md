# AI 이미지 생성·폰트 오버레이 개편 계획서 (2026-06-12)

순서도: `docs/flowcharts/ai_image_overlay_flow.md`

## 승인된 요구사항
1. 블로그 image_mode(ai/both/template) 선택 시 모듈 이미지 생성 **자동 활성화**(수동 토글 제거).
2. AI 텍스트 할루시네이션 제거 → AI는 **텍스트 없는 배경**만 생성.
3. 한글 □ 해결 → 시스템 폰트 설치 대신 **블로그 이미지 탭에서 폰트 업로드(필수)** 사용.
4. 재조합 제목 오버레이 on/off가 결과에 정확히 반영.
5. 이미지 모델 dall-e 제거 → gpt-image-1.
6. 폰트/오버레이 설정 전 모드 공통.

## 구현 내역
### 백엔드
- `ai_image_service.py`: `NO_TEXT_GUARD` 상수 추가, 프롬프트 끝에 강제 append. 기본 프롬프트를 배경형(텍스트 비유발)으로 변경.
- `image_generator.py`: `_generate_ai_with_overlay`에서 `overlay_config.font_file` 없으면 시스템 폰트 폴백 대신 **명확 실패**(폰트 필수).

### 프런트엔드
- `blog_image_settings.js`: openai 모델 목록 = gpt-image-1만, 기본값 gpt-image-1. 저장 시 **폰트 미업로드면 차단**.
- `_tab_ai.html`: 이미지 provider 모델 목록 gpt-image-1.
- `_tab_image.html`: 폰트 업로드·오버레이 설정 **전 모드 공통**, 폰트 **필수(*)** 표기. 템플릿 이미지 업로드만 template/both.
- `prompt-form-template.js`: 모듈 이미지 "활성화" 토글 제거 → 섹션 항상 표시(자동 적용).
- `prompt-form.js`: imageGeneration.enabled 기본 true, 기본 프롬프트 배경형.

## 검증
- AI 생성 이미지에 텍스트 없는지 육안 확인(no-text 가드).
- 폰트 미설정 시 오버레이 명확 실패 확인.
- 폰트 업로드 후 오버레이 한글 정상 렌더(사용자 폰트로 검증).
- 모델 드롭다운에 dall-e 없음 확인.

## 비고
- 기존 인프라 `overlay_title_on_image`(TemplateImageService 폰트 렌더) 재사용.
- blog.overlay_config는 블로그당 1벌 → 폰트는 자연히 공통.
