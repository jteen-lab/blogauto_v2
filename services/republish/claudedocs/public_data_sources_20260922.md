# 공공 API·이미지 소스 확장 — 니치별 1차 출처 후보

> 작성 2026-09-22 | 관련: `app/models/external_source.py`, `app/services/reference/sources/`, `docs/flowcharts/reference_accuracy.md`
> 오너 방향: "다른 포스트를 수집해 재가공하면 잘못된 정보가 수정이 아니라 재확산된다. 공공 정보를 1차 출처로 쓰면 정확도·품질이 올라간다." 장기 과제로 채택.
> 프로젝트 메모리 요약: `project_public_data_sources.md`

---

## 0. 왜 이 작업인가

지금 글 생성은 `reference_collector` 가 웹문서(네이버 웹문서·Brave)를 요약해 프롬프트에 넣는다. 웹문서는 이미 누군가가 재가공한 2차 자료라 오류가 있으면 그대로 옮겨진다. `external_sources` 는 이 문제를 풀려고 만든 자리 — 기관이 공시한 값을 **"[공식 자료] 웹 문서와 다르면 이쪽을 따르세요"** 로 프롬프트 맨 앞에 놓는다. 현재 금융 니치(금감원·서민금융진흥원)와 정책(정책브리핑)만 붙어 있다. 이 문서는 그 자리를 **다른 니치로 넓히는 후보 목록**이다.

부수 효과: 검색 미노출 진단(`docs/plans/search_visibility_*`)의 원인 중 하나가 "검증 불가 콘텐츠"였다. 1차 자료가 붙은 글은 그 원인을 직접 줄인다.

---

## 1. 현재 구조 (코드 기준)

| 구성 | 위치 | 내용 |
|---|---|---|
| 등록표 | `app/models/external_source.py` | `external_sources` 테이블. endpoint · auth_key(암호화) · options(JSON) · match_topics · match_keywords · daily_limit(기본 1,000) |
| 선택 | `app/services/reference/sources/registry.py` | 제목+니치 → 맞는 소스만 → 최대 3개(`MAX_SOURCES`) 호출. 둘 다 비면 안 씀 |
| 어댑터 | `sources/data_go_kr.py` | **공공데이터포털 표준.** JSON/XML 자동 판별, `options.items_path / title_field / field_map / query_field / date_params / date_range_days / extra_params / rows / max_facts`. 포털 오류코드 → 한국어 안내(`ERROR_GUIDE`) |
| 어댑터 | `sources/fss_finlife.py` | 금감원 전용(자체 규격, `{op}` 자동 치환) |
| 프리셋 | `sources/presets.py` | 금감원 6 · 서민금융진흥원 대출 · 정책브리핑 = 8종 |
| 공통형 | `sources/base.py` | `SourceFact(title, fields, source_name, url, published)` → `SourceResult.to_prompt()` |
| 이미지 | `generation/{template_image,ai_image}_service.py` | template(Pillow) · dalle · nanobanana. **스톡·공공사진 provider 없음** |

**결론: 공공데이터포털 규격 API는 코드 없이 `presets.py` 한 항목 + 인증키로 붙는다.** 포털 밖 자체 규격(KOSIS·ECOS·법제처·기상청허브)은 `fss_finlife` 처럼 어댑터를 써야 한다.

**교훈(프리셋 주석)**: 정책브리핑은 "짐작으로 적었다가 두 번 틀렸다", 서민금융진흥원은 "경로에 서비스명이 두 번 들어가 탐색으로 못 찾았다". **등록 전 반드시 포털 [미리보기] URL로 실호출해 `items_path`·필드명을 확정**한다.

---

## 2. 여행·관광 니치 (오너 제안: 포토코리아·콘텐츠랩)

둘 다 공공데이터포털에 있다 → `data_go_kr` 어댑터.

### 2.1 국문 관광정보 KorService2 — data.go.kr/15101578
- 약 26만 건, 15 카테고리: 관광지·문화시설·축제행사·여행코스·레포츠·숙박·쇼핑·음식점·반려동물 동반·이미지
- 주요 오퍼레이션(확정은 실호출로): `areaBasedList2`(지역), `searchKeyword2`(키워드), `searchFestival2`(축제, 시작일), `detailCommon2`(개요 `overview`), `detailIntro2`(운영시간·요금 등), `detailImage2`(추가 이미지)
- 응답 필드: `title, addr1, tel, firstimage, firstimage2, overview, mapx/mapy, contenttypeid`
- 라이선스: 공공누리 1유형(출처표시) 또는 3유형. **사진을 기업 브랜딩·명예훼손 용도로 쓰는 것 금지** → CPA 랜딩·광고 소재에는 쓰지 말 것
- 한도: 개발계정 1,000회/일, 운영계정 활용사례 등록 시 증량
- 글 소재: "OO 축제 2026 일정·요금·주차", "OO 지역 반려동물 동반 가능 관광지" — `overview`·요금·기간이 구조화돼 있음
- 등록안: `match_topics: ["여행", "관광", "지역"]`, `match_keywords: ["관광지", "축제", "여행", "가볼만한곳", "명소", "나들이"]`, `query_field: keyword`(searchKeyword2 기준), `max_facts: 3`

### 2.2 관광사진 정보 — data.go.kr/15101914
- 포토코리아(phoko.visitkorea.or.kr) 약 10만 장. 필드: 제목·촬영일·촬영지·촬영자·키워드·**웹용 이미지 URL**(`galWebImageUrl`)
- 공공누리 1유형 — 출처 "한국관광공사" 표기하면 영리 이용 가능, 재판매 금지
- 1,000회/일
- 용도 ①본문 사진(정보성 글) ②여행커넥트 패키지 글의 현지 사진 대체
- **주의**: 이건 SourceFact(텍스트)로 받아도 "사진을 본문에 넣는" 단계는 이미지 파이프라인이 처리해야 한다 → §5-B

### 2.3 콘텐츠랩 conlab.visitkorea.or.kr
위 API들의 통합 포털. 별도 API가 아니라 안내·발급 창구.

---

## 3. 다른 니치 후보 — 공공데이터포털(전부 무료·1,000회/일·`data_go_kr` 호환)

| 니치(match_topics) | API | 포털 ID | 글에 쓸 값 | 비고 |
|---|---|---|---|---|
| 정부지원금/복지 | 행정안전부 공공서비스(혜택) 정보 — 보조금24 | 15113968 | 약 7,500 서비스의 대상·조건·신청방법·담당기관 | 정책브리핑(뉴스)과 보완. Swagger 문서 있음 |
| 건강 | 식약처 의약품개요정보(e약은요) | 15075057 | 효능·용법·주의·부작용·보관·알약 이미지 | 일반의약품 한정. 의료광고 규제와 무관한 정보성만 |
| 건강 | 심평원 병원정보서비스 | 15001698 | 지역·진료과목별 병원 목록 | "OO동 야간진료 소아과" 류 |
| 건강 | 심평원 의료기관별상세정보 | 15001699 | 진료시간·장비·전문의 | 위와 세트 |
| 부동산 | 국토부 아파트 매매 실거래가 | (검색: 국토교통부_아파트 매매 실거래가) | 단지·면적·층·거래금액·거래일 | `LAWD_CD`(법정동 5자리)+`DEAL_YMD`(YYYYMM) 필수, XML |
| 부동산 | 국토부 아파트 전월세 실거래가 | 동상 | 보증금·월세·계약기간 | 동상 |
| 부동산 | 한국부동산원 부동산통계 | — | 주간·월간 가격지수 | |
| 생활/물가 | KAMIS 농수축산물 유통정보 | (KAMIS 자체 포털도 있음) | 품목별 일일 소매가·전주 대비 | "이번 주 장바구니 물가" |
| 문화 | KOPIS 공연예술통합전산망 | (kopis.or.kr 자체 키) | 공연명·기간·장소·가격 | 자체 규격 가능성 → 실호출로 확인 |
| 문화 | 문화포털 API / 국립중앙박물관 e뮤지엄 | culture.go.kr | 전시·유물·이미지(공공누리) | 자체 키 발급 |
| 교육/취업 | 나이스 학교기본정보, 커리어넷, HRD-Net | — | 학교·직업·훈련과정 | |
| 날씨 | 기상청 단기예보 | (data.go.kr) | 격자 좌표 기준 예보 | 여행 글 보조. 좌표 변환 필요 |
| 자동차 | 국토부 자동차종합정보(자동차365), 리콜정보 | — | 리콜·검사 | 카바딜러 오퍼와 결은 다름 |

## 4. 포털 밖 — 어댑터 코드 필요

| 소스 | 주소 | 조건 | 니치 |
|---|---|---|---|
| 법제처 국가법령정보 | open.law.go.kr | 회원가입 → 담당자 승인 1~2일. 법령·판례·행정규칙·자치법규 본문. **일부 API 상업이용 불가 명시** → API별 확인 | 법무·세금·복지 |
| KOSIS 국가통계포털 | kosis.kr/openapi | 자체 키, 통계표 ID 기반 | 시니어·재테크·부동산 |
| 한국은행 ECOS | ecos.bok.or.kr/api | 자체 키, 통계코드 기반 | 금융·재테크(금리·환율) |
| 기상청 API허브 | apihub.kma.go.kr | 자체 키 | 여행·생활 |

`reference_search_upgrade_20260915.md` 길 2("법령·판례를 정확히 가져온다")가 법제처 항목과 같은 방향.

---

## 5. 이미지 소스

| 소스 | 무료 한도 | 조건 | 판단 |
|---|---|---|---|
| 관광사진 API(한국관광공사) | 1,000/일 | 공공누리 1유형, 출처 표기, 브랜딩 금지 | **국내 여행·지역 글 1순위** |
| Pexels | 200/시간 | 상업 가능, **다운로드해 자체 저장** 권장, 영상 제공 | **해외·일반 소재 1순위** |
| Unsplash | 50/시간(승인 5,000) | **핫링크 필수**(자체 CDN 통계), 크레딧 권장 | 품질 높으나 한도·핫링크 제약 |
| Pixabay | 100/분 | 핫링크 금지 → 다운로드, 일러스트·벡터 | 보조 |
| 한국관광공사 외 공공(e뮤지엄·문화포털) | 각자 | 공공누리 유형 확인 | 문화 니치 |

---

## 6. 적용 계획

### A. 등록만(코드 없음) — 순서 제안
1. KorService2 프리셋 (여행)
2. 관광사진 프리셋 (여행) — 단, 사진 삽입은 B-1 전까지 URL을 SourceFact 필드로만 노출
3. 보조금24 (정부지원금/복지) — 기존 니치라 즉시 효과
4. 실거래가 (부동산) — 기존 니치. `date_params` 로 `DEAL_YMD` 생성 로직이 현재 어댑터의 날짜 처리(startDate/endDate 형)와 맞는지 확인 필요 → 안 맞으면 `extra_params` 로 고정하거나 소규모 코드
5. e약은요 / 심평원 (건강 니치 개설 시)
6. KAMIS (생활)

각 항목: 포털 활용신청(반영 ≤1시간) → 미리보기 URL 실호출 → `items_path`·`field_map` 확정 → 프리셋 추가 → 화면에서 키 등록 → 테스트 글 1건으로 "[공식 자료]" 블록 삽입 확인.

### B. 코드 필요
- **B-1 공공/스톡 이미지 provider**: `ai_image_service.py` 옆에 4번째 provider. 흐름: 제목/키워드 → 관광사진 API(국내) 또는 Pexels(그 외) 검색 → 다운로드 → 자체 저장(imgbb 경유 규칙은 Blogger 발행 로직 참고) → 본문 삽입 + 출처 캡션("사진: 한국관광공사" / "Photo by X on Pexels"). 실패 시 기존 template 로 폴백.
- **B-2 자체 규격 어댑터**: KOSIS · ECOS · 법제처. `fss_finlife.py` 를 본떠 각 1파일.
- **B-3 실거래가 날짜 파라미터**: `_date_params` 가 단일 월(YYYYMM) 형식을 지원하는지 확인 후 필요 시 `date_format` 옵션 추가.

### C. 제약·주의
- 관광사진 "기업 브랜딩 금지" → CPA 랜딩·광고 소재 금지, 정보성 본문만.
- 공공누리 출처 표기 누락은 라이선스 위반 — 이미지 캡션 자동 삽입을 B-1 에 포함.
- 소스가 "못 찾으면 조용히 넘어가는" 원칙(registry 주석, 2026-09-06 사고) 유지 — 비슷한 값을 억지로 붙이지 않는다.
- 색인 0건 상태에서는 유입 효과가 바로 안 보인다. 이 작업의 1차 목표는 유입이 아니라 **정확도**이고, 검증 가능 콘텐츠는 색인 회복의 조건 중 하나다.

---

## 7. 출처
- 공공데이터포털: 15101578(국문 관광정보 GW), 15101914(관광사진 GW), 15113968(보조금24), 15075057(e약은요), 15001698/15001699(심평원)
- 한국관광공사 콘텐츠랩 conlab.visitkorea.or.kr, 포토코리아 phoko.visitkorea.or.kr
- 법제처 open.law.go.kr OPEN API 활용가이드
- Pexels API pexels.com/api, Unsplash unsplash.com/documentation, Pixabay API 문서
- yybmion/public-apis-4Kr (한국 공개 API 모음)
