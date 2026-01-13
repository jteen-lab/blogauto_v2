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


class ExecuteFlowRequest(BaseModel):
    """플로우 실행 요청"""
    input_data: Optional[dict] = None


class ExecutionHistoryResponse(BaseModel):
    """실행 히스토리 응답"""
    flow_id: int
    executions: list[FlowExecutionResultSchema]
    total_count: int
