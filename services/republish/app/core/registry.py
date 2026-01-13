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
        """
        모듈 등록

        Args:
            module: 등록할 모듈 인스턴스
        """
        cls._modules[module.name] = module

    @classmethod
    def unregister(cls, name: str) -> None:
        """
        모듈 등록 해제

        Args:
            name: 모듈 이름
        """
        if name in cls._modules:
            del cls._modules[name]

    @classmethod
    def get(cls, name: str) -> Optional[ModuleInterface]:
        """
        모듈 조회

        Args:
            name: 모듈 이름

        Returns:
            ModuleInterface or None
        """
        return cls._modules.get(name)

    @classmethod
    def get_all(cls) -> list[ModuleInterface]:
        """전체 모듈 목록"""
        return list(cls._modules.values())

    @classmethod
    def get_by_type(cls, module_type: ModuleType) -> list[ModuleInterface]:
        """
        타입별 모듈 목록

        Args:
            module_type: 필터링할 모듈 타입

        Returns:
            list[ModuleInterface]: 해당 타입의 모듈 목록
        """
        return [m for m in cls._modules.values() if m.module_type == module_type]

    @classmethod
    def to_dict(cls) -> dict:
        """
        모듈 목록 직렬화 (API용)

        Returns:
            dict: 타입별로 그룹화된 모듈 목록
        """
        result = {}
        for module_type in ModuleType:
            modules = cls.get_by_type(module_type)
            result[module_type.value] = [m.to_dict() for m in modules]
        return result

    @classmethod
    def clear(cls) -> None:
        """전체 초기화 (테스트용)"""
        cls._modules.clear()

    @classmethod
    def count(cls) -> int:
        """등록된 모듈 수"""
        return len(cls._modules)

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """모듈 등록 여부 확인"""
        return name in cls._modules
