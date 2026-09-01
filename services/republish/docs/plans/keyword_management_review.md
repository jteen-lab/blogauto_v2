# 키워드 관리 — 현행 구현 재검토 보고서

> 작성일: 2026-09-01 | 상태: **검토만 수행, 코드 수정 없음**
> 대상 커밋: 7862748 ~ abc9f02 (키워드랩 → 키워드 모듈 승격 8커밋)

## 0. 결론 요약

1. **모듈화는 절반만 됐고, 그 절반도 저장이 안 된다.** 모듈 관리에 키워드 폼은 있으나
   저장 시 JS 예외(`ReferenceError`)가 나 모듈이 만들어지지 않는다. 사용자가
   "모듈 관리에 존재하지 않는다"고 본 것이 정확한 관찰이다.
2. **오토런(스케줄러) 경로는 100% 실패한다.** `flow.flow_blogs` 라는 없는 속성을 읽어
   매 회차 예외로 끝난다. 플로우 실행(수동/백그라운드) 경로에는 분기 자체가 없다.
3. **생산량 설계가 대량 발행 규모와 맞지 않는다.** 회차당 실질 산출이 한 자릿수~수십 편이고,
   그나마 만든 제목의 다수가 카테고리 미분류라 **생성 대상 조회에서 영구 제외**된다.
4. **기존 파이프라인을 승계한 게 아니라 우회했다.** 금지어 필터·유사도 그룹핑·제목 이관
   (temp→main) 관문을 모두 건너뛰고 `main_titles` 에 직접 꽂는다.

---

## 1. 현재 구현 실태 지도

| 구성요소 | 위치 | 상태 |
|---|---|---|
| 후보 테이블 | `app/models/keyword_candidate.py`, `alembic/056` | 있음 |
| 모듈 타입 등록 | `alembic/057` (`module_types.code='keyword'`) | 있음 |
| 수집·측정·판정 | `app/services/keyword_lab/{service,scoring}.py` | 동작 |
| 시드 확장 | `app/services/keyword_lab/expander.py` | 동작 |
| 한 회차 실행기 | `app/services/keyword_lab/runner.py` | 동작(직접 호출 시) |
| 제목 생성 | `app/services/keyword_lab/title_maker.py` | 동작(품질 관문 없음) |
| 전용 화면 | `/keyword-lab`, `app/static/js/keyword_lab/app.js` | 동작 |
| 모듈 관리 폼 | `app/static/js/modules/keyword-form-template.js` | **저장 불가** |
| 플로우 실행 | `app/routers/flows_execute.py` | **분기 없음** |
| 오토런 스케줄러 | `app/scheduler/flow_scheduler.py:2107` | **항상 예외** |
| 순서도 | `docs/flowcharts/keyword_lab.md`, `keyword_module.md` | **파일 없음** |

즉 실제로 살아 있는 실행 경로는 **`/keyword-lab` 화면의 버튼 하나뿐**이다.
사용자가 지적한 "키워드 관리 안에 모듈 한 회차 실행 버튼만 생겼다"는 서술 그대로다.

---

## 2. 요청과 어긋난 부분 (설계 차원)

### 2-1. "모듈에서 테스트 → 플로우에서 실행" 구조가 뒤집혔다
요청한 형태는 프롬프트/생성 모듈과 같다 — **모듈 안에서 테스트하고, 플로우에 얹어 돌린다.**
현재는 반대로 **별도 화면 안에 실행 버튼**이 있고 모듈은 설정 껍데기다.
- 프롬프트 모듈은 `_prompt_test_panel.html` 로 모듈 편집 화면 안에서 테스트한다.
- 키워드 모듈에는 그 대응물이 없고, 대신 `/keyword-lab` 이 실행 주체가 됐다.
- 모듈 단일 실행 API(`flows_execute.py:2252`)는 `keyword` 를
  "지원하지 않는 모듈 타입" 으로 400 처리한다.

### 2-2. 블로그 1개만 처리한다
`flow_scheduler.py:2123` 은 플로우에 연결된 블로그 중 **첫 번째만** 쓴다.
12개 블로그를 물린 플로우에서도 1개 블로그 니치로만 수집한다.
`keyword_lab.py:118` 의 수동 실행도 `settings["blogs"][0]` 로 같다
(게다가 모듈 폼은 `blogs` 를 저장조차 하지 않는다).

### 2-3. 기존 자산을 승계하지 않고 분리했다
모델 주석이 "기존 `seed_keywords` 를 건드리지 않는다"고 명시한다. 실험 단계에선 맞는 판단이나,
요청은 **승계**였다. 결과적으로 지금은 두 계통이 병존한다.

| 축 | 기존 수집(collect/bulk_collect) | 키워드 모듈 |
|---|---|---|
| 키워드 저장소 | `seed_keywords` / `collected_keywords` | `keyword_candidates` (별도) |
| 제목 경로 | `temp_titles` → 필터·분류·유사도 → `main_titles` | `main_titles` 직접 삽입 |
| 금지어 필터 | `ContentFilter` 적용(`keyword_collector_service.py:114`) | **미적용** |
| 유사도 그룹핑 | `title_transfer_service` 가 그룹 생성 | **미적용**(group_id NULL) |
| 카테고리 분류 | 이관 시 분류 + 재분류 도구 존재 | 수집 시 1회, 실패 시 NULL 고정 |

---

## 3. 지금 동작하지 않는 결함 (증거 기반)

### 🔴 D-1. 모듈 관리에서 키워드 모듈을 저장할 수 없다
`app/static/js/modules/form.js:881-900`
```js
} else if (this.formData.type_code === 'keyword') {
    settings.keyword = { ... };          // ← settings 가 선언된 적 없음
    settings.schedule = { interval_minutes: k.interval_minutes };
}
```
`prepareRequestData()` 스코프에 `settings` 선언이 없다(`const settings` 는 340행
`initializeSettings()` 안의 지역 변수다). 비-strict 클래식 스크립트라
**`ReferenceError: settings is not defined`** 로 저장이 중단된다.
게다가 `data.settings` 에 대입하는 줄도 없어, 예외를 고쳐도 설정이 전송되지 않는다.
→ **사용자가 본 "모듈 관리에 키워드 모듈이 없다"의 직접 원인.**

### 🔴 D-2. 오토런 실행이 항상 예외로 끝난다
`app/scheduler/flow_scheduler.py:2123`
```python
blog_ids = [fb.blog_id for fb in (flow.flow_blogs or [])]
```
`Flow` 모델의 관계명은 `blog_links` 다(`app/models/flow.py:64`). `flow_blogs` 는 테이블명일 뿐
속성이 아니다 → `AttributeError` → 상위 `except` 가 삼켜 `{"success": False}` 로만 남는다.
스케줄 등록·간격 계산(`flow_scheduler.py:299`)은 정상이라 **매 6시간 조용히 실패**한다.

### 🔴 D-3. 플로우 실행 경로에 분기가 없다
`app/routers/flows_execute.py` 의 백그라운드 플로우 실행은 `collect / prompt / generate /
data / bulk_collect / contact_form / growth_profile` 만 처리한다. `keyword` 는 없다.
플로우 편집 화면에는 "키워드" 탭이 있어 **선택은 되지만(`flows/_form.html:95`) 실행되지 않는다.**

### 🟠 D-4. 채택 키워드는 제목을 못 받는다 (`promoted` 플래그 충돌)
- `expander.pick_seeds()` — 채택 키워드를 시드로 쓰고 `row.promoted = True`
- `title_maker._targets()` — `promoted.is_(False)` 인 것만 제목 생성 대상

실행기는 `collect → measure → titles` 순서다(`runner.py:70`). 즉 **검색량 상위 채택 키워드가
시드로 소비되면서 제목 대상에서 빠진다.** 가장 좋은 키워드일수록 제목이 안 만들어진다.

### 🟠 D-5. 만든 제목의 대부분이 생성에 안 잡힌다
`title_maker._save()` 는 `topic_id/subtopic_id` 를 후보에서 그대로 물려받는다.
그런데 분류 성공률은 코드 주석 기준 **약 18%**(`service.py:_classify`).
`inventory_trigger.find_available_titles()` 는 블로그에 카테고리가 설정돼 있으면
`subtopic_id IN (...)` / `topic_id IN (...)` 조건을 걸고, 전체 폴백은
**카테고리 미설정 블로그에만** 허용한다(`inventory_trigger.py:186`).
→ 미분류(NULL) 제목은 정상 운영 블로그에서 **영구 사장(死藏) 재고**가 된다.

동시에 `runner._inventory()` 도 블로그 활성 카테고리로 필터해 센다.
→ 미분류 제목을 아무리 만들어도 재고 카운트가 안 오르고, `min_inventory` 게이트가 계속 열려
**매 회차 API를 태우며 사장 재고만 늘린다.**

### 🟠 D-6. 블로그 2번째부터는 수집이 0건이 된다
`keyword_candidates` 는 `UniqueConstraint(user_id, keyword)` 이고
`_existing_keywords()` 는 사용자 전역으로 조회한다.
→ 블로그 A가 먼저 잡은 키워드는 블로그 B에서 영원히 재수집 불가.
`blog_id` 도 먼저 잡은 블로그로 고정돼, 결과적으로 **제목도 그 블로그 몫으로만** 생긴다.
`saved==0 && errors==[]` 이면 `success: True` 로 끝나 화면엔 "0개 수집"만 뜬다.

### 🟡 D-7. 품질 관문 전면 우회
`title_maker._save()` 는 `MainTitle` 을 직접 `add` 한다.
- `ContentFilter`(금지어/제외 패턴) 미적용
- 유사도 그룹핑 미적용 → `group_id` NULL, 비슷한 제목이 무한 누적
- 중복 검사는 `title` 완전일치 1건뿐 → 어미만 다른 제목은 전부 통과
- `risk_label`(고객센터·시간표·채용조건 등)은 후보 단계에서만 보고, `hold` 판정을 받아도
  제목 생성 대상은 `adopt` 만이라 결과적으로 막히긴 하나, 반대로 **회색지대 키워드를
  사람이 검토할 큐가 화면에만 있고 워크플로우에는 없다.**

### 🟡 D-8. 판정 기준이 두 곳에서 다르게 적용된다
- 수집 시점 `service._build()` → `judge(keyword, volume, None)` : **기본 임계값**(100/0.2) 사용
- 측정 시점 `service.measure()` → `Thresholds.build(cfg.min_volume, cfg.min_saturation)` 사용

모듈에서 `min_volume=300` 으로 잡아도 수집 단계는 100 기준으로 `reject` 를 찍는다.
`reject` 는 이후 재판정 전까지 유지되므로 설정이 의도대로 안 먹는다.

### 🟡 D-9. 제목이 두 번 가공된다
`title_maker` 가 AI로 제목을 짓고, 생성 시점에 `title_recombiner` 가 그 제목을 다시 AI로
재조합한다. 키워드를 살려 만든 제목이 재조합 단계에서 변형돼 **수요 근거가 희석**된다.
또한 제목 프롬프트가 하드코딩(`title_maker.PROMPT`)이라 F4 니치·F7 정보이득·애드센스 프리셋 등
모듈 단위 프롬프트 체계와 완전히 분리돼 있다.

### 🟡 D-10. 순서도 없음 (CLAUDE.md 규칙 4 위반)
`keyword_lab.md`, `keyword_module.md` 를 6개 파일이 참조하지만 `docs/flowcharts/` 에 없다.

---

## 4. 대량 생성 관점의 산출량 검증

기본값(`settings.py`) 기준 1회차:

```
시드 10개 × (원형 1 + 수식어 5) = 조회 키워드 60개
  → 검색광고 API 12회 (5개씩 묶음)
  → 저장 상한 collect_limit=100
  → 문서수 측정 measure_limit=50   ← 병목: 저장 100 vs 측정 50, 매 회차 미측정분 누적
  → 제목 대상 상한 20개 키워드 × 3편 = 최대 60편
```
여기에 채택률(검색량 100↑ AND 포화도 0.2↑)과 D-4(상위 키워드 시드 소비),
D-5(미분류 사장)를 곱하면 **블로그 1개당 실사용 가능 제목은 회차당 한 자릿수**로 떨어진다.
6시간 주기 × 블로그 1개 처리(D-2) 구조로는 12개 블로그 대량 발행 수요를 못 받친다.

`min_inventory=30` 도 근거가 없다. 발행 주기(성장 프로파일)와 곱해 **소진 속도 기준**으로
정해야 하는데 지금은 고정 상수다.

---

## 5. 보완 방향 (재설계 시 지켜야 할 축)

### 5-1. 모듈 계약을 다른 모듈과 동일하게
- 모듈 관리 안에서 **① 설정 → ② 테스트 실행(미리보기) → ③ 저장** 이 닫히게 한다.
  (프롬프트 모듈 `_prompt_test_panel.html` 패턴 승계)
- 실행 주체는 **플로우**로 옮긴다: `flows_execute.py` 단일 실행 + 백그라운드 플로우 +
  `flow_scheduler` 오토런, 세 경로 모두에 `keyword` 분기를 넣고 **같은 실행기**를 호출.
- `/keyword-lab` 화면은 "실행 콘솔"이 아니라 **후보 열람·검수·수동 승격 화면**으로 성격을 바꾼다.
- 블로그 스코프는 `flow_module_blog_scope` 규약을 따라 **연결된 모든 블로그**를 순회.

### 5-2. 재고를 블로그·니치 단위 목표치로 관리
- `min_inventory` 를 상수가 아니라 **"성장 프로파일 발행량 × 안전계수 × 리드타임"** 으로 산출.
- 재고 계산 대상을 "그 블로그가 실제로 꺼낼 수 있는 제목"과 일치시킨다
  (= `inventory_trigger` 와 동일한 카테고리 조건 사용). 지금은 계산식이 서로 다르다.
- 부족한 니치를 먼저 채우는 **결핍 우선 큐**로 시드를 고른다(현재는 카테고리 순회).

### 5-3. 키워드 1개 → 제목 N개의 "확장 축"을 명시적으로 설계
단일 키워드 1제목은 대량 발행에 부적합하다는 지적이 맞다. 확장 축 후보:
- **검색 의도 축**: 정보형/비교형/방법형/후기형/문제해결형 → 키워드 1개에서 의도별 제목
- **롱테일 축**: 연관키워드를 제목 소재가 아니라 **묶음(클러스터)** 으로 보고,
  클러스터 1개 = 필러 글 1편 + 서브 글 N편 (토픽 클러스터 구조)
- **자동완성/연관검색어 축**: 검색광고 연관키워드만으로는 최신성이 약하다.
  자동완성·연관검색어·질문형 쿼리 수집 경로 추가 검토
- **시의성 축**: 기존 수집이 이미 보유한 트렌드 소스(구글 트렌드/데이터랩/뉴스)를
  **폐기하지 말고 키워드 모듈의 입력 소스로 승계**

### 5-4. 품질 관문을 우회하지 말고 통과시키기
제목 산출물이 `main_titles` 로 바로 가는 대신 **기존 관문을 태운다**:
```
키워드 후보(수요 검증)
  → 제목 생성/수집
  → ContentFilter(금지어)  →  카테고리 분류  →  유사도 그룹핑
  → main_titles (available)
```
분류 실패분은 NULL로 방치하지 말고 **미분류 큐 + 분류표 보강 루프**로 회수한다
(현재 분류율 18%가 병목의 실체다).

### 5-5. 제목 가공 단계 정리
- 키워드 모듈이 제목을 만들면 `title_recombiner` 는 **건너뛰거나**(source 기준 분기),
- 반대로 키워드 모듈은 "제목 소재(키워드+의도)"만 넘기고 **제목 문장은 생성 모듈이 담당**하도록
  역할을 하나로 정한다. 지금처럼 두 곳이 각자 AI를 부르면 비용·품질이 모두 샌다.

### 5-6. 벤치마킹에서 확인할 항목 (자료 수집 시 이 축으로)
현행 판정은 `검색량 ÷ 문서수` 단일 지표다. 국내 도구들이 쓰는 축과 비교 검증 필요:
- 검색량(PC/모바일 분리), **월간 발행량**(문서수와 다름 — 최신성 지표),
- 포화지수/경쟁강도, 광고 경쟁도(compIdx), 상위노출 문서의 성격(체험단/상업성),
- 계절성·트렌드 기울기, 그리고 **제목 생성 방식**(단일 제목 vs 클러스터 vs 의도별 확장).

---

## 6. 다음 단계 제안

1. **재설계 계획서 작성** — 위 5장을 순서도(`docs/flowcharts/keyword_module.md`)와 함께 확정.
2. **벤치마킹 자료 수집** — 5-6 축으로 정리해 블로그오토 접목 가능 항목 선별.
3. **구현 순서(안)**
   - P0: D-1/D-2/D-3 (모듈 저장·오토런·플로우 실행 3경로 연결) — 지금은 아예 안 도는 상태
   - P1: D-4/D-6 (플래그 분리, 블로그별 스코프)
   - P2: D-5/D-7 (분류·필터·유사도 관문 통과, 재고 계산 일치)
   - P3: 5-3 확장 축(클러스터/의도) — 대량 생성 대응
4. **회귀 확인 필수** — `main_titles` 직접 삽입 경로를 바꾸므로
   `docs/claude/REGRESSION_PREVENTION.md` 기준 영향 범위 분석 선행.

> 본 문서는 검토 결과만 담는다. 코드 수정은 별도 승인 후 진행한다.
