"""
모듈 표준 인터페이스
- ModuleType: 모듈 유형 Enum
- ModuleInterface: 모듈 베이스 클래스 (ABC)
- ModuleExecutionError: 모듈 실행 오류
"""
from abc import ABC, abstractmethod
from typing import Any
from enum import Enum


class ModuleType(str, Enum):
    """모듈 유형"""
    COLLECTION = "collection"      # 수집 (키워드, 제목)
    PROCESSING = "processing"      # 처리 (필터링, 분류, 유사도)
    GENERATION = "generation"      # 생성 (프롬프트, AI API)
    PUBLISHING = "publishing"      # 발행 (재발행, 신규발행)
    CONTROL = "control"            # 제어 (조건문)


class ModuleInterface(ABC):
    """
    모듈 표준 인터페이스. 모든 모듈은 이 인터페이스를 상속받아 구현합니다.
    플로우 내에서 모듈 간 데이터 전달을 표준화합니다.
    """
    # 메타 정보 (서브클래스에서 오버라이드)
    module_type: ModuleType = ModuleType.PROCESSING
    module_name: str = ""
    module_description: str = ""

    # Input/Output 스키마
    input_schema: dict = {"required": [], "optional": []}
    output_schema: dict = {"provides": []}

    @abstractmethod
    def execute_module(self, inputs: dict | None = None) -> dict:
        """
        모듈 실행 (플로우 연결용)
        Args:
            inputs: 이전 모듈에서 전달받은 데이터 (None이면 설정값 사용)
        Returns:
            다음 모듈로 전달할 데이터 (output_schema.provides 키 포함)
        Raises:
            ModuleExecutionError: 실행 중 오류 발생
        Note:
            기존 execute() 메서드와 충돌 방지를 위해 execute_module로 명명
        """
        pass

    def validate_inputs(self, inputs: dict | None) -> tuple[bool, str | None]:
        """입력값 검증. Returns: (is_valid, error_message)"""
        if not inputs:
            if self.input_schema["required"]:
                return False, f"Missing required inputs: {self.input_schema['required']}"
            return True, None
        for key in self.input_schema["required"]:
            if key not in inputs:
                return False, f"Missing required input: {key}"
        return True, None

    def get_input_value(
        self, inputs: dict | None, key: str, default: Any = None, fallback_config: dict | None = None
    ) -> Any:
        """입력값 가져오기. 우선순위: inputs[key] > fallback_config[key] > default"""
        if inputs and key in inputs:
            return inputs[key]
        if fallback_config and key in fallback_config:
            return fallback_config[key]
        return default

    def create_output(self, **kwargs) -> dict:
        """출력 데이터 생성. output_schema.provides에 정의된 키만 포함하여 반환"""
        return {key: kwargs.get(key) for key in self.output_schema["provides"]}

    def get_schema_info(self) -> dict:
        """모듈 스키마 정보 반환"""
        return {
            "module_type": self.module_type.value,
            "module_name": self.module_name,
            "module_description": self.module_description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


class ModuleExecutionError(Exception):
    """모듈 실행 오류"""
    def __init__(self, module_name: str, message: str, details: dict | None = None):
        self.module_name = module_name
        self.message = message
        self.details = details or {}
        super().__init__(f"[{module_name}] {message}")
