# Phase 1-3: 플로우 1회 실행 API

> **작업 유형**: 신규 개발  
> **예상 시간**: 2-3시간  
> **우선순위**: P0 (Critical)  
> **선행 작업**: Phase 1-1, 1-2 완료

---

## 📋 작업 개요

플로우를 1회 즉시 실행하는 API와 모듈 등록 초기화를 구현합니다.

### 목표
- 플로우 1회 실행 API 엔드포인트
- 앱 시작 시 모듈 자동 등록
- 실행 결과 반환

---

## 📁 생성/수정할 파일

### 1. app/routers/flows_execute.py (~120줄) [신규]

```python
"""
플로우 실행 API

플로우를 1회 즉시 실행합니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.database import get_db_session
from app.core.executor import (
    FlowExecutor, FlowDefinition, NodeConfig, Connection
)
from app.core.interface import PortType
from app.models.flow import Flow
from app.models.flow_module import FlowModule

router = APIRouter(prefix="/api/v1/flows", tags=["flows-execute"])
logger = logging.getLogger(__name__)


@router.post("/{flow_id}/execute")
async def execute_flow_once(
    flow_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """
    플로우 1회 즉시 실행
    
    오토런 스케줄과 무관하게 즉시 실행합니다.
    테스트 목적으로 사용됩니다.
    
    Args:
        flow_id: 플로우 ID
    
    Returns:
        FlowExecutionResult: 실행 결과
    """
    # 1. 플로우 조회
    result = await db.execute(select(Flow).where(Flow.id == flow_id))
    flow = result.scalar_one_or_none()
    
    if not flow:
        raise HTTPException(status_code=404, detail="플로우를 찾을 수 없습니다")
    
    if not flow.is_active:
        raise HTTPException(status_code=400, detail="비활성화된 플로우입니다")
    
    # 2. 플로우 정의 변환
    flow_definition = await _convert_to_flow_definition(flow, db)
    
    if not flow_definition.nodes:
        raise HTTPException(status_code=400, detail="플로우에 모듈이 없습니다")
    
    # 3. 실행
    executor = FlowExecutor(db, logger)
    execution_result = await executor.execute(flow_definition, is_test=True)
    
    # 4. 결과 반환
    return execution_result.to_dict()


async def _convert_to_flow_definition(
    flow: Flow, 
    db: AsyncSession
) -> FlowDefinition:
    """
    DB의 Flow 모델을 FlowDefinition으로 변환
    
    현재 구조: 플로우 → 모듈들 (순차 연결)
    """
    # 플로우의 모듈 조회
    result = await db.execute(
        select(FlowModule)
        .where(FlowModule.flow_id == flow.id)
        .order_by(FlowModule.order)
    )
    flow_modules = result.scalars().all()
    
    # 노드 변환
    nodes = []
    module_type_to_name = _get_module_type_mapping()
    
    for fm in flow_modules:
        module_name = module_type_to_name.get(fm.module_type, fm.module_type)
        
        node = NodeConfig(
            id=f"node_{fm.id}",
            module_name=module_name,
            params=fm.settings or {}
        )
        nodes.append(node)
    
    # 트리거 노드가 없으면 수동 트리거 추가
    if nodes and not _has_trigger(nodes):
        trigger_node = NodeConfig(
            id="node_trigger",
            module_name="manual_trigger",
            params={}
        )
        nodes.insert(0, trigger_node)
    
    # 연결 생성 (순차 연결)
    connections = []
    for i in range(len(nodes) - 1):
        conn = Connection(
            from_node=nodes[i].id,
            from_port=PortType.MAIN,
            to_node=nodes[i + 1].id,
            to_port=PortType.MAIN
        )
        connections.append(conn)
    
    return FlowDefinition(
        id=flow.id,
        name=flow.name,
        nodes=nodes,
        connections=connections
    )


def _get_module_type_mapping() -> dict[str, str]:
    """기존 모듈 타입 → 새 모듈 이름 매핑"""
    return {
        "republish": "publish",  # 재발행 → 발행 모듈
        # 추가 매핑
    }


def _has_trigger(nodes: list[NodeConfig]) -> bool:
    """트리거 노드 존재 여부"""
    from app.core.registry import ModuleRegistry
    from app.core.interface import ModuleType
    
    for node in nodes:
        module = ModuleRegistry.get(node.module_name)
        if module and module.module_type == ModuleType.TRIGGER:
            return True
    return False


@router.get("/{flow_id}/execute/history")
async def get_execution_history(
    flow_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db_session)
):
    """
    플로우 실행 히스토리 조회
    
    TODO: 실행 결과 DB 저장 후 구현
    """
    return {
        "flow_id": flow_id,
        "executions": [],
        "message": "실행 히스토리 기능 준비 중"
    }
```

### 2. app/routers/__init__.py 수정

```python
# 기존 import에 추가
from app.routers import flows_execute

# router 등록 추가
```

### 3. app/main.py 수정 (~10줄 추가)

```python
# 앱 시작 시 모듈 등록 추가

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클 관리"""
    # 시작 시
    from app.modules import register_all_modules
    register_all_modules()
    logger.info("모듈 등록 완료")
    
    yield
    
    # 종료 시
    logger.info("앱 종료")


# FastAPI 앱 생성 시 lifespan 추가
app = FastAPI(
    title="BlogAuto V2",
    lifespan=lifespan,
    # ...
)

# 라우터 등록
from app.routers import flows_execute
app.include_router(flows_execute.router)
```

### 4. app/schemas/flow_execute.py (~50줄) [신규]

```python
"""
플로우 실행 관련 스키마
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NodeResultSchema(BaseModel):
    """노드 실행 결과"""
    node_id: str
    module_name: str
    success: bool
    items_in: int
    items_out: int
    execution_time_ms: int
    error: Optional[str] = None


class FlowExecutionResultSchema(BaseModel):
    """플로우 실행 결과"""
    execution_id: str
    flow_id: int
    flow_name: str
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int
    total_items_processed: int
    error: Optional[str] = None
    node_results: list[NodeResultSchema]
    
    class Config:
        from_attributes = True
```

---

## 🔗 라우터 등록

### app/main.py에 추가

```python
# 기존 라우터들...
from app.routers import flows_execute

app.include_router(flows_execute.router)
```

---

## ✅ 완료 조건

### 필수
- [ ] app/routers/flows_execute.py 생성
- [ ] POST /api/v1/flows/{flow_id}/execute 동작
- [ ] app/main.py에 모듈 등록 추가
- [ ] app/main.py에 라우터 등록

### 검증
- [ ] 앱 시작 시 모듈 등록 로그 확인
- [ ] API 호출 시 실행 결과 반환

---

## 🧪 테스트 방법

### 1. 앱 시작 확인
```bash
docker-compose logs app --tail 20
# "모듈 등록 완료" 로그 확인
```

### 2. API 테스트
```bash
# 플로우 1회 실행
curl -X POST http://localhost:8001/api/v1/flows/1/execute

# 예상 응답
{
  "execution_id": "uuid...",
  "flow_id": 1,
  "flow_name": "테스트 플로우",
  "success": true,
  "duration_ms": 150,
  "node_results": [
    {
      "node_id": "node_trigger",
      "module_name": "manual_trigger",
      "success": true,
      "items_in": 0,
      "items_out": 1
    },
    ...
  ]
}
```

---

## 🚨 주의사항

1. **is_test=True**: 1회 실행은 항상 테스트 모드
2. **트리거 자동 추가**: 트리거 없으면 manual_trigger 추가
3. **기존 API 유지**: /api/v1/flows 기존 CRUD는 그대로

---

## 📝 커밋 메시지

```
feat(api): 플로우 1회 실행 API 추가

- POST /api/v1/flows/{flow_id}/execute
- 앱 시작 시 모듈 자동 등록
- FlowDefinition 변환 로직

관련: DCR-001
```
