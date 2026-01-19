"""
테스트용 ExecutionContext 모킹 클래스

shared 모듈 의존성 없이 핵심 로직을 테스트하기 위한 경량화된 클래스들
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4


@dataclass
class BlogData:
    """블로그 데이터 (불변 복사본용)"""
    id: int
    name: str
    url: str
    platform: str
    post_count: int
    last_publish_at: Optional[str] = None
    credential_id: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlogData":
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            url=data.get("url", ""),
            platform=data.get("platform", ""),
            post_count=data.get("post_count", 0),
            last_publish_at=data.get("last_publish_at"),
            credential_id=data.get("credential_id")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "platform": self.platform,
            "post_count": self.post_count,
            "last_publish_at": self.last_publish_at,
            "credential_id": self.credential_id
        }

    def deep_copy(self) -> "BlogData":
        return BlogData(
            id=self.id,
            name=self.name,
            url=self.url,
            platform=self.platform,
            post_count=self.post_count,
            last_publish_at=self.last_publish_at,
            credential_id=self.credential_id
        )


@dataclass
class FilteredQueue:
    """모듈별 필터링된 블로그 큐"""
    queue_id: str
    module_id: int
    module_type: str
    post_range_start: Optional[int]
    post_range_end: Optional[int]
    blogs: list[BlogData] = field(default_factory=list)
    processed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_blog(self, blog: BlogData) -> None:
        self.blogs.append(blog.deep_copy())

    def get_blogs_as_dict(self) -> list[dict[str, Any]]:
        return [b.to_dict() for b in self.blogs]

    @property
    def count(self) -> int:
        return len(self.blogs)


class ExecutionContext:
    """실행 컨텍스트 (테스트용 축소 버전)"""

    def __init__(
        self, flow_id: int, user_id: int, execution_id: Optional[str] = None
    ):
        self.flow_id = flow_id
        self.user_id = user_id
        self.execution_id = execution_id or str(uuid4())
        self.created_at = datetime.now().isoformat()
        self._original_blog_pool: list[BlogData] = []
        self._filtered_queues: dict[int, FilteredQueue] = {}
        self._metadata: dict[str, Any] = {}

    def set_original_pool(self, blogs: list[dict[str, Any]]) -> None:
        self._original_blog_pool = [BlogData.from_dict(b) for b in blogs]

    def get_original_pool(self) -> list[BlogData]:
        return self._original_blog_pool

    @property
    def original_pool_count(self) -> int:
        return len(self._original_blog_pool)

    def create_filtered_queue(
        self, module_id: int, module_type: str,
        post_range_start: Optional[int] = None,
        post_range_end: Optional[int] = None
    ) -> FilteredQueue:
        queue_id = f"queue_{module_id}_{uuid4().hex[:8]}"
        queue = FilteredQueue(
            queue_id=queue_id,
            module_id=module_id,
            module_type=module_type,
            post_range_start=post_range_start,
            post_range_end=post_range_end
        )
        self._filtered_queues[module_id] = queue
        return queue

    def populate_filtered_queue(
        self, module_id: int, filter_func: Optional[callable] = None
    ) -> FilteredQueue:
        queue = self._filtered_queues.get(module_id)
        if not queue:
            raise ValueError(f"Queue not found for module_id={module_id}")

        def default_filter(blog: BlogData) -> bool:
            if queue.post_range_start is not None:
                if blog.post_count < queue.post_range_start:
                    return False
            if queue.post_range_end is not None:
                if blog.post_count > queue.post_range_end:
                    return False
            return True

        actual_filter = filter_func or default_filter

        for blog in self._original_blog_pool:
            if actual_filter(blog):
                queue.add_blog(blog)

        return queue

    def get_filtered_queue(self, module_id: int) -> Optional[FilteredQueue]:
        return self._filtered_queues.get(module_id)

    def get_summary(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "flow_id": self.flow_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "original_pool_count": self.original_pool_count,
            "filtered_queues": {
                mid: {"queue_id": q.queue_id, "count": q.count,
                      "range": f"{q.post_range_start}-{q.post_range_end}",
                      "processed": q.processed}
                for mid, q in self._filtered_queues.items()
            }
        }


def create_execution_context(
    flow_id: int, user_id: int, execution_id: Optional[str] = None
) -> ExecutionContext:
    return ExecutionContext(flow_id, user_id, execution_id)
