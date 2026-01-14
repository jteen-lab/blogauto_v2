# Phase 1-6: 실제 노드 체인 분할

> **작업 유형**: 리팩토링  
> **예상 시간**: 4-6시간  
> **우선순위**: P0 (Critical)  
> **선행 작업**: Phase 1-5 완료

---

## 📋 작업 개요

현재 Publish 모듈 내부에 모든 로직이 포함되어 있습니다. 이를 실제 노드 체인으로 분할합니다.

### 현재 상태

```
[ManualTrigger] → [Publish]
                      ↓
                  Publish 내부에서 모든 것 처리:
                  - DB에서 블로그 조회
                  - 재발행할 포스트 선택
                  - WordPress API 호출
                  - 결과 DB 저장
```

### 목표 상태

```
[ManualTrigger] → [DBQuery] → [PostSelector] → [Publish] → [DBSave]
       ↓              ↓             ↓              ↓           ↓
    시작점        블로그 조회    포스트 선택    순수 발행    결과 저장
```

---

## 🤖 에이전트별 작업 분배

### @explorer-agent

**역할**: 현재 Publish 모듈 내부 로직 분석

**분석 대상**:
```
services/republish/app/modules/actions/publish.py
```

**분석 항목**:
1. DB 조회 로직 위치 및 내용 (어떤 테이블, 어떤 쿼리)
2. 포스트 선택 로직 위치 및 내용
3. WordPress API 호출 로직 위치 및 내용
4. 결과 저장 로직 위치 및 내용
5. 각 로직 간 데이터 전달 형태

**출력 형식**:
```markdown
## Publish 모듈 내부 로직 분석

### 1. DB 조회 로직
- 위치 (라인): 
- 테이블: 
- 쿼리 내용:
- 출력 데이터:

### 2. 포스트 선택 로직
- 위치 (라인):
- 선택 방식:
- 입력 데이터:
- 출력 데이터:

### 3. WordPress API 호출 로직
- 위치 (라인):
- 필요 입력:
- API 호출 방식:

### 4. 결과 저장 로직
- 위치 (라인):
- 저장 테이블:
- 저장 필드:
```

---

### @backend-agent

**역할**: 노드 모듈 분할 구현

#### 작업 1: DBQuery 모듈 보강

**파일**: `app/modules/data/db_query.py`

Publish에서 사용하는 블로그 조회 로직을 DBQuery가 처리하도록 수정:

```python
# 추가할 기능:
# - flow_id 기반 블로그 목록 조회
# - is_active 필터링
# - 출력: BlogAutoItem 리스트 (blog_id, blog_url, platform 등 포함)
```

#### 작업 2: PostSelector 모듈 실제 구현

**파일**: `app/modules/data/post_selector.py`

현재 껍데기 상태인 execute() 메서드에 실제 로직 구현:

```python
async def execute(self, items: ItemList, params: dict, context: ExecutionContext) -> ModuleResult:
    """
    입력: DBQuery에서 전달받은 블로그 목록 (BlogAutoItem 리스트)
    처리: 각 블로그에서 재발행할 포스트 선택
    출력: 선택된 포스트 정보가 포함된 BlogAutoItem 리스트
    
    선택 모드:
    - oldest: 가장 오래된 포스트
    - random: 랜덤 선택
    - sequential: 순차 선택
    """
    # 실제 로직 구현
```

#### 작업 3: Publish 모듈 순수화

**파일**: `app/modules/actions/publish.py`

DB 조회, 포스트 선택, 결과 저장 로직 제거. **순수 발행 로직만 남김**:

```python
async def execute(self, items: ItemList, params: dict, context: ExecutionContext) -> ModuleResult:
    """
    입력: PostSelector에서 전달받은 포스트 정보 (blog_id, post_id 등 포함)
    처리: WordPress/Blogger API 호출하여 발행
    출력: 발행 결과가 포함된 BlogAutoItem 리스트
    
    주의: DB 조회나 저장 하지 않음!
    """
    for item in items:
        blog_id = item.get("blog_id")
        post_id = item.get("post_id")
        # WordPress API 호출만 수행
        result = await self._publish_wordpress(blog_id, post_id, ...)
        # 결과를 item에 추가
        item.set("publish_result", result)
    
    return ModuleResult.ok(items)
```

#### 작업 4: DBSave 모듈 보강

**파일**: `app/modules/data/db_save.py`

Publish 결과 저장 로직 추가:

```python
# 추가할 기능:
# - autorun_logs 테이블에 실행 결과 저장
# - url_history 테이블에 발행 기록 저장
# - last_published 필드 업데이트
```

#### 작업 5: FlowDefinition 수정 (핵심!)

**파일**: `app/scheduler/flow_scheduler.py`

`_build_republish_flow_definition()` 메서드를 5개 노드 체인으로 수정:

```python
def _build_republish_flow_definition(self, flow: Flow, module: Module) -> FlowDefinition:
    """
    노드 구성 (5개 체인):
    1. ManualTrigger → 시작점
    2. DBQuery → Flow 블로그 조회
    3. PostSelector → 재발행할 포스트 선택
    4. Publish → WordPress API 호출 (순수 발행만)
    5. DBSave → 결과 저장
    """
    nodes = []
    connections = []
    
    # 1. ManualTrigger
    trigger_node = NodeConfig(
        id="node_trigger",
        module_name="manual_trigger",
        params={}
    )
    nodes.append(trigger_node)
    
    # 2. DBQuery - 블로그 조회
    db_query_node = NodeConfig(
        id="node_db_query",
        module_name="db_query",
        params={
            "table": "flow_blogs",
            "filter": {"flow_id": flow.id, "is_active": True}
        }
    )
    nodes.append(db_query_node)
    
    # 3. PostSelector - 포스트 선택
    post_selector_node = NodeConfig(
        id="node_post_selector",
        module_name="post_selector",
        params={
            "selection_mode": module.settings.get("selection_mode", "oldest"),
            "min_age_days": module.settings.get("min_age_days", 30),
            "max_posts": module.settings.get("max_posts", 1)
        }
    )
    nodes.append(post_selector_node)
    
    # 4. Publish - 순수 발행
    publish_node = NodeConfig(
        id="node_publish",
        module_name="publish",
        params={
            "platform": "wordpress",
            "publish_mode": "update",
            "update_date": True
        }
    )
    nodes.append(publish_node)
    
    # 5. DBSave - 결과 저장
    db_save_node = NodeConfig(
        id="node_db_save",
        module_name="db_save",
        params={
            "table": "autorun_logs",
            "mode": "insert"
        }
    )
    nodes.append(db_save_node)
    
    # 연결 (순차)
    connections = [
        Connection(from_node="node_trigger", from_port=PortType.MAIN, 
                   to_node="node_db_query", to_port=PortType.MAIN),
        Connection(from_node="node_db_query", from_port=PortType.MAIN,
                   to_node="node_post_selector", to_port=PortType.MAIN),
        Connection(from_node="node_post_selector", from_port=PortType.MAIN,
                   to_node="node_publish", to_port=PortType.MAIN),
        Connection(from_node="node_publish", from_port=PortType.MAIN,
                   to_node="node_db_save", to_port=PortType.MAIN),
    ]
    
    return FlowDefinition(
        id=flow.id,
        name=flow.name,
        nodes=nodes,
        connections=connections
    )
```

---

### @reviewer-agent

**역할**: 코드 리뷰 및 노드 체인 검증

#### 검증 항목

1. **데이터 흐름 검증**
   - DBQuery 출력 → PostSelector 입력 호환성
   - PostSelector 출력 → Publish 입력 호환성
   - Publish 출력 → DBSave 입력 호환성

2. **기능 동일성**
   - 기존 Publish 모듈과 동일한 결과 출력
   - 블로그 조회, 포스트 선택, 발행, 저장 모두 정상 동작

3. **코드 품질**
   - 각 모듈 < 300줄
   - 함수 < 50줄
   - 타입 힌트, Docstring

#### 테스트 시나리오

```bash
# 1. 플로우 1회 실행 (▶ 버튼)
# 2. 로그에서 5개 노드 순차 실행 확인
# 3. 각 노드별 items_in, items_out 확인
# 4. 최종 발행 결과 확인
```

---

## 📁 파일 목록

### 수정 파일

| 파일 | 담당 | 수정 내용 |
|------|------|----------|
| `app/modules/data/db_query.py` | @backend-agent | flow_blogs 조회 로직 추가 |
| `app/modules/data/post_selector.py` | @backend-agent | 실제 포스트 선택 로직 구현 |
| `app/modules/actions/publish.py` | @backend-agent | DB 로직 제거, 순수 발행만 |
| `app/modules/data/db_save.py` | @backend-agent | 실행 결과 저장 로직 추가 |
| `app/scheduler/flow_scheduler.py` | @backend-agent | 5개 노드 체인으로 수정 |

---

## 🔄 작업 순서

```
1. @explorer-agent: 현재 Publish 모듈 내부 로직 분석
       ↓
2. @backend-agent: 분석 결과 기반 모듈 분할
   - DBQuery 보강
   - PostSelector 실제 구현
   - Publish 순수화
   - DBSave 보강
       ↓
3. @backend-agent: _build_republish_flow_definition() 5개 노드 체인으로 수정
       ↓
4. @reviewer-agent: 데이터 흐름 검증 + 기능 테스트
```

---

## ✅ 완료 조건

### 필수
- [ ] DBQuery: flow_blogs 조회 가능
- [ ] PostSelector: 실제 포스트 선택 로직 동작
- [ ] Publish: DB 로직 없이 순수 발행만
- [ ] DBSave: 실행 결과 저장
- [ ] _build_republish_flow_definition(): 5개 노드 체인

### 검증
- [ ] 1회 실행 시 5개 노드 순차 실행 로그 확인
- [ ] 기존과 동일한 재발행 결과
- [ ] node_results에 5개 노드 결과 포함

---

## 🚨 주의사항

1. **데이터 형식 통일**: 모든 노드는 `BlogAutoItem` 리스트를 주고받음
2. **기존 기능 유지**: 분할 후에도 기존과 동일하게 동작해야 함
3. **롤백 대비**: 문제 시 기존 Publish 로직으로 복구 가능하도록

---

## 📝 커밋 메시지

```
refactor(modules): 재발행 노드 체인 5개로 분할

- DBQuery: flow_blogs 조회 추가
- PostSelector: 실제 포스트 선택 로직 구현
- Publish: 순수 발행 로직만 유지
- DBSave: 실행 결과 저장 추가
- flow_scheduler: 5개 노드 체인 구성

관련: Phase 1-6
```

---

## 📊 노드 데이터 흐름 상세

```
[ManualTrigger]
    ↓ 출력: [{triggered_at: "...", is_test: false}]

[DBQuery]
    ↓ 입력: 트리거 정보 (무시 가능)
    ↓ 출력: [{blog_id: 1, blog_url: "...", platform: "wordpress"}, ...]

[PostSelector]
    ↓ 입력: 블로그 목록
    ↓ 출력: [{blog_id: 1, post_id: 123, post_title: "...", post_url: "..."}, ...]

[Publish]
    ↓ 입력: 포스트 정보
    ↓ 출력: [{blog_id: 1, post_id: 123, publish_result: {success: true, url: "..."}}, ...]

[DBSave]
    ↓ 입력: 발행 결과
    ↓ 출력: [{saved: true, log_id: 456}, ...]
```
