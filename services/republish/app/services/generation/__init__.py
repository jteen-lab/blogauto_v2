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

Phase D 구현:
- WarmupManager: 워밍업 판단 서비스 (신규 블로그 발행 점진 증가)
- WarmupStatus: 워밍업 상태 판단 결과
- Publisher: 발행 오케스트레이터 (재고 조회 + 워밍업 체크 + 상태 업데이트)

Growth Profile (Phase A):
- FlowExecutionContext: 플로우 실행 컨텍스트 (스테이지별 파라미터)
- GrowthProfileResolver: 성장 프로파일 → 스테이지 파라미터 해석
- growth_profile_defaults: 기본 프로파일 정의 및 유틸리티
"""
from .title_recombiner import TitleRecombiner, RecombineResult
from .reference_collector import ReferenceCollector, ReferenceCollectionResult
from .generator import ContentGenerator, GenerationResult
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor
from .inventory_trigger import InventoryTrigger, InventoryCheckResult
from .flow_generate_executor import FlowGenerateExecutor
from .inventory_manager import InventoryManager, PublishResult
# Phase D
from .warmup_manager import WarmupManager, WarmupStatus
from .publisher import Publisher
# Growth Profile (Phase A)
from .flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)
from .growth_profile_resolver import GrowthProfileResolver
from .growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)

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
    # Phase D
    "WarmupManager",
    "WarmupStatus",
    "Publisher",
    # Growth Profile (Phase A)
    "FlowExecutionContext",
    "StageParams",
    "ModuleIntervalParams",
    "GrowthProfileResolver",
    "DEFAULT_PROFILES",
    "get_default_profile",
    "get_available_profiles",
]
