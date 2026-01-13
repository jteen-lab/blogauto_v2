# Phase 1-5: 재발행 모듈 노드 방식 대체

> **작업 유형**: 마이그레이션  
> **예상 시간**: 6-8시간  
> **우선순위**: P0 (Critical)  
> **선행 작업**: Phase 1-1 ~ 1-4 완료

---

## 📋 작업 개요

기존 재발행 모듈(`services/modules/republish.py`)의 로직을 노드 방식 모듈 시스템으로 이전합니다.

### 목표
1. 기존 재발행 로직 분석
2. 노드 모듈별로 분할 이전
3. 오토런 스케줄러 → FlowExecutor 연결
4. 기존 시스템과 동일 동작 검증

### 변환 구조

```
대체 전:
┌─────────────────────────────────────────────────────────┐
│  오토런 스케줄러                                         │
│       ↓                                                 │
│  기존 republish.py (모든 로직 포함)                      │
│  - DB에서 블로그 조회                                    │
│  - 재발행할 포스트 선택                                  │
│  - WordPress API 호출                                   │
│  - 결과 DB 저장                                         │
└─────────────────────────────────────────────────────────┘

대체 후:
┌─────────────────────────────────────────────────────────┐
│  오토런 스케줄러                                         │
│       ↓                                                 │
│  FlowExecutor (노드 실행 엔진)                           │
│       ↓                                                 │
│  [ScheduleTrigger] → [DBQuery] → [PostSelector] →       │
│  [Publish] → [DBSave]                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 🤖 에이전트별 작업 분배

### @explorer-agent (Gemini CLI)

**역할**: 기존 코드 분석 (읽기 전용)

**분석 대상 파일**:
```
services/republish/app/services/modules/republish.py
services/republish/app/services/modules/base.py
services/republish/app/services/autorun_scheduler.py (있다면)
services/republish/app/services/wordpress_service.py (있다면)
```

**분석 항목**:
1. `execute()` 메서드의 전체 흐름
2. DB 조회 로직 (어떤 테이블, 어떤 조건)
3. 포스트 선택 로직 (랜덤? 순차? 조건?)
4. WordPress API 호출 로직 (어떤 파라미터, 어떤 응답)
5. 결과 저장 로직 (어떤 테이블, 어떤 필드)
6. 사용하는 설정값/파라미터

**출력 형식**:
```markdown
## 기존 재발행 로직 분석 결과

### 1. 전체 흐름
[단계별 설명]

### 2. DB 조회
- 테이블: 
- 조건: 
- 코드 위치: 

### 3. 포스트 선택
- 로직: 
- 코드 위치: 

### 4. WordPress API 호출
- 엔드포인트: 
- 파라미터: 
- 코드 위치: 

### 5. 결과 저장
- 테이블: 
- 필드: 
- 코드 위치: 

### 6. 사용 설정값
- [설정명]: [설명]
```

---

### @backend-agent

**역할**: 노드 모듈 구현

#### 작업 1: PostSelector 모듈 신규 생성

**파일**: `app/modules/data/post_selector.py` (~150줄)

```python
"""
포스트 선택 모듈

재발행할 포스트를 선택합니다.
기존 republish.py의 포스트 선택 로직을 분리한 모듈입니다.
"""

from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class PostSelectorModule(ModuleInterface):
    """포스트 선택 모듈"""
    
    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA
    
    @property
    def name(self) -> str:
        return "post_selector"
    
    @property
    def display_name(self) -> str:
        return "포스트 선택"
    
    @property
    def description(self) -> str:
        return "재발행할 포스트를 선택합니다."
    
    @property
    def icon(self) -> str:
        return "🎯"
    
    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="selection_mode",
                type="select",
                required=False,
                default="random",
                description="선택 방식",
                options=[
                    {"value": "random", "label": "랜덤"},
                    {"value": "oldest", "label": "가장 오래된 것"},
                    {"value": "sequential", "label": "순차"}
                ]
            ),
            ModuleParam(
                name="min_age_days",
                type="number",
                required=False,
                default=30,
                description="최소 경과 일수"
            ),
            ModuleParam(
                name="max_posts",
                type="number",
                required=False,
                default=100,
                description="선택 대상 최대 포스트 수"
            )
        ]
    
    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """포스트 선택 실행"""
        # @explorer-agent 분석 결과 기반으로 구현
        # 기존 republish.py의 포스트 선택 로직 이전
        pass
```

#### 작업 2: db_query.py 보강

**파일**: `app/modules/data/db_query.py`

기존 파일에 재발행에 필요한 테이블/필터 옵션 추가:
- `url_history` 테이블 조회 지원
- `last_published` 기준 필터링
- 블로그별 조회 지원

#### 작업 3: publish.py 실제 로직 구현

**파일**: `app/modules/actions/publish.py`

기존 TODO 부분에 실제 WordPress API 호출 로직 추가:
- 기존 `wordpress_service.py` 또는 `republish.py`의 API 호출 코드 이전
- 인증 정보 처리
- 에러 핸들링

#### 작업 4: db_save.py 보강

**파일**: `app/modules/data/db_save.py`

재발행 결과 저장 로직 추가:
- `url_history` 테이블 업데이트
- `last_published` 필드 갱신

#### 작업 5: 모듈 등록

**파일**: `app/modules/__init__.py`

```python
# 추가
from app.modules.data.post_selector import PostSelectorModule

def register_all_modules():
    # 기존 내용...
    ModuleRegistry.register(PostSelectorModule())
```

#### 작업 6: 오토런 스케줄러 연결

**파일**: `app/services/autorun_scheduler.py` (또는 해당 파일)

```python
# 기존: 직접 republish 모듈 호출
# await republish_module.execute(...)

# 변경: FlowExecutor 통해 실행
from app.core.executor import FlowExecutor, FlowDefinition

async def run_republish_flow(flow_id: int):
    flow_definition = await build_republish_flow(flow_id)
    executor = FlowExecutor(db_session, logger)
    result = await executor.execute(flow_definition, is_test=False)
    return result
```

---

### @reviewer-agent

**역할**: 코드 리뷰 및 테스트

#### 검증 항목

1. **기능 동일성**
   - 기존 재발행과 동일한 블로그 선택
   - 동일한 포스트 선택 로직
   - 동일한 WordPress API 호출
   - 동일한 결과 저장

2. **코드 품질**
   - 파일 < 300줄
   - 함수 < 50줄
   - 타입 힌트 완료
   - Docstring 완료

3. **에러 처리**
   - 개별 아이템 실패 시 전체 중단 안 함
   - 에러 로깅 적절함
   - 롤백 처리 (필요시)

#### 테스트 시나리오

```python
# tests/integration/test_republish_migration.py

async def test_republish_flow_execution():
    """재발행 플로우 실행 테스트"""
    # 1. 테스트 플로우 생성
    # 2. FlowExecutor로 실행
    # 3. 결과 검증
    pass

async def test_post_selector_module():
    """포스트 선택 모듈 테스트"""
    # 랜덤, oldest, sequential 모드 각각 테스트
    pass

async def test_publish_module_wordpress():
    """WordPress 발행 모듈 테스트"""
    # 테스트 모드로 실행
    pass
```

---

## 📁 파일 목록

### 신규 생성
| 파일 | 담당 | 예상 줄수 |
|------|------|----------|
| `app/modules/data/post_selector.py` | @backend-agent | ~150줄 |
| `tests/integration/test_republish_migration.py` | @reviewer-agent | ~100줄 |

### 수정
| 파일 | 담당 | 수정 내용 |
|------|------|----------|
| `app/modules/data/db_query.py` | @backend-agent | 테이블/필터 옵션 추가 |
| `app/modules/data/db_save.py` | @backend-agent | 결과 저장 로직 추가 |
| `app/modules/actions/publish.py` | @backend-agent | 실제 API 호출 로직 |
| `app/modules/__init__.py` | @backend-agent | PostSelector 등록 |
| `app/services/autorun_scheduler.py` | @backend-agent | FlowExecutor 연결 |

---

## 🔄 작업 순서

```
1. @explorer-agent: 기존 코드 분석 → 분석 결과 공유
       ↓
2. @backend-agent: 분석 결과 기반 모듈 구현
   - PostSelector 신규 생성
   - db_query, db_save 보강
   - publish 실제 로직 구현
   - 모듈 등록
       ↓
3. @backend-agent: 오토런 스케줄러 연결
       ↓
4. @reviewer-agent: 코드 리뷰 + 테스트 코드 작성
       ↓
5. 통합 테스트 및 검증
```

---

## ✅ 완료 조건

### 필수
- [ ] 기존 재발행 로직 100% 분석 완료
- [ ] PostSelector 모듈 구현
- [ ] publish.py 실제 WordPress API 호출 구현
- [ ] db_query.py, db_save.py 보강
- [ ] 오토런 스케줄러 → FlowExecutor 연결
- [ ] 모든 파일 < 300줄

### 검증
- [ ] 기존 재발행과 동일 동작 확인
- [ ] 1회 실행 (▶ 버튼) 정상 동작
- [ ] 오토런 스케줄 정상 동작
- [ ] 에러 발생 시 적절한 처리

---

## 🚨 주의사항

1. **기존 코드 수정 금지**: `services/modules/republish.py`는 수정하지 않음 (백업용 유지)
2. **점진적 전환**: 새 시스템 검증 완료 후 기존 시스템 비활성화
3. **롤백 계획**: 문제 시 기존 시스템으로 즉시 복구 가능하도록

---

## 📝 커밋 메시지

```
feat(modules): 재발행 모듈 노드 방식 전환

- PostSelector 모듈 신규 추가
- publish 모듈 WordPress API 연동
- db_query, db_save 보강
- 오토런 스케줄러 FlowExecutor 연결

관련: DCR-001
```

---

## 📚 참조

- Phase 1-1: 기반 구조 (`app/core/`)
- Phase 1-2: 기본 모듈 (`app/modules/`)
- Phase 1-3: 실행 API
- Phase 1-4: 실행 UI
- n8n 패턴 분석 문서
