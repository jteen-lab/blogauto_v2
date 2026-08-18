# F10 — 문의 폼 자동 생성 (Tally 통합)

> 근거: `docs/plans/adsense_f10_contact_form_plan.md`. 사용자 확정(2026-08-18):
> **블로거·워드프레스 통합 — 양 플랫폼 모두 Tally 폼 임베드.** 단일 Tally 계정으로
> 블로그별 폼을 만들어 **문의가 한 곳(대시보드 + 계정 이메일 알림 + webhook)에
> 자동 수집**된다. Google Forms는 폼별 응답 분리·네이티브 알림 없음이 한계라 Tally로
> 전환(도메인 무구매·범용 `tally.so` 도메인이라 공개 지문 없음).

## 원칙
- **단일 방식**: 블로그별 Tally 폼을 Tally API로 생성 → 문의 페이지에 폼 URL을
  `contact_form_url`로 자동 채움(기존 iframe+링크 골격 재사용).
- **통합 수신(핵심)**: 모든 폼이 한 Tally 계정에 모임 → (a) Tally 대시보드 한 곳,
  (b) 계정 소유자 이메일 알림(기본), (c) webhook(Phase 2, blogauto 통합 수신함).
- **이메일 미노출**: 필수 페이지 mailto 제거, 폼 링크로 대체(기존 `_contact_section`).
- **멱등**: 블로그별 `contact_form_id` 저장 → 재생성 방지. 운영자 수동 URL 존중.

## 인증 — 단일 Tally 계정(API 키)
- Tally → Settings → API keys 에서 발급한 `tly-...` API 키를 blogauto 설정에 입력
  → `system_settings`에 암호화 저장 → `POST https://api.tally.so/forms`(Bearer)로 호출.
- 키 하나로 모든 블로그 폼 생성. 다른 API 키 항목과 동일하게 마스킹+토글 UI.

## 프로비저닝 흐름

```mermaid
flowchart TD
    A[필수 페이지 생성 시 ensure_contact_form] --> B{contact_form_id 있음?}
    B -->|있음| C[기존 URL 재사용]
    B -->|없음, 수동 URL 존중| C
    B -->|없음| D{Tally API 키 설정?}
    D -->|아니오| E[None → 기존 mailto 폴백]
    D -->|예| F[POST /forms<br/>FORM_TITLE + TITLE/INPUT 쌍(이름·이메일·메시지)]
    F --> G[form_id + 공개 URL tally.so/r/id]
    G --> H[author_profile에 contact_form_id/url 저장]
    H --> I[문의 페이지가 폼+링크로 렌더(이메일 미노출)]
```

## 폼 블록 구성 (Tally)
- `FORM_TITLE`(payload.title="{블로그} 문의")
- 질문 3개 = 각 `TITLE`(payload.html=라벨) + `INPUT_*`(payload.isRequired=true) 쌍,
  라벨·입력은 같은 `groupUuid`로 묶음.
  - 이름=INPUT_TEXT, 이메일=INPUT_EMAIL, 문의 내용=TEXTAREA
- 공개 URL: `https://tally.so/r/{form_id}` (링크+iframe 겸용). **최초 실호출 응답을
  원시 로깅**해 form_id 필드/URL 형식을 실측 검증(로그 `[F10] Tally 폼 생성 응답 원시`).

## 수신 (단계적)
- **Phase 1**: Tally 네이티브 — 대시보드 + 계정 이메일 알림(모든 폼이 한 계정).
- **Phase 2(후속)**: Tally webhook → blogauto 통합 수신함 테이블(실시간, 폴링 불필요).

## 영향 파일
| 구분 | 파일 |
|------|------|
| 신규 | `services/publishing/tally_forms_service.py`(폼 생성/URL·API키) |
| 수정 | `services/publishing/contact_form_provisioner.py`(Tally 사용), `required_pages_service.py`(훅), `routers/settings.py`(tally-account API), `templates/settings/modal.html`(Tally 키 입력 UI) |
| 삭제 | `services/publishing/google_forms_service.py` |
| 테스트 | `tests/unit/test_tally_forms_service.py` |

## 사전 준비물(운영자)
1. **Tally 계정 1개 생성**(무료 무제한).
2. **Settings → API keys 에서 API 키 발급**(`tly-...`).
3. blogauto **설정 → API 설정 → 문의 폼(Tally 연동)** 에 키 입력.

## 리스크/한계
- Tally API 응답 필드/공개 URL 형식은 최초 실호출로 실측 검증(원시 로깅) 후 조정.
- API 100 req/분 → 대량 생성 throttling.
- 일부 WP(멀티사이트·보안 플러그인) iframe 제거 시 링크 폴백.
- 한 Tally 계정에 모든 폼 → 비공개 계정 연결(공개 미노출, 수용).

## 마이그레이션
- **없음.** API 키는 `system_settings`(암호화), 폼 식별자는 `author_profile` JSONB.
