# 통합 테스터(휘발성 플로우) 타당성 검토

> 작성 2026-09-14 · 코드 수정 없음, 검토 보고

## 0. 결론

**가능합니다. 그리고 새로 만들 것이 거의 없습니다.**

제안하신 "테스트 페이지가 하나의 플로우가 된다"는 구조가 **이미 코드에 있습니다.**
다만 **아무도 부르지 않아 화면에 없을 뿐**입니다.

| 확인 항목 | 결과 |
|---|---|
| 모듈 타입별 실행 디스패치 | **있음** — `execute_flow_now()` |
| 그 함수의 호출처 | **없음 (고아 함수)** |
| 실사용 "1회 실행" | **없음** — start/pause/resume/stop 뿐 |
| dry_run 지원 | 키워드·제목은 **있음**, 생성은 부분 |
| 휘발성 실행 | 변형 필요 (작음) |

---

## 1. 핵심 발견 — 완성됐는데 노출이 안 된 함수

`app/scheduler/flow_scheduler.py:630`

```python
async def execute_flow_now(self, flow_id: int,
                           action_type: str = "republish") -> Dict[str, Any]:
    """플로우 즉시 실행 (수동) - 모듈 방식"""
```

이 안에 **모든 모듈 타입의 실행 분기가 모여 있습니다.**

| action_type | 호출 |
|---|---|
| `collect` / `bulk_collect` | 수집 실행 |
| `data` | `_execute_data_module` |
| `generate` / `prompt` | `_execute_generate_module` → `FlowGenerateExecutor` |
| `keyword` | `_execute_keyword_module` |
| `title_gen` | `_execute_title_module` |
| `contact_form` | `_execute_contact_form_module` |
| `republish` | `_execute_republish_action` |

**그런데 전체 코드베이스에서 이 함수를 부르는 곳이 없습니다.**

```
$ grep -rn "execute_flow_now" app/
app/scheduler/flow_scheduler.py:630:    async def execute_flow_now(
```

실사용 경로인 `autorun_service.execute_flow_action()` 은 `start/pause/resume/stop`
만 처리합니다. **"지금 한 번 돌려봐"가 실제로 없었습니다.**

→ **테스트 페이지는 이 함수를 부르는 껍데기면 됩니다.** 실행 로직을 새로 쓰지
않습니다.

---

## 2. "휘발성 플로우"를 어떻게 만드나

`execute_flow_now` 는 `flow_id` 로 DB에서 플로우를 읽습니다. 저장하지 않는
플로우를 돌리려면 이 지점만 바꾸면 됩니다.

### 방안 비교

| 방안 | 방법 | 평가 |
|---|---|---|
| A. 임시 Flow 생성 후 삭제 | DB에 만들고 끝나면 지움 | 중간에 죽으면 쓰레기가 남음 |
| B. **메모리 플로우 주입** | 조립한 객체를 함수에 직접 넘김 | **권고** |
| C. 전용 Flow 고정 | 테스트 플로우 하나를 두고 링크만 교체 | 동시 사용 시 충돌 |

**B를 권고합니다.** 변경은 한 줄 수준입니다.

```python
async def execute_flow_now(self, flow_id: int, action_type: str = "republish",
                           flow: Optional[Flow] = None,      # 추가
                           dry_run: bool = False) -> Dict:   # 추가
    ...
    flow = flow or await self._get_flow_with_modules(db, flow_id)
```

화면에서 고른 모듈·블로그로 **SQLAlchemy 객체를 메모리에서 조립해 넘깁니다.**
`Flow(id=0, module_links=[...], blog_links=[...])` 형태라 DB에 붙지 않습니다.

기존 호출부가 없으므로 **회귀 위험도 사실상 없습니다.**

---

## 3. 부작용을 어디서 막나

"반영 안 하면 휘발"을 지키려면 저장 지점을 알아야 합니다. 세 층입니다.

### 3-1. 실행 기록 (공통, 막기 쉬움)

`execute_flow_now` 안에 둘뿐입니다.

```python
await self._save_autorun_log(...)          # 오토런 로그
state.record_execution(result.get("success"))   # 실행 상태 카운터
```

`dry_run` 이면 이 둘을 건너뛰면 끝입니다. **다른 플로우 통계를 오염시키지
않는 게 여기서 확보됩니다.**

### 3-2. 모듈별 데이터 쓰기 (모듈마다 다름)

| 모듈 | dry_run | 근거 |
|---|---|---|
| `title_gen` | **있음** | `title_gen/runner.py` 9곳 |
| `keyword` | **있음** | `title_maker.py` 9곳, `title_gate.py` 5곳 |
| `data` (제목 이관) | **있음** | `title_collect/workbench.py` 3곳 |
| `generate` / `prompt` | **부분** | 아래 참조 |
| `contact_form` | 없음 | 외부 서비스(Tally) 생성 — **테스트 제외 권고** |
| `republish` | 없음 | 실제 블로그 수정 — **테스트 제외 권고** |

`TitleGate.admit(titles, row, dry_run=True)` 처럼 **이미 판정만 하고 저장하지
않는 경로가 만들어져 있습니다.** 키워드·제목 모듈은 그대로 쓰면 됩니다.

### 3-3. 생성 모듈 — 여기가 유일한 난점

`generate` 는 `FlowGenerateExecutor` 를 타는데 이쪽엔 `dry_run` 이 없습니다.
대신 **별도 테스터가 따로 있습니다.**

```
app/services/generation/pipeline_full_tester.py  (163줄)
  → 7단계: 제목선택 → 재조합 → 참조수집 → 생성 → 이미지 → HTML → 발행
```

**문제는 경로가 둘로 갈린다는 점입니다.**

```
실제:   flow_scheduler → FlowGenerateExecutor → ContentGenerator
테스트: pipeline_full_tester → PipelineTester → 각 단계 개별 호출
```

**"테스트는 됐는데 실제는 다르다"가 여기서 생깁니다.** 실제로 어제 넣은
프롬프트 로테이션은 `FlowGenerateExecutor._apply_rotation()` 에 붙어 있어
**`pipeline_full_tester` 로는 검증되지 않습니다.**

→ 이 검토에서 가장 중요한 지점입니다. §6에서 다시 다룹니다.

---

## 4. 화면은 기존 가지 안에 들어갑니다

새 개념을 만들지 않고 기존 용어를 그대로 씁니다.

```
플로우 ─┬─ 목록        (기존)
        ├─ 편집        (기존)
        └─ 테스트 ★    (신설 — 저장 안 되는 플로우)
```

**조작 흐름도 기존과 같습니다.**

| 기존 플로우 | 테스트 플로우 |
|---|---|
| 모듈 추가 | 모듈 추가 (메모리) |
| 블로그 연결 | 블로그 연결 (메모리) |
| 오토런 등록 → 스케줄 실행 | **[실행] 버튼 → 즉시 1회** |
| 결과가 DB에 저장 | **결과가 화면에만** |
| — | **[반영] 누르면 그때 저장·발행** |

화면 배치 제안입니다.

```
┌─ 좌: 모듈 구성 ──┬─ 중: 실행·결과 ────┬─ 우: 미리보기 ─┐
│ 블로그 선택       │ 단계별 실행 버튼     │ HTML / 렌더    │
│ 모듈 추가/순서    │ 로그·소요시간       │ 커버 이미지     │
│                 │ 중간 산출물 편집     │ 버튼·고지문     │
│ 소스 수집 패널 ★  │                   │               │
│  지식인·카페 목록 │ [단계] [전체]       │ [반영] [폐기]  │
└─────────────────┴────────────────────┴───────────────┘
```

**소스 수집 패널만 새 요소입니다.** 나머지는 기존 화면의 재배치입니다.
그리고 이 패널이 쓸 수집기는 **어제 만든 `community.py`(지식iN·카페)가
그대로 들어갑니다.**

---

## 5. 필요한 작업량

| 항목 | 내용 | 난이도 |
|---|---|---|
| `execute_flow_now` 에 `flow`·`dry_run` 인자 | 2줄 + 분기 2곳 | **낮음** |
| 실행 라우트 신설 | `POST /api/v1/flows/test/execute` | **낮음** |
| 메모리 플로우 조립 | 신규 모듈 (~100줄) | 낮음 |
| 테스트 화면 | 3단 레이아웃 | 중간 |
| 소스 수집 패널 | `community.py` 호출 + 목록 UI | 낮음 |
| 미리보기 | `_markdown_to_html` + 블로그 CSS 주입 | 중간 |
| 중간 산출물 편집 | 제목·본문·체크리스트 수정 후 재실행 | **중간** |
| 반영(저장/발행) | 기존 발행 경로 재사용 | 중간 |
| **생성 경로 통합** | §6 | **높음** |

**"생성 경로 통합"만 빼면 전부 조립 수준입니다.**

---

## 6. 짚어야 할 위험 셋

### 6-1. 생성 경로가 둘이면 테스트가 거짓말을 합니다 ★

`pipeline_full_tester` 를 그대로 쓰면 **실제 발행 경로와 다른 코드를 검증**하게
됩니다. 어제 넣은 로테이션이 이미 그 상태입니다.

**두 선택지가 있습니다.**

| 선택 | 내용 | 대가 |
|---|---|---|
| A | 테스트도 **`FlowGenerateExecutor` 를 타게** 하고 그쪽에 `dry_run` 추가 | 실제 경로 수정(회귀 위험) |
| B | `pipeline_full_tester` 를 계속 쓰고 차이를 감수 | 검증이 헐거워짐 |

**A를 권고합니다.** 테스터의 존재 이유가 "실제로 어떻게 도는지 보는 것"인데
다른 코드를 돌리면 의미가 없습니다. 다만 `FlowGenerateExecutor` 는 운영 중인
경로라 **`dry_run` 추가는 신중히** 해야 합니다.

### 6-2. Celery 분기

`execute_flow_now` 의 `data` 액션은 `_use_celery()` 결과에 따라 **큐에 넣고
바로 반환**합니다. 테스트에서 이러면 결과를 못 봅니다.

→ **테스트 실행은 Celery를 타지 않고 동기로 강제**해야 합니다.

### 6-3. 발행은 되돌릴 수 없습니다

"반영"을 누르면 실제 블로그에 올라갑니다. **되돌리기가 없습니다.**

- 반영 전 **확인 단계**를 두는 게 맞습니다
- 발행 대신 **발행대기글로 저장**하는 선택지도 함께 두면 안전합니다
- `contact_form`(Tally 생성)과 `republish`(기존 글 수정)는 **테스트 대상에서
  빼는 것**을 권고합니다. 외부에 즉시 반영되고 dry_run이 없습니다

---

## 7. 남는 결정거리

1. **생성 경로 통합(6-1)** — A로 갈지 B로 갈지
2. **반영의 기본값** — 발행인지 발행대기글 저장인지
3. **모듈 구성 저장** — 테스트 구성을 나중에 다시 쓰려면 저장이 필요한데,
   "휘발"과 충돌합니다. **구성만 저장하고 결과는 휘발**이 절충안입니다
4. **테스트 대상 모듈 범위** — `contact_form`·`republish` 제외 여부

---

## 8. 요약

- 제안하신 구조는 **이미 코드에 있습니다.** `execute_flow_now` 가 완성돼 있고
  **아무도 부르지 않습니다**
- "저장 안 되는 플로우"는 **메모리 객체 주입**으로 됩니다. 변경은 두 줄 수준
- 실행 기록 오염은 **저장 지점 2곳**만 막으면 끝납니다
- 키워드·제목·데이터 모듈은 **이미 dry_run 이 있습니다**
- 소스 수집 패널은 **어제 만든 `community.py`** 가 그대로 들어갑니다
- **유일한 난점은 생성 경로가 둘로 갈려 있다는 것**입니다
- `contact_form`·`republish` 는 테스트 대상에서 빼는 것을 권고합니다
