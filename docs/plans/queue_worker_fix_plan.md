# 큐/워커 시스템 ON/OFF 로직 통합 수정 계획서

> **버전**: v1.0.0 | **작성일**: 2026-04-19
> **대상 시스템**: blogauto_v2/services/republish
> **목표**: 큐 ON 모드가 OFF 모드와 동일한 공통 로직을 사용하도록 통합하여, ON/OFF 모드 전환 시 기능 결과가 동일하게 동작하도록 보장

---

## 1. 문제 요약

### 1.1 현재 상태

큐 시스템 OFF(직접 실행)일 때는 정상 동작하지만, ON(Celery 워커 실행)일 때는 실제 기능이 동작하지 않으면서 워커에서는 "성공"으로 표시됩니다.

### 1.2 근본 원인

ON 모드의 Celery 태스크가 OFF 모드와 **같은 서비스 함수를 재사용하지 않고 별도 로직으로 작성**되어, 워크플로우의 핵심 단계(재고 체크, 발행 후처리 등)가 누락되었습니다.

### 1.3 발견된 5가지 문제

| # | 문제 | 심각도 | 영향 |
|---|------|--------|------|
| 1 | Celery 태스크가 실패해도 예외를 삼키고 dict 반환 → Celery가 SUCCESS로 기록 | 치명적 | 모든 태스크 |
| 2 | 발행 ON: `crawled_post` 미반환으로 후속 발행 로직 전체 스킵 | 치명적 | 발행 모듈 |
| 3 | 생성 ON: 재고 체크, stage_params, user_id 등 핵심 파라미터 누락 | 심각 | 생성 모듈 |
| 4 | `_run_async()` 이벤트 루프 관리 불안정 → DB 세션 오류 가능 | 심각 | 모든 태스크 |
| 5 | 발행 ON: `complete_publish()` 미호출로 재고/상태 업데이트 누락 | 심각 | 발행 후처리 |

---

## 2. 수정 전략

### 2.1 핵심 원칙: "공통 로직 단일화"

```
[수정 전]
OFF 모드: flows_execute.py → FlowGenerateExecutor → ContentGenerator (완전한 로직)
ON 모드:  flows_execute.py → Celery 태스크 → ContentGenerator (불완전한 별도 로직)

[수정 후]
OFF 모드: flows_execute.py → 공통 서비스 함수 직접 호출
ON 모드:  flows_execute.py → Celery 큐 등록 → 워커가 같은 공통 서비스 함수 호출
```

### 2.2 Celery 태스크의 역할 재정의

Celery 태스크는 **얇은 래퍼(thin wrapper)** 역할만 수행합니다:

```
Celery 태스크 = DB 세션 생성 + 공통 서비스 함수 호출 + DB 세션 정리
```

실제 비즈니스 로직은 모두 공통 서비스 함수에 있으므로, ON/OFF 모드 전환 시 결과가 동일합니다.

---

## 3. 페이즈별 구현 계획

### Phase 1: 기반 안정화 (`_run_async()` + 예외 처리)

> **목표**: Celery 태스크의 실행 환경을 안정화하고, 실패를 정확히 감지할 수 있도록 합니다.
> **이유**: 이 단계가 불안정하면 이후 Phase에서 통합한 로직도 제대로 동작하지 않습니다.

#### 1-1. `_run_async()` 함수 통합 및 안정화

**현재 문제**: 3개 파일에 각각 `_run_async()`가 존재하며, 3가지 분기가 불안정합니다.

**변경 대상**:
- `app/core/celery_tasks.py` (11-21행)
- `app/core/celery_publish_tasks.py` (10-22행)
- `app/core/celery_utility_tasks.py` (16-26행)

**변경 내용**:
1. `app/core/celery_async_bridge.py` 파일을 새로 생성하여 `_run_async()` 함수를 1곳에서 관리
2. 단순하고 안정적인 구현으로 변경:
   ```python
   # 항상 새 이벤트 루프에서 실행 (Celery prefork 워커에 가장 안전)
   def run_async(coro):
       return asyncio.run(coro)
   ```
3. 3개 파일에서 로컬 `_run_async()` 제거 후 공통 함수 import

#### 1-2. 예외 삼킴 패턴 제거

**현재 문제**: 실패 시 `return {"success": False, ...}` → Celery가 SUCCESS로 기록

**변경 대상**:
- `app/core/celery_tasks.py`: `generate_content` (278-288행), `generate_image` (384-390행), `on_generation_complete` (424-425행)
- `app/core/celery_publish_tasks.py`: `publish_post` (196행), `republish_post` (285행)
- `app/core/celery_utility_tasks.py`: `collect_keywords` (118-122행)

**변경 내용**:
- 최대 재시도 초과 후에는 예외를 `raise`하여 Celery가 FAILURE로 기록
- 의도적인 스킵(제목 없음 등)은 별도 SkipTask 예외 클래스로 구분
  ```python
  class TaskSkipped(Exception):
      """의도적 스킵 (실패가 아님)"""
      pass
  ```

#### Phase 1 완료 기준
- [ ] `_run_async()` 함수가 1곳에만 존재
- [ ] 모든 Celery 태스크에서 실패 시 Celery FAILURE로 기록됨
- [ ] 의도적 스킵과 실제 에러가 구분됨
- [ ] OFF 모드 정상 동작 확인 (기존 기능 영향 없음)

---

### Phase 2: 생성(Generation) 태스크 로직 통합

> **목표**: Celery 생성 태스크가 `FlowGenerateExecutor`를 호출하여 OFF 모드와 동일한 로직을 사용하도록 합니다.

#### 2-1. 디스패처에 필수 파라미터 추가

**변경 대상**: `app/core/task_dispatcher.py` → `dispatch_generation()` (102-148행)

**변경 내용**:
- `user_id`, `stage_params`(dict 직렬화), `force` 파라미터를 Celery 태스크에 전달
- 현재:
  ```python
  dispatch_generation(blog_id, module_id, title_id=0, flow_id=None)
  ```
- 변경 후:
  ```python
  dispatch_generation(blog_id, module_id, title_id=0, flow_id=None,
                      user_id=None, stage_params_dict=None, force=False)
  ```

#### 2-2. Celery 생성 태스크를 얇은 래퍼로 변경

**변경 대상**: `app/core/celery_tasks.py` → `generate_content` 태스크 (222-290행)

**변경 내용**:
- 기존의 `_async_generate_content()`, `_resolve_title_id()`, `_filter_categories_for_blog()` 제거
- 태스크 내부에서 `FlowGenerateExecutor.execute_for_blog()` 호출
  ```python
  @celery_app.task(...)
  def generate_content(self, blog_id, module_id, ...):
      async def _execute():
          async with db_manager.get_session() as db:
              executor = FlowGenerateExecutor(db, user_id)
              # OFF 모드와 동일한 함수 호출
              return await executor.execute_for_blog(module, blog, stage_params, force)
      return run_async(_execute())
  ```

#### 2-3. `flows_execute.py` ON 모드 생성 분기 정리

**변경 대상**: `app/routers/flows_execute.py` → 생성 모듈 디스패치 부분 (~649-700행)

**변경 내용**:
- ON 모드: 디스패치 후 즉시 반환 (후속 로직은 Celery 태스크 내부에서 처리)
- OFF 모드: 기존 로직 유지

#### Phase 2 완료 기준
- [ ] Celery 생성 태스크가 `FlowGenerateExecutor.execute_for_blog()` 호출
- [ ] 재고 체크(InventoryTrigger)가 ON 모드에서도 동작
- [ ] stage_params, user_id, force 파라미터가 정상 전달
- [ ] ON/OFF 모드 모두 동일한 생성 결과 확인

---

### Phase 3: 발행(Publish) 태스크 로직 통합

> **목표**: Celery 발행 태스크가 "대상 선택 → 실제 발행 → 후처리" 전체 워크플로우를 포함하도록 합니다.

#### 3-1. 발행 워크플로우 공통 서비스 함수 생성

**신규 파일**: `app/services/generation/publish_workflow.py`

**역할**: OFF 모드의 `flows_execute.py`에 흩어져 있는 발행 워크플로우를 하나의 서비스 함수로 통합

```python
class PublishWorkflow:
    """발행 전체 워크플로우 (ON/OFF 모드 공통)"""
    
    async def execute_publish(self, blog_id, post_id=0, flow_id=None):
        """대상 선택 → 실제 발행 → 후처리 (complete_publish 포함)"""
        # 1. 발행 대상 선택 (post_id=0이면 자동 선택)
        # 2. 플랫폼별 발행 (WordPress/Blogger)
        # 3. complete_publish() 호출 (재고/상태 업데이트)
        # 4. FES 갱신
```

#### 3-2. Celery 발행 태스크를 얇은 래퍼로 변경

**변경 대상**: `app/core/celery_publish_tasks.py` → `publish_post` 태스크 (145-198행)

**변경 내용**:
- 기존의 `_async_publish_post()`, `_resolve_post_id()` 제거
- 태스크 내부에서 `PublishWorkflow.execute_publish()` 호출

#### 3-3. 재발행(Republish) 태스크도 동일하게 통합

**변경 대상**: `app/core/celery_publish_tasks.py` → `republish_post` 태스크 (242-287행)

**변경 내용**:
- `_async_republish()` 제거
- `PublishWorkflow.execute_republish()` 호출로 통합

#### 3-4. `flows_execute.py` ON 모드 발행 분기 정리

**변경 대상**: `app/routers/flows_execute.py` → 발행 디스패치 부분 (~396-450행)

**변경 내용**:
- ON 모드: `dispatcher.dispatch_publish()` 후 `crawled_post` 체크 로직 제거
- `crawled_post` 관련 후속 로직은 `PublishWorkflow` 내부에서 처리되므로 불필요

#### Phase 3 완료 기준
- [ ] Celery 발행 태스크가 대상 선택 → 발행 → 후처리 전체 수행
- [ ] `complete_publish()`가 ON 모드에서도 호출됨
- [ ] `flows_execute.py`에서 ON 모드 발행 후 불필요한 후속 로직 제거
- [ ] ON/OFF 모드 모두 동일한 발행 결과 확인

---

### Phase 4: 유틸리티(Collect/Data) 태스크 점검 및 정리

> **목표**: 수집/데이터 태스크도 동일한 패턴으로 통합되었는지 확인하고 정리합니다.

#### 4-1. 유틸리티 태스크 점검

**변경 대상**: `app/core/celery_utility_tasks.py`

**확인 사항**:
- `_async_collect()`가 `flows_execute.py`의 `_execute_collect_module()` / `_execute_data_module()`을 직접 호출하고 있는지 확인 (현재는 재사용하고 있으나 정확한 동작 검증 필요)
- 파라미터 전달 누락 없는지 확인

#### 4-2. `flows_execute.py` ON 모드 유틸리티 분기 정리

**변경 대상**: `app/routers/flows_execute.py` → 수집/데이터 모듈 디스패치 부분

**변경 내용**:
- ON 모드에서도 동일한 결과가 나오는지 확인
- 불필요한 후속 로직 정리

#### Phase 4 완료 기준
- [ ] 수집/데이터 태스크의 ON/OFF 동작 동일 확인
- [ ] 파라미터 전달 누락 없음 확인

---

### Phase 5: 통합 테스트 및 검증

> **목표**: 전체 파이프라인이 ON/OFF 모드에서 동일하게 동작하는지 검증합니다.

#### 5-1. 테스트 시나리오

| # | 시나리오 | 검증 항목 |
|---|---------|----------|
| 1 | OFF 모드: 플로우 1회 실행 (생성) | 제목 선택 → 글 생성 → 이미지 생성 → DB 저장 |
| 2 | ON 모드: 동일 플로우 1회 실행 (생성) | 위와 동일한 결과 |
| 3 | OFF 모드: 플로우 1회 실행 (발행) | 대상 선택 → 발행 → 후처리 → 재고 업데이트 |
| 4 | ON 모드: 동일 플로우 1회 실행 (발행) | 위와 동일한 결과 |
| 5 | ON 모드: 생성 실패 시 | Celery에 FAILURE 기록 확인 |
| 6 | ON 모드: 제목 없을 때 | 의도적 스킵으로 구분 확인 |
| 7 | OFF→ON 모드 전환 | 환경변수 변경만으로 동작 전환 확인 |

#### 5-2. 로그 검증

- Celery 워커 로그에서 `[GENERATOR]`, `[INVENTORY]`, `[PUBLISHER]` 태그 확인
- 생성/발행 각 단계가 실행되는지 로그로 확인

#### Phase 5 완료 기준
- [ ] 7개 테스트 시나리오 모두 통과
- [ ] Celery 워커 로그에서 전체 파이프라인 단계 확인
- [ ] OFF 모드 기존 기능 정상 동작 확인 (회귀 없음)

---

## 4. 변경 파일 목록

### 신규 파일
| 파일 | 설명 |
|------|------|
| `app/core/celery_async_bridge.py` | `run_async()` 공통 함수 + `TaskSkipped` 예외 클래스 |
| `app/services/generation/publish_workflow.py` | 발행 전체 워크플로우 공통 서비스 |

### 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `app/core/celery_tasks.py` | 생성 태스크를 얇은 래퍼로 변경, `_run_async()` 제거 |
| `app/core/celery_publish_tasks.py` | 발행 태스크를 얇은 래퍼로 변경, `_run_async()` 제거 |
| `app/core/celery_utility_tasks.py` | `_run_async()` 제거, 공통 함수 import |
| `app/core/task_dispatcher.py` | `dispatch_generation()`에 `user_id`, `stage_params_dict`, `force` 추가 |
| `app/routers/flows_execute.py` | ON 모드 디스패치 후 불필요한 후속 로직 제거 |

### 삭제 대상 (파일 내 함수)
| 파일 | 삭제 함수 | 이유 |
|------|----------|------|
| `celery_tasks.py` | `_run_async()`, `_async_generate_content()`, `_resolve_title_id()`, `_filter_categories_for_blog()` | 공통 로직으로 대체 |
| `celery_publish_tasks.py` | `_run_async()`, `_async_publish_post()`, `_resolve_post_id()`, `_async_republish()` | 공통 로직으로 대체 |
| `celery_utility_tasks.py` | `_run_async()` | 공통 함수로 대체 |

---

## 5. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| Phase 1 변경으로 기존 OFF 모드에 영향 | 높음 | Phase 1 완료 후 OFF 모드 테스트 우선 실행 |
| `FlowGenerateExecutor`가 Celery에서 DB 세션 문제 | 중간 | `run_async()` 내부에서 매번 새 세션 생성 + 정리 |
| `stage_params` dict 직렬화/역직렬화 오류 | 중간 | dataclass의 `asdict()` / `from_dict()` 메서드 구현 |
| `PublishWorkflow` 추출 시 `flows_execute.py` 기존 로직 깨짐 | 높음 | OFF 모드 로직은 그대로 두고 공통 함수를 별도 생성 |
| Celery 워커 재시작 필요 | 낮음 | Docker Compose로 일괄 재시작 |

---

## 6. 작업 순서 및 예상 규모

| Phase | 작업 | 예상 변경량 | 의존성 |
|-------|------|-----------|--------|
| 1 | 기반 안정화 | ~100줄 신규, ~60줄 삭제 | 없음 |
| 2 | 생성 태스크 통합 | ~50줄 수정, ~80줄 삭제 | Phase 1 |
| 3 | 발행 태스크 통합 | ~150줄 신규, ~100줄 삭제 | Phase 1 |
| 4 | 유틸리티 점검 | ~20줄 수정 | Phase 1 |
| 5 | 통합 테스트 | 테스트만 | Phase 2, 3, 4 |

---

**Last Updated**: 2026-04-19 | **Version**: v1.0.0
