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
        """노드 ID로 노드 조회"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_trigger_nodes(self) -> list[NodeConfig]:
        """트리거 노드 목록"""
        triggers = []
        for node in self.nodes:
            module = ModuleRegistry.get(node.module_name)
            if module and module.module_type == ModuleType.TRIGGER:
                triggers.append(node)
        return triggers

    def get_incoming_connections(self, node_id: str) -> list[Connection]:
        """노드로 들어오는 연결 목록"""
        return [c for c in self.connections if c.to_node == node_id]

    def get_outgoing_connections(self, node_id: str) -> list[Connection]:
        """노드에서 나가는 연결 목록"""
        return [c for c in self.connections if c.from_node == node_id]


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

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "module_name": self.module_name,
            "success": self.success,
            "items_in": self.items_in,
            "items_out": self.items_out,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error
        }


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
        """실행 시간 (밀리초)"""
        if self.completed_at is None:
            return 0
        delta = self.completed_at - self.started_at
        return int(delta.total_seconds() * 1000)

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "flow_id": self.flow_id,
            "flow_name": self.flow_name,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "total_items_processed": self.total_items_processed,
            "error": self.error,
            "node_results": [r.to_dict() for r in self.node_results]
        }


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
        """
        플로우 실행

        Args:
            flow: 플로우 정의
            is_test: 테스트 모드 여부

        Returns:
            FlowExecutionResult: 실행 결과
        """
        execution_id = str(uuid.uuid4())
        result = FlowExecutionResult(
            execution_id=execution_id,
            flow_id=flow.id,
            flow_name=flow.name,
            success=True,
            started_at=datetime.now()
        )
        context = ExecutionContext(
            flow_id=flow.id,
            flow_name=flow.name,
            execution_id=execution_id,
            db_session=self.db_session,
            logger=self.logger,
            is_test=is_test
        )
        context.log(f"플로우 실행 시작: {flow.name}")

        try:
            sorted_nodes = self._topological_sort(flow)
            node_outputs: dict[str, dict[PortType, ItemList]] = {}

            for node in sorted_nodes:
                node_result = await self._execute_node(
                    node, flow, node_outputs, context
                )
                result.node_results.append(node_result)
                result.total_items_processed += node_result.items_out

                if not node_result.success:
                    result.success = False
                    result.error = f"노드 실패: {node.id} - {node_result.error}"
                    break

            result.completed_at = datetime.now()
            context.log(f"플로우 완료: success={result.success}, duration={result.duration_ms}ms")

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.completed_at = datetime.now()
            context.log(f"플로우 오류: {e}", level="error")

        return result

    async def _execute_node(
        self,
        node: NodeConfig,
        flow: FlowDefinition,
        node_outputs: dict,
        context: ExecutionContext
    ) -> NodeExecutionResult:
        """단일 노드 실행"""
        start_time = datetime.now()
        module = ModuleRegistry.get(node.module_name)

        if not module:
            return NodeExecutionResult(
                node_id=node.id, module_name=node.module_name,
                success=False, items_in=0, items_out=0,
                execution_time_ms=0, error=f"모듈 없음: {node.module_name}"
            )

        input_items = self._collect_inputs(node, flow, node_outputs)
        context.log(f"노드 실행: {node.id} ({module.display_name}), 입력: {len(input_items)}개")

        try:
            result = await module.execute(input_items, node.params, context)
            node_outputs[node.id] = {PortType.MAIN: result.items}

            if result.outputs:
                node_outputs[node.id].update(result.outputs)

            end_time = datetime.now()
            exec_time = int((end_time - start_time).total_seconds() * 1000)

            return NodeExecutionResult(
                node_id=node.id, module_name=node.module_name,
                success=result.success, items_in=len(input_items),
                items_out=len(result.items), execution_time_ms=exec_time,
                error=result.error
            )
        except Exception as e:
            end_time = datetime.now()
            exec_time = int((end_time - start_time).total_seconds() * 1000)
            return NodeExecutionResult(
                node_id=node.id, module_name=node.module_name,
                success=False, items_in=len(input_items), items_out=0,
                execution_time_ms=exec_time, error=str(e)
            )

    def _collect_inputs(
        self,
        node: NodeConfig,
        flow: FlowDefinition,
        node_outputs: dict
    ) -> ItemList:
        """노드 입력 수집"""
        incoming = flow.get_incoming_connections(node.id)
        if not incoming:
            return []

        all_items: ItemList = []
        for conn in incoming:
            if conn.from_node in node_outputs:
                port_outputs = node_outputs[conn.from_node]
                items = port_outputs.get(conn.from_port, [])
                all_items.extend(items)
        return all_items

    def _topological_sort(self, flow: FlowDefinition) -> list[NodeConfig]:
        """토폴로지 정렬"""
        in_degree: dict[str, int] = defaultdict(int)
        for node in flow.nodes:
            in_degree[node.id] = 0
        for conn in flow.connections:
            in_degree[conn.to_node] += 1

        queue = [n for n in flow.nodes if in_degree[n.id] == 0]
        result: list[NodeConfig] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for conn in flow.get_outgoing_connections(node.id):
                in_degree[conn.to_node] -= 1
                if in_degree[conn.to_node] == 0:
                    target = flow.get_node(conn.to_node)
                    if target:
                        queue.append(target)
        return result
