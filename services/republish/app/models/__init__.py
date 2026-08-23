"""
Models Package
"""

# Core models
from .user import User
from .blog import Blog, BlogPlatform
from .category import Topic, SubTopic, Keyword

# Phase 4 models
from .post import Post
from .publish_log import PublishLog

# Group models (레거시)
from .blog_group_link import BlogGroupLink
from .profile_group import ProfileGroup, GroupProfileLink
from .publish_profile import PublishProfile

# Phase 5-1: Google/Blogger models
from .google_credential import GoogleCredential
from .google_account_policy import GoogleAccountPolicy
from .blogger_global_slot import BloggerGlobalSlot
from .daily_publish_counter import DailyPublishCounter

# Phase A-1: Module/Flow models (new schema)
from .module_type import ModuleType
from .module import Module
from .flow import Flow
from .flow_module import FlowModule
from .flow_blog import FlowBlog

# Phase C-4: Autorun models
from .autorun_log import AutorunLog
from .flow_execution_state import FlowExecutionState

# Phase S-1: Settings models
from .user_settings import UserSettings

# Phase S-2: AI API Key Multi-Account models
from .ai_api_key import AIApiKey

# Phase D-1-1: Keyword models
from .keyword import KeywordCategory, SeedKeyword, CollectedKeyword

# Phase D-1-2: Title models
from .title import TitleGroup, MainTitle, TempTitle

# Phase D-1-3: URL History models
from .url_history import BlogUrlHistory

# Phase D-1-4: Learning models
from .learning import FilterLearningData, SimilarityLearningData

# Phase D-1-5: Content Filter models
from .content_filter import ContentFilter

# Phase D-2: Bulk Collection models
from .collected_url import CollectedUrl

# Phase A-041: Bulk Collect 모듈 분리 — 진행 상태
from .bulk_collect_progress import BulkCollectProgress

# 프롬프트 빌더 옵션 블록 (DB화)
from .prompt_block import PromptBlock

# Phase M-1: Crawled Post models (유사도 매칭)
from .crawled_post import CrawledPost

# Phase M-2: Action Log models (동작 로그)
from .action_log import ActionLog

# Phase R-1: Reference Collection models (참조자료 수집)
from .collected_reference import CollectedReference, CrawlLog
from .domain_blacklist import DomainBlacklist

# Phase G-1: Generation models (생성 모듈)
from .generation_history import GenerationHistory
from .blog_growth_setting import BlogGrowthSetting

# Phase MATCH-040: 블로그 × 정식제목 검토 카드
from .blog_main_title_scan import BlogMainTitleScan
from .adsense_account import AdsenseAccount, AdsenseSite

__all__ = [
    # Core models
    "User",
    "Blog",
    "BlogPlatform",
    "Topic",
    "SubTopic",
    "Keyword",
    # Phase 4 models
    "Post",
    "PublishLog",
    # Group models (레거시)
    "BlogGroupLink",
    "ProfileGroup",
    "GroupProfileLink",
    "PublishProfile",
    # Phase 5-1: Google/Blogger models
    "GoogleCredential",
    "GoogleAccountPolicy",
    "BloggerGlobalSlot",
    "DailyPublishCounter",
    # Phase A-1: Module/Flow models
    "ModuleType",
    "Module",
    "Flow",
    "FlowModule",
    "FlowBlog",
    # Phase C-4: Autorun models
    "AutorunLog",
    "FlowExecutionState",
    # Phase S-1: Settings models
    "UserSettings",
    # Phase S-2: AI API Key Multi-Account models
    "AIApiKey",
    # Phase D-1-1: Keyword models
    "KeywordCategory",
    "SeedKeyword",
    "CollectedKeyword",
    # Phase D-1-2: Title models
    "TitleGroup",
    "MainTitle",
    "TempTitle",
    # Phase D-1-3: URL History models
    "BlogUrlHistory",
    # Phase D-1-4: Learning models
    "FilterLearningData",
    "SimilarityLearningData",
    # Phase D-1-5: Content Filter models
    "ContentFilter",
    # Phase D-2: Bulk Collection models
    "CollectedUrl",
    "PromptBlock",
    # Phase A-041: Bulk Collect 모듈 분리 — 진행 상태
    "BulkCollectProgress",
    # Phase M-1: Crawled Post models
    "CrawledPost",
    # Phase M-2: Action Log models
    "ActionLog",
    # Phase R-1: Reference Collection models
    "CollectedReference",
    "CrawlLog",
    "DomainBlacklist",
    # Phase G-1: Generation models
    "GenerationHistory",
    "BlogGrowthSetting",
    # Phase MATCH-040: 검토 카드
    "BlogMainTitleScan",
    # 애드센스 계정·사이트 상태(다중 계정)
    "AdsenseAccount",
    "AdsenseSite",
]
