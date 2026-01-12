"""모듈 인터페이스 관련 Pydantic 스키마"""
from pydantic import BaseModel
from typing import Any
from enum import Enum


class ModuleTypeEnum(str, Enum):
    """모듈 유형"""
    COLLECTION = "collection"
    PROCESSING = "processing"
    GENERATION = "generation"
    PUBLISHING = "publishing"
    CONTROL = "control"


class InputSchema(BaseModel):
    """입력 스키마"""
    required: list[str] = []
    optional: list[str] = []


class OutputSchema(BaseModel):
    """출력 스키마"""
    provides: list[str] = []


class ModuleSchemaInfo(BaseModel):
    """모듈 스키마 정보"""
    module_type: ModuleTypeEnum
    module_name: str
    module_description: str = ""
    input_schema: InputSchema
    output_schema: OutputSchema


class ModuleExecutionInput(BaseModel):
    """모듈 실행 입력"""
    module_id: int
    inputs: dict[str, Any] = {}


class ModuleExecutionResult(BaseModel):
    """모듈 실행 결과"""
    success: bool
    module_name: str
    outputs: dict[str, Any] = {}
    error_message: str | None = None
    execution_time_ms: int = 0


class ModuleConnectionInfo(BaseModel):
    """모듈 연결 정보"""
    source_module_id: int
    source_output_key: str
    target_module_id: int
    target_input_key: str


class FlowExecutionContext(BaseModel):
    """플로우 실행 컨텍스트"""
    flow_id: int
    current_module_id: int
    accumulated_outputs: dict[int, dict[str, Any]] = {}  # module_id -> outputs
    execution_history: list[ModuleExecutionResult] = []
