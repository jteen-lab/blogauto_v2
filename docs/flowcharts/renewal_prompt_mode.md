# 리뉴얼 프롬프트 모드 + 미리보기 생성모듈 이전 (a,b) (2026-06-17)

[[project-republish-renewal]]. 사용자 요구: 리뉴얼은 생성 모듈 프롬프트를 쓰되,
재발행용 별도 지침을 넣을 수 있어야 하고(특히 기존 정보 보존+확장), 미리보기는
생성 모듈 안에 있어야 함(재발행은 별도 모듈 없음).

## (a) 프롬프트 모드 + 기존 글 주입
```mermaid
flowchart TD
    A[리뉴얼 생성] --> B{renewal_prompt.mode}
    B -->|inherit 승계| C[생성 프롬프트 그대로 (기존 글 미주입)]
    B -->|new 새| D[text를 프롬프트로 교체 + {existing_content} 제공]
    B -->|additional 추가| E[생성 프롬프트 + text 결합 + 기존 글 본문 주입]
    E --> F[정보 보존하며 최신 내용 확장]
```
- `Module.settings.content_generation.renewal_prompt = {mode, text}`.
- `generate_content_with_meta(prompt_override, extra_instruction, existing_content)` 옵션(하위호환).
- 기존 글 = RenewalSource가 가져온 라이브 본문(HTML 제거+8000자 상한).
- inherit=현재 동작 그대로.

## (b) 위치
- 프롬프트 설정: 생성 모듈 프롬프트 폼 "글 생성 프롬프트" 섹션에 모드 select+text.
- 미리보기: **생성 모듈 테스트 패널**에 "리뉴얼 미리보기" 버튼+비교 모달(선택 블로그 가장
  오래된 글로 dry-run, 원본 vs 리뉴얼 좌우 비교). 저장 후 실행(저장본 설정 반영).
- 블로그 설정 재발행 탭의 미리보기는 제거(주기/제목모드/유예 설정만 유지).

## 비변경
- 스키마 변경 없음(settings JSON 키 + 코드/UI). 리뉴얼은 여전히 스케줄러 미연결(다음 단계 c,d).
