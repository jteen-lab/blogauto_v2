# 키워드 모듈 재설계 계획서

> 작성일: 2026-09-01 | 버전: v1 (초안)
> 선행 문서: `keyword_management_review.md`(현행 결함) · `keyword_management_benchmark.md`(벤치마킹)
> 순서도(예정): `docs/flowcharts/keyword_module.md`

---

## 1. 배경과 목표

현행 키워드 관리는 ① 모듈 관리에서 저장이 안 되고 ② 오토런이 항상 실패하며 ③ 플로우 실행
분기가 없어, 실제로 도는 경로가 `/keyword-lab` 화면 버튼 하나뿐이다(검토서 3장).
설계 면에서도 "키워드 1개 → 제목 3편, 네이버 단일 소스"라 대량 발행 규모를 못 받친다.

### 목표
1. **기존 모듈 시스템 승계** — 프롬프트/생성 모듈과 동일한 계약(모듈 내 테스트 → 플로우 실행).
2. **대량 생산 가능** — 클러스터 단위 생산으로 회차당 산출을 수십~수백 편 규모로.
3. **멀티 엔진 수집** — 네이버 + 구글 양쪽에서 키워드를 모은다.
4. **멀티 엔진 노출** — 구글 단일이 아니라 네이버·빙 등 다중 검색 노출을 목표로 한다.
5. **성과 되먹임** — 발행 후 색인·노출 결과가 다음 키워드 선정에 반영된다.

### 비목표(이번 범위 밖)
- 순위 추적(SERP rank tracking) 자체 구현
- 유료 3rd-party 키워드 API(DataForSEO 등) 도입 — 4장에 후보로만 기록

---

## 2. 벤치마킹 반영 요약

`keyword_management_benchmark.md` 조사 결과 중 설계에 직접 반영하는 항목:

| # | 조사 결과 | 반영 |
|---|---|---|
| B1 | 수집은 시드 → **자동완성 + 연관검색어** 확장 → 일괄 측정 → 사분면 선별 | §3 [2]단계 다소스 확장 |
| B2 | 판정 축은 검색량 대 **월간 발행량**(누적 문서수 아님), 검색량 **상한**도 존재 | §3 [3][4], §5 스키마 |
| B3 | 대량 툴은 키워드 리스트 → **큐** → 배치 → 자동 발행 (ZimmWriter 1,000편 큐) | §3 [6], §6 재고 목표식 |
| B4 | 생산 단위는 **클러스터** (클러스터당 8~10 키워드, 인벤토리 500~1,000) | §3 [4][5], §5 `keyword_clusters` |
| B5 | 확장은 **head × modifier 다축 매트릭스**, 착수 전 50변형 수요 검증 | §3 [2], §5 `expansion_axes` |
| B6 | AI 검색의 **query fan-out** — 하위 질문 커버리지가 노출을 만든다 | §3 [5] 제목 전개, FAQ 스키마 연계 |

---

## 3. 목표 파이프라인 (6단계)

```
[1] 시드 결정
     니치 카탈로그 + 블로그 활성 카테고리 + **결핍 니치 우선** + 채택 키워드 재귀
     ↓
[2] 확장 (다소스 · 다축)
     · head × 축(의도/형식/대상/시점/지역) 매트릭스
     · 네이버: 검색광고 연관키워드 + 자동완성 + 연관검색어
     · 구글  : Autocomplete(suggest) + Trends related_queries + GSC 실측 쿼리
     ↓
[3] 측정 (엔진별)
     · 수요: 네이버 검색광고 월간 검색량 / 구글 Keyword Planner·Trends
     · 공급: **월간 발행량**(최근 30일 신규) ← 누적 문서수에서 전환
     ↓
[4] 판정 · 클러스터링
     · 검색량 하한 **+ 상한**, 포화 등급, 위험 유형, 의도 분류
     · 유사 키워드를 클러스터로 묶음(1차 임베딩/토큰 유사도, 2차 SERP 오버랩)
     ↓
[5] 제목 생산
     클러스터 1개 = **필러 1편 + 서브 N편**
     하위 질문(fan-out)을 제목·소제목으로 전개
     ↓
[6] 재고 투입
     금지어 필터 → 카테고리 분류 → 유사도 그룹핑 → main_titles(available)
     ※ 현행은 이 관문을 전부 우회한다 — 반드시 통과시킨다
```

---

## 4. 멀티 엔진 **수집** 설계 (네이버 + 구글)

### 4-1. 유사 프로그램의 구글 키워드 수집 실태 (조사 결과)

**국내 도구도 이미 구글을 같이 다룬다.** 네이버 전용이 아니다.
- **로워드** — 네이버·구글 **양쪽 검색량 조회** + 구글 유입 트래킹
- **플러스제로 키워드도구** — "네이버/구글 키워드 검색량 조회 및 분석" 이 서비스 정체성
- **키워드마스터** — 네이버·구글 등 다중 플랫폼 검색량·연관어·트렌드
- **데일리 키워드** — 앱 이름 자체가 "구글 네이버 검색광고 키워드 검색량"

**해외 키워드 도구가 구글 데이터를 얻는 표준 경로**는 네 가지다.
1. **Google Autocomplete(suggest) 엔드포인트** — `google.com/complete/search?output=toolbar&gl=kr&q=...`
   무료·무인증. 시드 뒤에 a~z·0~9를 붙여(prepend/append) 반복 호출해 롱테일을 긁는 방식이
   AnswerThePublic류의 실제 구현이다. Apify·DataForSEO도 이 스크래퍼를 상품화한다.
2. **Google Ads Keyword Planner API** — 검색량·경쟁도. 단 **활성 캠페인이 없으면 구간값**만
   나오고(1k~10k), 유사 키워드를 묶어 합산해 보여 준다. 2013년 정확 수치 제공 중단 이후
   "범위로 해석하라"가 공식 입장이다. → **절대값이 아니라 상대 비교·필터 용도**로만 써야 한다.
3. **Google Trends** — 절대 검색량이 아닌 **상대 관심도·계절성·related_queries**. 방향성 판단용.
4. **Google Search Console** — 자기 사이트가 **실제로 노출된 쿼리**(노출수·클릭·순위).
   프로그래매틱 SEO 문헌이 "가장 신뢰할 수 있는 modifier 확장 소스"로 꼽는 것이 GSC다.

### 4-2. 블로그오토의 강점 — 이미 다 갖고 있다

| 수단 | 보유 여부 | 위치 |
|---|---|---|
| 네이버 검색광고(연관+검색량) | ✅ | `naver_ads_service.py` |
| 네이버 검색(문서수) | ✅ | `naver_search_service.py` |
| 네이버 데이터랩(트렌드) | ✅ | `naver_datalab_service.py` |
| 구글 Keyword Planner | ✅ **미사용** | `google_keyword_planner_service.py` |
| 구글 Trends(related_queries/계절성) | ✅ **미사용** | `google_trends_service.py` |
| **구글 Search Console** | ✅ **스코프까지 확보** | `search_visibility/index_check_service.py` (`webmasters.readonly`) |
| 자동완성(네이버/구글) | ❌ 없음 | 신규 |

> 🔑 **가장 큰 발견**: GSC 연동이 이미 `webmasters.readonly` 스코프로 들어와 있다.
> 같은 스코프로 **Search Analytics API**(`searchAnalytics/query`)를 호출할 수 있다.
> 즉 **우리 블로그가 실제로 노출된 쿼리·노출수·평균순위**를 추가 인증 없이 가져올 수 있다.
> 이것이 (a) 가장 정확한 키워드 소스이자 (b) 지금 없는 성과 되먹임의 재료다.

### 4-3. 수집 소스 매트릭스 (설계안)

| 소스 | 엔진 | 얻는 것 | 비용/제약 | 우선순위 |
|---|---|---|---|---|
| GSC Search Analytics | 구글 | 실제 노출 쿼리·노출·클릭·순위 | 사이트 등록 필요, 데이터 지연 2~3일 | **P1** |
| 네이버 검색광고 | 네이버 | 연관키워드 + 월간 검색량 + compIdx | 5개/호출, 공백 키워드 거부 | P1(현행) |
| 구글 Autocomplete | 구글 | 롱테일·질문형 확장 | 비공식 경로, 호출 간격 필요 | P2 |
| 네이버 자동완성 | 네이버 | 최신성 강한 롱테일 | 파싱 경로, 차단 리스크 | P2 |
| 네이버 연관검색어 | 네이버 | 자동완성과 겹치지 않는 축 | 결과 페이지 파싱 | P2 |
| 구글 Keyword Planner | 구글 | 검색량 구간·경쟁도 | **구간값**, Ads 계정 필요 | P3 |
| 구글 Trends | 구글 | 계절성·related_queries | 절대값 없음, 레이트리밋 | P3 |
| 네이버 데이터랩 | 네이버 | 상대 트렌드 | 절대값 없음 | P3 |

### 4-4. 데이터 모델 함의 — 지표를 **엔진별로** 분리

현행 `keyword_candidates` 는 검색량·문서수 컬럼이 **엔진 구분 없이 1벌**이다.
구글을 더하는 순간 컬럼이 충돌한다. 1:N 으로 쪼갠다.

```
keywords                 (키워드 그 자체 — 정규화, 클러스터 소속, 의도, 위험라벨)
keyword_metrics          (keyword_id, engine, search_volume, monthly_pub_count,
                          competition, saturation, measured_at)   ← engine = naver|google
keyword_clusters         (클러스터, 대표 키워드, 필러 제목, 상태)
```
- 판정은 **블로그의 타깃 엔진 기준**으로 수행한다(§6-2).
- 어느 엔진에서도 수요가 없으면 reject, 한쪽에서만 있으면 그 엔진 타깃 블로그에만 배정.

---

## 5. 멀티 엔진 **노출** 설계 (구글 + 네이버 + 빙)

### 5-1. 현재 보유 자산 (이미 상당하다)

`app/services/search_visibility/` 에 다음이 이미 있다:
- `indexnow_service.py` — **IndexNow 제출**. 네이버·빙 등 참여 엔진에 발행 URL 통지
  (구글은 IndexNow 미참여). 키 파일이 **호스트 루트**에 있어야 하는 제약까지 구현됨
- `index_check_service.py` — **구글 GSC URL Inspection** 으로 색인 상태 확인
- `naver_index_service.py` — 네이버는 색인 API 가 없어 **웹문서 검색에 잡히는지**로 대체(found/not_found)
- `naver_check.py` — **robots.txt 가 `Yeti`(네이버 크롤러)를 막는지** + 서치어드바이저 소유확인 메타 점검
- `sitemap_service.py`, `discover_service.py`, `tracker.py`, `backfill.py`

또한 `naver_index_service.py` 주석에 네이버 자동화 한계가 이미 정리돼 있다:
> 사이트 등록·사이트맵 제출 = API 없음(수동 1회) / 웹페이지 수집 요청 = 수동, 하루 50건 /
> **IndexNow 가 유일한 자동 경로**(단 블로거는 키 파일을 못 올려 불가)

### 5-2. 조사로 확인한 네이버 노출의 현실

- 네이버 서치어드바이저는 **2023년 7월부터 IndexNow 지원** → 워드프레스는 자동 색인 통보 가능
- 등록 절차: 사이트 등록 → 소유확인(HTML 파일 권장) → **사이트맵 + RSS 제출**.
  노출까지 통상 **14~16일**
- **외부 워드프레스는 네이버 "블로그 탭"이 아니라 "웹사이트 탭"에 노출**된다.
  뷰탭이 스마트블록으로 통합되면서 외부 블로그의 블로그탭 진입은 사실상 막혔다
- 따라서 네이버 목표는 "블로그탭 상위노출"이 아니라 **웹사이트 탭 + 스마트블록 인기주제 진입**
  으로 잡아야 한다. 스마트블록은 세분화된 **주제(하위 의도)** 단위로 노출되므로,
  §3[5]의 **클러스터 + 하위 질문 전개**가 그대로 네이버 대응책이 된다

### 5-3. 노출 측면 보강 제안

| # | 항목 | 현재 | 제안 |
|---|---|---|---|
| E1 | 블로그별 **타깃 엔진 설정** | 없음(암묵적 구글) | `Blog.target_engines = [google, naver, bing]`. 키워드 판정·제목 생성·색인 점검이 이 값을 따른다 |
| E2 | 네이버 사이트 등록 상태 추적 | 메타태그 정황만 점검 | 블로그별 **SA 등록 체크리스트**(소유확인/사이트맵/RSS 제출 여부)를 상태로 관리. API 가 없으므로 **수동 완료 체크 + 자동 정황 점검** 병행 |
| E3 | RSS 제출 | 사이트맵만 | 워드프레스 `/feed` 를 **RSS 로 별도 제출** 안내·기록 (네이버는 RSS 로 더 빨리 수집) |
| E4 | 블로거의 IndexNow 불가 | 스킵 처리 | 블로거는 키 파일 업로드 불가 → **네이버 타깃 블로그는 워드프레스로 배정**하는 정책을 플로우 단계에서 강제 |
| E5 | `Yeti` 차단 점검 | 있음 | 발행 전 게이트로 승격(차단 상태면 네이버 타깃 발행을 보류) |
| E6 | 빙(Bing) | IndexNow 로 이미 통지됨 | Bing Webmaster 색인 확인을 `index_check` 에 추가 검토(선택) |
| E7 | 다음(카카오) | 없음 | 다음은 자체 색인 비중이 낮고 공개 API 가 없어 **후순위**. 사이트 등록만 수동 항목으로 |
| E8 | **성과 되먹임** | 데이터만 있고 미연결 | 색인 결과 + GSC 노출/순위를 키워드·클러스터 점수에 반영(§6-3) |

---

## 6. 판정·재고 정책

### 6-1. 판정 기준 개편
```
reject : 검색량 < 하한  (엔진별)
reject : 검색량 > 상한  (기본 100,000 — 벤치마크 권장 회피 구간)
reject : 포화도 < 하한  (공급 = 월간 발행량 기준)
hold   : 위험 유형(연락처·시간표·채용조건 등) → 사람 검토 큐
adopt  : 위 통과 + 의도 분류 성공 + 클러스터 소속
```
- 수집 시점과 측정 시점의 임계값이 달랐던 현행 버그(검토서 D-8) 제거 — **단일 기준 객체**를 주입.

### 6-2. 엔진별 판정
- 블로그의 `target_engines` 에 포함된 엔진 지표만 본다.
- 다중 엔진 블로그는 **OR 통과 + 우선 엔진 지표로 정렬**.

### 6-3. 성과 되먹임 (신규)
- GSC Search Analytics 에서 발행 글의 **노출·클릭·평균순위**를 회수
- 네이버는 `naver_index_service` 의 found/not_found 로 대체 지표 사용
- 반복적으로 노출 0 / 미색인이 나오는 **키워드 패턴·클러스터·수식어 축**에 감점
- 반대로 노출이 붙은 축은 시드 우선순위 상향 → 확장 매트릭스가 스스로 학습

### 6-4. 재고 목표식 (상수 폐기)
```
목표재고(블로그, 니치) = 일일발행수(성장 프로파일) × 리드타임(일) × 안전계수
부족분 = 목표재고 − 현재 available(그 블로그가 실제 꺼낼 수 있는 것)
```
- **현재 재고 계산과 생성 대상 조회의 조건을 동일 함수로 통일**한다(현행 D-5의 원인).
- 부족분이 큰 니치부터 시드를 뽑는다(결핍 우선 큐).

---

## 7. 모듈 계약 (요청 사항 반영)

1. **모듈 관리 안에서 완결**
   - 설정 → **테스트 실행** → 저장. 테스트는 시드 → 확장 → 측정 → 클러스터 → **제목 샘플**까지
     미리보기(저장 없음 / 소량 호출). 프롬프트 모듈 `_prompt_test_panel.html` 패턴 승계.
2. **플로우에서 실제 동작**
   - `flows_execute.py` 단일 실행 · 백그라운드 플로우 · `flow_scheduler` 오토런 **3경로 모두**
     동일 실행기(`KeywordModuleRunner`) 호출.
3. **블로그 스코프**
   - 플로우에 연결된 **모든 블로그** 순회(`flow_module_blog_scope` 규약). 현행 `blogs[0]` 폐기.
4. **`/keyword-lab` 화면 성격 변경**
   - 실행 콘솔 → **후보·클러스터 열람 / 위험 유형 검수 / 수동 승격** 화면.

---

## 8. 구현 단계

| 단계 | 내용 | 근거 |
|---|---|---|
| **P0** | 3경로 연결 + 모듈 저장 버그 수정 (`form.js` 미선언 `settings`, `flow.flow_blogs`→`blog_links`, `flows_execute` keyword 분기), 전 블로그 순회, `promoted` 플래그 분리 | 검토서 D-1~D-4, D-6 |
| **P1** | 재고 계산·생성 조회 조건 통일, 품질 관문 통과(필터→분류→유사도), 미분류 회수 큐 | 검토서 D-5, D-7 |
| **P2** | 스키마 분리(`keywords`/`keyword_metrics`/`keyword_clusters`), 월간 발행량 지표, 검색량 상한 | 벤치마크 B2, B4 |
| **P3** | 멀티 소스 수집 — GSC Search Analytics(P1급 가치) → 구글/네이버 자동완성 → Planner/Trends | §4-3 |
| **P4** | 클러스터 생산(필러+서브), 의도 분류, fan-out 질문 전개, FAQ 스키마 연계 | 벤치마크 B4, B6 |
| **P5** | 멀티 엔진 노출 보강(E1~E5) + 성과 되먹임(§6-3) | §5-3 |

> P0 는 "지금 안 도는 것을 돌게" 하는 최소 수정이고, P2 이후가 실제 재설계다.
> P0 없이 P2 를 하면 검증할 실행 경로가 없다.

---

## 8-1. 구현 현황 (2026-09-01 · P0~P5 완료)

| 단계 | 상태 | 무엇이 들어갔나 | 주요 파일 |
|---|---|---|---|
| **P0** | ✅ | 모듈 저장 버그(미선언 변수) 수정 · 오토런 `flow.flow_blogs`→`blog_links` · 플로우 단일/백그라운드 실행 분기 · 전 블로그 순회 · `promoted`/`titled` 분리 · 블로그별 후보 격리 | `058` · `runner.run_for_blogs` · `flows_execute` · `flow_scheduler` · `modules/form.js` |
| **P1** | ✅ | 제목이 금지어 필터→분류→유사도 그룹핑을 통과 · 미분류는 `temp_titles` 회수 큐 · 재고 카운트를 생성 조회와 동일 함수로 통일 · 목표재고 = 발행실적×리드타임×안전계수 | `title_gate.py` · `inventory.py` · `inventory_category_mixin.py` |
| **P2** | ✅ | `keyword_metrics`(엔진별 1:N) · 공급을 **최근 30일 발행량**으로 전환(최신순 100건 표본, capped 표시) · 검색량 **상한** · 수집/측정 기준 통일 | `059` · `supply.py` · `metrics.py` · `scoring.py` |
| **P3** | ✅ | 자동완성(구글·네이버) · **서치콘솔 실측 쿼리** · 키워드플래너(구간값 표시) · 트렌드 · 소스 실패 격리 · 검색량 보강 | `sources/` · `ingest.py` |
| **P4** | ✅ | 검색 의도 7종 규칙 분류 · 토큰 겹침 클러스터링 · `keyword_clusters` · **대표 글 1편 + 곁가지 N편** 프롬프트(fan-out 질문) | `060` · `intent.py` · `clustering.py` · `cluster_builder.py` |
| **P5** | ✅ | 블로그별 타깃 엔진(`seo_config`) · 플랫폼 제약 경고(블로거×네이버) · 네이버 준비 상태 점검표 · **성과 되먹임**(노출·순위 → 시드 순서) | `061` · `engines.py` · `feedback.py` · `naver_readiness.py` |

**마이그레이션**: 058 → 059 → 060 → 061 (head=061). SQLite 스크래치 DB로 업/다운 왕복 검증.
**테스트**: 키워드 모듈 관련 신규 201건 통과. 전체 회귀 대비 **신규 실패 0건**
(기존 실패 43건은 손대지 않은 영역의 선행 문제).

### 아직 안 한 것
- SERP 오버랩 클러스터링(1차는 토큰 겹침으로 대체 — §9-4)
- 네이버 연관검색어 수집(결과 페이지 파싱이라 차단 위험 — 자동완성만 넣음)
- 블로그 편집 화면의 타깃 엔진 UI(현재는 키워드 관리 화면에서 설정)
- 서버 배포(로컬 커밋까지만 — 마이그레이션 4건이 포함돼 사용자 확인 후 진행)

---

## 9. 미결정 항목 / 리스크

1. **월간 발행량 측정 방법** — 네이버 검색 API에 기간 필터가 없다. `sort=date` + 날짜 컷으로
   최근 30일 건수를 세는 방식의 정확도·호출비용 검증 필요. 구글은 대체 지표 설계 필요.
2. **자동완성 수집 안정성** — 구글·네이버 모두 공식 API 가 아니다. 호출 간격·차단 대응·
   실패 시 degrade 정책을 정해야 한다.
3. **Keyword Planner 구간값** — 절대값으로 쓰면 안 된다. 정렬·필터 용도로 한정하고,
   절대 기준(하한·상한)은 네이버 지표 또는 GSC 실측에 건다.
4. **SERP 오버랩 클러스터링 비용** — 키워드마다 검색 결과가 필요해 호출량이 크다.
   1차는 보유 중인 `similarity_matcher_service`(임베딩/토큰) 로 묶고, 상위 후보에만 SERP 적용.
5. **GSC 사이트 등록 전제** — Search Analytics 는 등록·소유확인된 사이트만 조회된다.
   미등록 블로그는 이 소스를 못 쓰므로 폴백 경로가 필요하다.
6. **네이버 노출 리드타임 14~16일** — 되먹임 루프의 주기를 이보다 길게 잡아야 한다.
7. **회귀 위험** — `main_titles` 진입 경로를 바꾸므로 `docs/claude/REGRESSION_PREVENTION.md`
   기준 영향 범위 분석 선행 필수(발행·재고·유사도 그룹핑 전반).

---

## 10. 출처 (이번 차수 추가분)

- [플러스제로 키워드도구 — 네이버/구글 키워드검색량 조회](https://keywordsearch.pluszero.co.kr/naver) · [로워드](https://loword.co.kr/) · [네이버·구글 키워드 검색량 조회 방법(로워드)](https://bkgroup30.com/%EB%84%A4%EC%9D%B4%EB%B2%84-%EA%B5%AC%EA%B8%80-%ED%82%A4%EC%9B%8C%EB%93%9C-%EA%B2%80%EC%83%89%EB%9F%89-%EC%A1%B0%ED%9A%8C-%EB%A1%9C%EC%9B%8C%EB%93%9C/) · [네이버 키워드 검색량 조회 툴 정리](https://inside.ampm.co.kr/insight/13229) — 국내 도구의 구글·네이버 동시 지원
- [How to Use Google Autocomplete API for Your Keyword Research Tool — DataForSEO](https://dataforseo.com/blog/google-autocomplete-api-for-keyword-research-tool) · [Google Autocomplete Scraper — Apify](https://apify.com/automation-lab/google-autocomplete-scraper) · [Keyword Research Tool (GitHub)](https://github.com/hassancs91/Keyword-Research-Tool) · [MLforSEO 구현 가이드](https://www.mlforseo.com/machine-learning-implementation-guides/keyword-research/how-to-use-google-autocomplete-apis-for-keyword-suggestions/) — 구글 suggest 엔드포인트 기반 확장 방식
- [How Accurate is Google Keyword Planner?](https://medium.com/@raihanrasel806/how-accurate-is-google-keyword-planner-the-truth-unveiled-5f2f02dfab38) · [Beyond Google Keyword Planner — searchvolume.io](https://searchvolume.io/resources/google-keyword-planner-alternative-tools) · [Inaccurate search volumes — Ellipsis](https://getellipsis.com/blog/search-volumes/) — 구간값·묶음 합산 한계
- [워드프레스 네이버 서치어드바이저 등록 A to Z — 은별월드](https://eunbyeol.co.kr/blog/web-master/seo-naver-search-advisor-site-index-register/) · [네이버 웹마스터도구 등록 가이드 — webdot](https://webdot.co.kr/guide/%EB%84%A4%EC%9D%B4%EB%B2%84-%EC%84%9C%EC%B9%98%EC%96%B4%EB%93%9C%EB%B0%94%EC%9D%B4%EC%A0%80-%EB%93%B1%EB%A1%9D-%EB%B0%A9%EB%B2%95-%EB%8B%A8%EA%B3%84%EB%B3%84-%EA%B0%80%EC%9D%B4%EB%93%9C) · [워드프레스 사이트 네이버 노출](https://sundryinfo.com/) — 소유확인·사이트맵·RSS·노출 리드타임
- [네이버 서치어드바이저 IndexNow 지원 — GeekNews](https://news.hada.io/topic?id=19225) · [워드프레스 IndexNow 자동 색인요청 — dobiho](https://dobiho.com/68631/) · [IndexNow 등록하기(Naver, Bing) — PromleeBlog](https://www.promleeblog.com/blog/post/184-indexnow) · [네이버 전용 인덱스나우 플러그인 — 워드프레스 정보꾸러미](https://www.thewordcracker.com/basic/%EB%84%A4%EC%9D%B4%EB%B2%84-%EC%A0%84%EC%9A%A9-%EC%9D%B8%EB%8D%B1%EC%8A%A4%EB%82%98%EC%9A%B0-%ED%94%8C%EB%9F%AC%EA%B7%B8%EC%9D%B8-%EC%97%85%EB%8D%B0%EC%9D%B4%ED%8A%B8/) — 네이버·빙 동시 색인 통보, 구글 미참여
- [네이버 스마트블록 변화와 SEO 대응 — 오픈애즈](https://www.openads.co.kr/content/contentDetail?contsId=13050) · [네이버 블로그 영역에 워드프레스를 검색되게 하는 방법 — 워드프레스 정보꾸러미](https://www.thewordcracker.com/basic/%EB%84%A4%EC%9D%B4%EB%B2%84-%EB%B8%94%EB%A1%9C%EA%B7%B8-%EC%98%81%EC%97%AD%EC%97%90-%EC%9B%8C%EB%93%9C%ED%94%84%EB%A0%88%EC%8A%A4-%EC%82%AC%EC%9D%B4%ED%8A%B8%EB%A5%BC-%EA%B2%80%EC%83%89/) · [스마트블록 인기글과 SEO — TBWA](https://seo.tbwakorea.com/blog/naver-smartblock-and-seo/) — 외부 사이트는 웹사이트 탭, 스마트블록은 세분 주제 단위
