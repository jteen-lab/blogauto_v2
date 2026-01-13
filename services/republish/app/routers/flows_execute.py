"""
플로우 실행 API

플로우를 1회 즉시 실행합니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.database import get_db_session
from app.core.executor import (
    FlowExecutor, FlowDefinition, NodeConfig, Connection
)
from app.core.interface import PortType
from app.core.registry import ModuleRegistry
from app.models.flow import Flow
from app.models.flow_module import FlowModule
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/v1/flows", tags=["flows-execute"])
logger = logging.getLogger(__name__)


@router.post("/{flow_id}/execute")
async def execute_flow_once(
    flow_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    플로우 1회 즉시 실행

    오토런 스케줄과 무관하게 즉시 실행합니다.
    테스트 목적으로 사용됩니다.
    """
    # 1. 플로우 조회
    result = await db.execute(
        select(Flow).where(Flow.id == flow_id, Flow.user_id == current_user.id)
    )
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
        "db_query": "db_query",
        "db_save": "db_save",
    }


def _has_trigger(nodes: list[NodeConfig]) -> bool:
    """트리거 노드 존재 여부"""
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
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    플로우 실행 히스토리 조회

    TODO: 실행 결과 DB 저장 후 구현
    """
    return {
        "flow_id": flow_id,
        "executions": [],
        "total_count": 0,
        "message": "실행 히스토리 기능 준비 중"
    }
