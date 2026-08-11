# 필수 페이지 4종 — 이메일 노출을 Contact Form으로 전환

> 작성: 2026-08-11 (체셔캣 세션에서 논의, 코드 위치 확인 후 작성)

## 문제

`required_pages_templates.py`가 생성하는 애드센스 필수 페이지 4종 중
3개(privacy/about/contact)가 `mailto:{owner_email}`로 **연락처 이메일 주소를
페이지에 그대로 노출**한다 (해당 파일 60, 102, 112~113행).

시각적 분산(벤치마킹하는 다른 사용자에게 "동일 소유주 블로그 묶음"이
드러나는 것을 피하는 것) 목적상 이 방식은 문제가 있다:
- 도메인 기반 워드프레스는 도메인 자체가 다르면 이메일도 달라 상대적으로 안전
- 하지만 캐치올(도메인 하나로 대량 이메일 생성) 구조를 쓰면 뒤쪽 도메인이
  같아 결국 동일 소유주로 추정 가능
- 구글 블로거는 계정 1개당 블로그 최대 100개 — 같은 구글 계정 이메일을
  쓰면 노출 문제가 이메일 층위에서 더 크게 발생

## 결정 (2026-08-11 논의 결과)

1. **필수 페이지 4종 자체는 삭제하지 않는다.** 애드센스 심사·유지 요건이라
   삭제 시 정책 위반 소지가 있음. 대신 페이지 문구를 블로그마다 변형(paraphrase)
   하는 방향이 시각적 분산 목적에 더 맞음 (템플릿 생성 시 문구 변주 필요 —
   현재 `required_pages_templates.py`는 고정 템플릿이라 문구가 블로그마다 동일).
2. **이메일 직접 노출(mailto) 대신 Contact Form으로 전환.**
   - 애드센스 필수 페이지 요건은 "이메일 텍스트 노출"이 아니라 "연락 가능한
     수단의 존재"이므로 Contact Form으로 대체해도 요건 위반 아님(확인 완료).
   - 워드프레스: Contact Form 7 등 플러그인 설치 후 문의 페이지에 폼 삽입.
   - 구글 블로거: 블로거 내장 "연락처 양식" 가젯 사용 시 방문자가 작성한
     내용이 **그 블로그 소유 구글 계정의 등록 이메일로 전달**되며, 방문자는
     주소를 볼 수 없음.

## 현재 코드 구조상 확인 필요한 것

- **블로거 내장 연락처 가젯은 Layout 위젯이지 Page가 아니다.** 현재
  `blogger_page_publisher.py`는 Blogger **Pages API**(`pages.insert`)로 정적
  HTML 페이지만 생성한다. 내장 연락처 가젯을 자동으로 붙이려면 Blogger
  **Layout/Template API**(또는 XML 템플릿 편집)가 별도로 필요 — 지금
  구조로는 자동화 난이도가 워드프레스보다 높음. 조사 필요.
- 대안: 블로거 쪽은 당장 자동화 대신, Google Forms/Formspree 같은 외부 폼을
  iframe으로 문의 페이지 HTML에 삽입하는 방식이면 기존 Pages API로도
  가능(콘텐츠 HTML만 바뀌는 것이라 `_contact_page()` 템플릿 수정으로 충분).
  단, 응답 수신처를 블로그별로 분리할지, 캐치올 메일함 하나로 모을지는
  별도 결정 필요.
- 워드프레스는 REST API로 플러그인 설치·활성화까지 자동화 가능한지,
  아니면 수동 설치가 필요한지 `wordpress_api.py` 기준으로 확인 필요.

## 수정 범위 (착수 시)

1. `required_pages_templates.py`
   - `_privacy_page`, `_about_page`, `_contact_page`의 `mailto:` 링크를
     제거하고 Contact Form(또는 폼 링크) 삽입으로 교체
   - 문구를 블로그별로 변형할 수 있는 최소한의 변주 장치 검토
2. `required_pages_service.py` / `blogger_page_publisher.py`
   - 블로거 내장 가젯 자동화 여부 조사 결과에 따라 분기 처리 결정
3. 관련 단위테스트(`test_required_pages_templates.py`, `test_required_pages_service.py`) 갱신

## 상태

**구현 완료(2026-08-11, 같은 세션 이어서 착수)** — 아래 "대안" 경로로 구현:

- `required_pages_templates.py` — `author_profile.contact_form_url`이
  설정되면 privacy/about/contact 페이지에서 `mailto:` 노출을 완전히
  제거하고 외부 폼(iframe 임베드 + 링크)으로 대체. 미설정 블로그는 기존
  mailto 방식 그대로 동작(하위호환, 회귀 없음).
- Blogger/WordPress 모두 콘텐츠 HTML만 바뀌는 방식이라 플랫폼별 분기가
  불필요 — `blogger_page_publisher.py`/`wordpress_api.py` 수정 없이 해결.
- 문구 변주(paraphrase) — 4종 페이지 각각 인트로 문장 2가지를 블로그별로
  안정적으로(md5 해시 기반, 재실행해도 동일) 선택하도록 최소 구현.
- 관리자 UI(`_tab_adsense.html`)에 "문의 폼 URL" 입력 필드 추가, 기존
  "문의용 이메일"은 폼 미설정 시 대체용으로 문구 변경.
- 단위테스트 4종 추가(`test_required_pages_templates.py`) — 폼 URL
  설정 시 이메일 미노출, 미설정 시 하위호환, 변주 안정성 확인.

**미해결(다음 세션 과제)**:
- 실제 Google Forms/Formspree 폼 URL 생성은 외부 수동 작업 — 코드는
  URL을 받아 임베드하는 지점까지만 담당. 블로그별 폼을 분리할지
  캐치올로 모을지는 운영자가 폼 생성 시점에 결정.
- 블로거 내장 "연락처 양식" 가젯(Layout API) 자동화는 여전히 미조사 —
  현재 iframe 임베드 방식으로 요건은 충족되므로 우선순위 낮음.
