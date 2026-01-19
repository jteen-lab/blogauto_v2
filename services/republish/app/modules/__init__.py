"""
BlogAuto V2 모듈 패키지

노드 방식 모듈들을 등록합니다.
"""

from app.core.registry import ModuleRegistry

# 트리거 모듈
from app.modules.triggers.schedule import ScheduleTriggerModule
from app.modules.triggers.manual import ManualTriggerModule

# 데이터 모듈
from app.modules.data.db_query import DBQueryModule
from app.modules.data.db_save import DBSaveModule
from app.modules.data.post_selector import PostSelectorModule
from app.modules.data.keyword_loader import KeywordLoaderModule
from app.modules.data.title_collector import TitleCollectorModule

# 액션 모듈
from app.modules.actions.publish import PublishModule


def register_all_modules():
    """모든 기본 모듈 등록"""
    # 트리거
    ModuleRegistry.register(ScheduleTriggerModule())
    ModuleRegistry.register(ManualTriggerModule())

    # 데이터 - 재발행용
    ModuleRegistry.register(DBQueryModule())
    ModuleRegistry.register(DBSaveModule())
    ModuleRegistry.register(PostSelectorModule())

    # 데이터 - 수집용
    ModuleRegistry.register(KeywordLoaderModule())
    ModuleRegistry.register(TitleCollectorModule())

    # 액션
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
