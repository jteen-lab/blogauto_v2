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
# from .blog_group_link import BlogGroupLink  # 제거됨 (Flow 시스템으로 교체)

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
    # "BlogGroupLink",  # 제거됨
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
]
