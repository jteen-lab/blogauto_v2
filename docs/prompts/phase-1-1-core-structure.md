# Phase 1-1: 노드 방식 모듈 시스템 기반 구조

> **작업 유형**: 신규 개발  
> **예상 시간**: 4-6시간  
> **우선순위**: P0 (Critical)

---

## 📋 작업 개요

BlogAuto V2에 n8n 스타일의 노드 기반 모듈 시스템 기반 구조를 구현합니다.

### 목표
- BlogAutoItem: 모든 모듈이 주고받는 표준 데이터 구조
- ModuleInterface: 모듈 인터페이스 재설계
- FlowExecutor: 플로우 실행 엔진
- ModuleRegistry: 모듈 등록/조회

### 작업 위치
```
services/republish/app/core/     # 🆕 신규 디렉토리
```

---

## 📁 생성할 파일

### 1. app/core/__init__.py (~20줄)

```python
"""
BlogAuto V2 Core Module System

n8n 스타일의 노드 기반 모듈 시스템 핵심 구성 요소
"""

from app.core.item import BlogAutoItem, BinaryData, ItemMeta, ItemList
from app.core.interface import (
    ModuleInterface, ModuleType, PortType,
    ModuleParam, ModuleResult, ExecutionContext
)
from app.core.executor import (
    FlowExecutor, FlowDefinition, NodeConfig, 
    Connection, FlowExecutionResult
)
from app.core.registry import ModuleRegistry

__all__ = [
    # Item
    "BlogAutoItem", "BinaryData", "ItemMeta", "ItemList",
    # Interface
    "ModuleInterface", "ModuleType", "PortType",
    "ModuleParam", "ModuleResult", "ExecutionContext",
    # Executor
    "FlowExecutor", "FlowDefinition", "NodeConfig",
    "Connection", "FlowExecutionResult",
    # Registry
    "ModuleRegistry",
]
```

### 2. app/core/item.py (~100줄)

BlogAutoItem 표준 데이터 구조:

```python
"""
BlogAuto 표준 데이터 아이템

모든 모듈이 주고받는 표준 데이터 단위입니다.
n8n의 item 구조를 참고하여 설계되었습니다.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import uuid


@dataclass
class BinaryData:
    """바이너리 데이터 (파일, 이미지 등)"""
    data: bytes
    mime_type: str
    filename: Optional[str] = None
    size: Optional[int] = None


@dataclass
class ItemMeta:
    """아이템 메타데이터"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_module: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlogAutoItem:
    """
    모든 모듈이 주고받는 표준 데이터 단위
    
    Attributes:
        json: 일반 데이터 (필수)
        binary: 파일 데이터 (선택)
        meta: 메타데이터 (자동 생성)
    
    Example:
        item = BlogAutoItem(
            json={"keyword": "다이어트", "volume": 5000}
        )
    """
    json: dict[str, Any]
    binary: Optional[dict[str, BinaryData]] = None
    meta: Optional[ItemMeta] = None
    
    def __post_init__(self):
        if self.meta is None:
            self.meta = ItemMeta()
    
    def get(self, key: str, default: Any = None) -> Any:
        """json 데이터에서 값 조회"""
        return self.json.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """json 데이터에 값 설정"""
        self.json[key] = value
    
    def has_binary(self, key: str) -> bool:
        """바이너리 데이터 존재 여부"""
        return self.binary is not None and key in self.binary
    
    def to_dict(self) -> dict:
        """직렬화"""
        # 구현
    
    @classmethod
    def from_dict(cls, data: dict) -> "BlogAutoItem":
        """역직렬화"""
        # 구현


# 타입 별칭
ItemList = list[BlogAutoItem]
```

### 3. app/core/interface.py (~180줄)

ModuleInterface 재설계:

```python
"""
모듈 인터페이스

모든 노드 방식 모듈이 구현해야 하는 인터페이스입니다.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field

from app.core.item import BlogAutoItem, ItemList


class ModuleType(str, Enum):
    """모듈 타입"""
    TRIGGER = "trigger"
    DATA = "data"
    PROCESS = "process"
    ACTION = "action"


class PortType(str, Enum):
    """포트 타입"""
    MAIN = "main"
    TRUE = "true"
    FALSE = "false"
    ERROR = "error"


@dataclass
class ModuleParam:
    """모듈 파라미터 정의"""
    name: str
    type: str  # string, number, boolean, select, json
    required: bool = False
    default: Any = None
    description: str = ""
    options: list[dict] = field(default_factory=list)


@dataclass
class ModuleResult:
    """모듈 실행 결과"""
    success: bool
    items: ItemList = field(default_factory=list)
    outputs: dict[str, ItemList] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: int = 0
    
    @classmethod
    def ok(cls, items: ItemList) -> "ModuleResult":
        """성공 결과"""
        return cls(success=True, items=items)
    
    @classmethod
    def multi_output(cls, outputs: dict[str, ItemList]) -> "ModuleResult":
        """멀티 아웃풋 결과"""
        return cls(success=True, outputs=outputs)
    
    @classmethod
    def fail(cls, error: str) -> "ModuleResult":
        """실패 결과"""
        return cls(success=False, error=error)


@dataclass
class ExecutionContext:
    """실행 컨텍스트"""
    flow_id: int
    flow_name: str
    execution_id: str
    db_session: Any
    logger: Any
    is_test: bool = False
    
    def log(self, message: str, level: str = "info"):
        """로깅 헬퍼"""
        # 구현


class ModuleInterface(ABC):
    """
    노드 방식 모듈 인터페이스
    
    모든 모듈은 이 인터페이스를 구현해야 합니다.
    """
    
    @property
    @abstractmethod
    def module_type(self) -> ModuleType:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    def display_name(self) -> str:
        return self.name
    
    @property
    def description(self) -> str:
        return ""
    
    @property
    def icon(self) -> str:
        return "📦"
    
    @property
    def inputs(self) -> list[PortType]:
        return [PortType.MAIN]
    
    @property
    def outputs(self) -> list[PortType]:
        return [PortType.MAIN]
    
    @property
    def params(self) -> list[ModuleParam]:
        return []
    
    @abstractmethod
    async def execute(
        self,
        items: ItemList,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> ModuleResult:
        pass
    
    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """파라미터 유효성 검사"""
        # 구현
```

### 4. app/core/executor.py (~280줄)

FlowExecutor 실행 엔진:

```python
"""
플로우 실행 엔진

플로우 정의를 받아 노드들을 순서대로 실행합니다.
"""

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict

from app.core.item import BlogAutoItem, ItemList
from app.core.interface import (
    ModuleInterface, ModuleResult, ModuleType,
    PortType, ExecutionContext
)
from app.core.registry import ModuleRegistry


@dataclass
class NodeConfig:
    """노드 설정"""
    id: str
    module_name: str
    params: dict[str, Any] = field(default_factory=dict)
    position: dict[str, int] = field(default_factory=dict)


@dataclass
class Connection:
    """노드 연결"""
    from_node: str
    from_port: PortType
    to_node: str
    to_port: PortType


@dataclass
class FlowDefinition:
    """플로우 정의"""
    id: int
    name: str
    nodes: list[NodeConfig]
    connections: list[Connection]
    
    def get_node(self, node_id: str) -> Optional[NodeConfig]:
        # 구현
    
    def get_trigger_nodes(self) -> list[NodeConfig]:
        # 구현


@dataclass
class NodeExecutionResult:
    """노드 실행 결과"""
    node_id: str
    module_name: str
    success: bool
    items_in: int
    items_out: int
    execution_time_ms: int
    error: Optional[str] = None


@dataclass
class FlowExecutionResult:
    """플로우 실행 결과"""
    execution_id: str
    flow_id: int
    flow_name: str
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    node_results: list[NodeExecutionResult] = field(default_factory=list)
    total_items_processed: int = 0
    error: Optional[str] = None
    
    @property
    def duration_ms(self) -> int:
        # 구현
    
    def to_dict(self) -> dict:
        # 구현


class FlowExecutor:
    """플로우 실행 엔진"""
    
    def __init__(self, db_session: Any, logger: Any):
        self.db_session = db_session
        self.logger = logger
    
    async def execute(
        self,
        flow: FlowDefinition,
        is_test: bool = False
    ) -> FlowExecutionResult:
        """플로우 실행"""
        # 1. 실행 ID 생성
        # 2. 토폴로지 정렬
        # 3. 노드 순차 실행
        # 4. 결과 반환
    
    async def _execute_node(
        self,
        node: NodeConfig,
        flow: FlowDefinition,
        node_outputs: dict,
        context: ExecutionContext
    ) -> NodeExecutionResult:
        """단일 노드 실행"""
        # 구현
    
    def _collect_inputs(
        self,
        node: NodeConfig,
        flow: FlowDefinition,
        node_outputs: dict
    ) -> ItemList:
        """노드 입력 수집"""
        # 구현
    
    def _topological_sort(self, flow: FlowDefinition) -> list[NodeConfig]:
        """토폴로지 정렬"""
        # 구현
```

### 5. app/core/registry.py (~80줄)

ModuleRegistry:

```python
"""
모듈 레지스트리

모든 모듈을 등록하고 조회합니다.
"""

from typing import Optional
from app.core.interface import ModuleInterface, ModuleType


class ModuleRegistry:
    """모듈 레지스트리 (싱글톤 패턴)"""
    
    _modules: dict[str, ModuleInterface] = {}
    
    @classmethod
    def register(cls, module: ModuleInterface) -> None:
        """모듈 등록"""
        cls._modules[module.name] = module
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """모듈 등록 해제"""
        if name in cls._modules:
            del cls._modules[name]
    
    @classmethod
    def get(cls, name: str) -> Optional[ModuleInterface]:
        """모듈 조회"""
        return cls._modules.get(name)
    
    @classmethod
    def get_all(cls) -> list[ModuleInterface]:
        """전체 모듈 목록"""
        return list(cls._modules.values())
    
    @classmethod
    def get_by_type(cls, module_type: ModuleType) -> list[ModuleInterface]:
        """타입별 모듈 목록"""
        return [m for m in cls._modules.values() if m.module_type == module_type]
    
    @classmethod
    def to_dict(cls) -> dict:
        """모듈 목록 직렬화 (API용)"""
        # 구현
    
    @classmethod
    def clear(cls) -> None:
        """전체 초기화 (테스트용)"""
        cls._modules.clear()
```

---

## ✅ 완료 조건

### 필수
- [ ] app/core/__init__.py 생성
- [ ] app/core/item.py 생성 (BlogAutoItem)
- [ ] app/core/interface.py 생성 (ModuleInterface)
- [ ] app/core/executor.py 생성 (FlowExecutor)
- [ ] app/core/registry.py 생성 (ModuleRegistry)
- [ ] 모든 파일 < 300줄
- [ ] 타입 힌트 완료
- [ ] Docstring 완료

### 검증
- [ ] Python import 오류 없음
- [ ] 기본 단위 테스트 통과

---

## 🚨 주의사항

1. **파일 크기 제한**: 각 파일 300줄 이하
2. **타입 힌트 필수**: 모든 함수/메서드에 타입 힌트
3. **Docstring 필수**: 모든 클래스/함수에 설명
4. **기존 코드 수정 금지**: app/services/modules/ 기존 파일 유지
5. **의존성 최소화**: 외부 라이브러리 추가 금지

---

## 📝 커밋 메시지

```
feat(core): 노드 방식 모듈 시스템 기반 구조 추가

- BlogAutoItem: 표준 데이터 구조
- ModuleInterface: 모듈 인터페이스
- FlowExecutor: 플로우 실행 엔진
- ModuleRegistry: 모듈 등록/조회

관련: DCR-001
```
