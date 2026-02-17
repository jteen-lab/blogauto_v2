"""
생성 모듈 서비스 패키지

설계 문서: generation_module_workplan.md

Phase 2 구현:
- TitleRecombiner: 제목 재조합 서비스
- ReferenceCollector: 참조자료 수집 통합 서비스

Phase 3 구현:
- ContentGenerator: 전체 생성 파이프라인 오케스트레이터
- InternalLinker: 내부링크 삽입 서비스
- SubstitutionProcessor: 치환 처리 서비스

Phase 4 구현:
- InventoryTrigger: 재고 기반 생성 트리거
- FlowGenerateExecutor: 플로우-생성 모듈 실행기

Phase 6 구현:
- InventoryManager: 발행-생성 인터페이스 (재고 관리)
"""
from .title_recombiner import TitleRecombiner, RecombineResult
from .reference_collector import ReferenceCollector, ReferenceCollectionResult
from .generator import ContentGenerator, GenerationResult
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor
from .inventory_trigger import InventoryTrigger, InventoryCheckResult
from .flow_generate_executor import FlowGenerateExecutor
from .inventory_manager import InventoryManager, PublishResult

__all__ = [
    # Phase 2
    "TitleRecombiner",
    "RecombineResult",
    "ReferenceCollector",
    "ReferenceCollectionResult",
    # Phase 3
    "ContentGenerator",
    "GenerationResult",
    "InternalLinker",
    "SubstitutionProcessor",
    # Phase 4
    "InventoryTrigger",
    "InventoryCheckResult",
    "FlowGenerateExecutor",
    # Phase 6
    "InventoryManager",
    "PublishResult",
]
