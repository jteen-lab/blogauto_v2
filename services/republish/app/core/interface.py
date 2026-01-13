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

    def to_dict(self) -> dict:
        """직렬화"""
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "options": self.options
        }


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

    def to_dict(self) -> dict:
        """직렬화"""
        return {
            "success": self.success,
            "items_count": len(self.items),
            "outputs": {k: len(v) for k, v in self.outputs.items()},
            "error": self.error,
            "execution_time_ms": self.execution_time_ms
        }


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
        log_func = getattr(self.logger, level, self.logger.info)
        prefix = f"[Flow:{self.flow_id}][{self.execution_id[:8]}]"
        log_func(f"{prefix} {message}")


class ModuleInterface(ABC):
    """
    노드 방식 모듈 인터페이스

    모든 모듈은 이 인터페이스를 구현해야 합니다.
    """

    @property
    @abstractmethod
    def module_type(self) -> ModuleType:
        """모듈 타입 반환"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """모듈 고유 이름 (영문 snake_case)"""
        pass

    @property
    def display_name(self) -> str:
        """표시용 이름 (한글 가능)"""
        return self.name

    @property
    def description(self) -> str:
        """모듈 설명"""
        return ""

    @property
    def icon(self) -> str:
        """모듈 아이콘 (이모지)"""
        return "📦"

    @property
    def inputs(self) -> list[PortType]:
        """입력 포트 목록"""
        return [PortType.MAIN]

    @property
    def outputs(self) -> list[PortType]:
        """출력 포트 목록"""
        return [PortType.MAIN]

    @property
    def params(self) -> list[ModuleParam]:
        """모듈 파라미터 정의"""
        return []

    @abstractmethod
    async def execute(
        self,
        items: ItemList,
        params: dict[str, Any],
        context: ExecutionContext
    ) -> ModuleResult:
        """
        모듈 실행

        Args:
            items: 입력 아이템 목록
            params: 사용자 설정 파라미터
            context: 실행 컨텍스트

        Returns:
            ModuleResult: 실행 결과
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        파라미터 유효성 검사

        Args:
            params: 검사할 파라미터

        Returns:
            list[str]: 오류 메시지 목록 (비어있으면 유효)
        """
        errors = []
        for param in self.params:
            if param.required and param.name not in params:
                errors.append(f"필수 파라미터 누락: {param.name}")
            if param.name in params and param.type == "number":
                value = params[param.name]
                if not isinstance(value, (int, float)):
                    errors.append(f"{param.name}은(는) 숫자여야 합니다")
        return errors

    def to_dict(self) -> dict:
        """모듈 정보 직렬화 (API용)"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "module_type": self.module_type.value,
            "inputs": [p.value for p in self.inputs],
            "outputs": [p.value for p in self.outputs],
            "params": [p.to_dict() for p in self.params]
        }
