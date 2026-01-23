"""
데이터 모듈 (레거시)

NOTE: 노드 기반은 더 이상 사용하지 않습니다.
제목 이동 등의 데이터 처리는 flows_execute.py와 flow_scheduler.py에서
TitleTransferService를 직접 호출합니다.
"""

from app.modules.data.db_query import DBQueryModule
from app.modules.data.db_save import DBSaveModule
from app.modules.data.post_selector import PostSelectorModule
from app.modules.data.keyword_loader import KeywordLoaderModule
from app.modules.data.title_collector import TitleCollectorModule

__all__ = [
    "DBQueryModule",
    "DBSaveModule",
    "PostSelectorModule",
    "KeywordLoaderModule",
    "TitleCollectorModule",
]
