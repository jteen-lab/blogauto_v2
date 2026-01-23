"""
BlogAuto V2 모듈 패키지

NOTE: 노드 방식은 더 이상 사용하지 않습니다.
플로우 실행은 flows_execute.py와 flow_scheduler.py에서
직접 서비스를 호출하는 방식으로 동작합니다.

이 파일은 하위 호환성을 위해 유지되지만,
새로운 모듈은 services/ 디렉토리에 서비스로 구현하세요.
"""

from app.core.registry import ModuleRegistry

# 트리거 모듈 (레거시)
from app.modules.triggers.schedule import ScheduleTriggerModule
from app.modules.triggers.manual import ManualTriggerModule

# 데이터 모듈 (레거시)
from app.modules.data.db_query import DBQueryModule
from app.modules.data.db_save import DBSaveModule
from app.modules.data.post_selector import PostSelectorModule
from app.modules.data.keyword_loader import KeywordLoaderModule
from app.modules.data.title_collector import TitleCollectorModule

# 액션 모듈 (레거시)
from app.modules.actions.publish import PublishModule


def register_all_modules():
    """
    모든 기본 모듈 등록 (레거시 호환용)

    NOTE: 이 함수는 하위 호환성을 위해 유지됩니다.
    실제 모듈 실행은 flows_execute.py와 flow_scheduler.py에서
    직접 서비스를 호출합니다.
    """
    # 트리거 (레거시)
    ModuleRegistry.register(ScheduleTriggerModule())
    ModuleRegistry.register(ManualTriggerModule())

    # 데이터 - 재발행용 (레거시)
    ModuleRegistry.register(DBQueryModule())
    ModuleRegistry.register(DBSaveModule())
    ModuleRegistry.register(PostSelectorModule())

    # 데이터 - 수집용 (레거시)
    ModuleRegistry.register(KeywordLoaderModule())
    ModuleRegistry.register(TitleCollectorModule())

    # 액션 (레거시)
    ModuleRegistry.register(PublishModule())


__all__ = [
    "register_all_modules",
    "ScheduleTriggerModule",
    "ManualTriggerModule",
    "DBQueryModule",
    "DBSaveModule",
    "PostSelectorModule",
    "KeywordLoaderModule",
    "TitleCollectorModule",
    "PublishModule",
]
