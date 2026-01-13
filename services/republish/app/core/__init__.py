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
    Connection, FlowExecutionResult, NodeExecutionResult
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
    "Connection", "FlowExecutionResult", "NodeExecutionResult",
    # Registry
    "ModuleRegistry",
]
