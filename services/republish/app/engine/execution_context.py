"""
실행 컨텍스트 (Execution Context)

Features:
- 전체 실행 흐름의 데이터를 담는 Context Pool
- original_blog_pool: 조회된 원본 블로그 목록
- filtered_queues: 모듈별 필터링된 블로그 큐
- 블로그 데이터 deep copy로 독립성 보장
- 실행 경로(Path) 추적
"""
import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger("execution_context")


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
        """딕셔너리에서 BlogData 생성"""
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
        """딕셔너리로 변환"""
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
        """Deep copy 생성"""
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
        """블로그 추가 (deep copy)"""
        self.blogs.append(blog.deep_copy())

    def get_blogs_as_dict(self) -> list[dict[str, Any]]:
        """블로그 목록을 딕셔너리 리스트로 반환"""
        return [b.to_dict() for b in self.blogs]

    @property
    def count(self) -> int:
        """블로그 수"""
        return len(self.blogs)


@dataclass
class ExecutionPath:
    """실행 경로 추적"""
    path_id: str
    source_queue_id: str
    module_sequence: list[int] = field(default_factory=list)
    current_step: int = 0
    status: str = "pending"  # pending, running, completed, failed
    results: list[dict[str, Any]] = field(default_factory=list)


class ExecutionContext:
    """
    실행 컨텍스트

    모든 실행 데이터를 담는 Context Pool입니다.
    - original_blog_pool: BlogFetcher에서 조회된 원본 데이터
    - filtered_queues: 각 분류 모듈별 독립적인 큐
    - execution_paths: 각 큐의 실행 경로 추적
    """

    def __init__(
        self,
        flow_id: int,
        user_id: int,
        execution_id: Optional[str] = None
    ):
        """
        Args:
            flow_id: 플로우 ID
            user_id: 사용자 ID
            execution_id: 실행 ID (선택, 없으면 자동 생성)
        """
        self.flow_id = flow_id
        self.user_id = user_id
        self.execution_id = execution_id or str(uuid4())
        self.created_at = datetime.now().isoformat()

        # 원본 블로그 풀
        self._original_blog_pool: list[BlogData] = []

        # 모듈별 필터링된 큐 (module_id -> FilteredQueue)
        self._filtered_queues: dict[int, FilteredQueue] = {}

        # 실행 경로 추적
        self._execution_paths: dict[str, ExecutionPath] = {}

        # 메타데이터
        self._metadata: dict[str, Any] = {}

        logger.info(
            f"[CONTEXT] 생성 | ExecutionID={self.execution_id} | "
            f"FlowID={flow_id} | UserID={user_id}"
        )

    # ========================================
    # Original Blog Pool 관리
    # ========================================

    def set_original_pool(self, blogs: list[dict[str, Any]]) -> None:
        """
        원본 블로그 풀 설정

        Args:
            blogs: BlogFetcher 출력 (딕셔너리 리스트)
        """
        self._original_blog_pool = [
            BlogData.from_dict(b) for b in blogs
        ]
        logger.info(
            f"[CONTEXT] Original Pool 설정 | "
            f"블로그 수={len(self._original_blog_pool)}"
        )

    def get_original_pool(self) -> list[BlogData]:
        """원본 블로그 풀 조회 (읽기 전용)"""
        return self._original_blog_pool

    def get_original_pool_as_dict(self) -> list[dict[str, Any]]:
        """원본 블로그 풀을 딕셔너리 리스트로 반환"""
        return [b.to_dict() for b in self._original_blog_pool]

    @property
    def original_pool_count(self) -> int:
        """원본 블로그 수"""
        return len(self._original_blog_pool)

    # ========================================
    # Filtered Queue 관리
    # ========================================

    def create_filtered_queue(
        self,
        module_id: int,
        module_type: str,
        post_range_start: Optional[int] = None,
        post_range_end: Optional[int] = None
    ) -> FilteredQueue:
        """
        새로운 필터링 큐 생성

        Args:
            module_id: 모듈 ID
            module_type: 모듈 타입 코드
            post_range_start: 포스트 범위 시작
            post_range_end: 포스트 범위 끝

        Returns:
            생성된 FilteredQueue
        """
        queue_id = f"queue_{module_id}_{uuid4().hex[:8]}"

        queue = FilteredQueue(
            queue_id=queue_id,
            module_id=module_id,
            module_type=module_type,
            post_range_start=post_range_start,
            post_range_end=post_range_end
        )

        self._filtered_queues[module_id] = queue

        logger.info(
            f"[CONTEXT] Filtered Queue 생성 | "
            f"QueueID={queue_id} | ModuleID={module_id} | "
            f"Range={post_range_start}-{post_range_end}"
        )

        return queue

    def populate_filtered_queue(
        self,
        module_id: int,
        filter_func: Optional[callable] = None
    ) -> FilteredQueue:
        """
        원본 풀에서 필터링하여 큐 채우기

        원본 블로그 데이터를 deep copy하여 독립적인 큐 생성

        Args:
            module_id: 대상 모듈 ID
            filter_func: 필터 함수 (blog: BlogData) -> bool
                        None이면 범위 조건만 사용

        Returns:
            채워진 FilteredQueue
        """
        queue = self._filtered_queues.get(module_id)
        if not queue:
            raise ValueError(f"Queue not found for module_id={module_id}")

        # 범위 기반 기본 필터
        def default_filter(blog: BlogData) -> bool:
            if queue.post_range_start is not None:
                if blog.post_count < queue.post_range_start:
                    return False
            if queue.post_range_end is not None:
                if blog.post_count > queue.post_range_end:
                    return False
            return True

        # 필터 적용
        actual_filter = filter_func or default_filter

        for blog in self._original_blog_pool:
            if actual_filter(blog):
                queue.add_blog(blog)  # deep copy됨

        logger.info(
            f"[CONTEXT] Queue 채우기 완료 | "
            f"ModuleID={module_id} | 결과={queue.count}개"
        )

        return queue

    def get_filtered_queue(self, module_id: int) -> Optional[FilteredQueue]:
        """특정 모듈의 필터링 큐 조회"""
        return self._filtered_queues.get(module_id)

    def get_all_filtered_queues(self) -> dict[int, FilteredQueue]:
        """모든 필터링 큐 조회"""
        return self._filtered_queues

    # ========================================
    # Execution Path 관리
    # ========================================

    def create_execution_path(
        self,
        source_queue_id: str,
        module_sequence: list[int]
    ) -> ExecutionPath:
        """
        실행 경로 생성

        Args:
            source_queue_id: 소스 큐 ID
            module_sequence: 실행할 모듈 ID 시퀀스

        Returns:
            생성된 ExecutionPath
        """
        path_id = f"path_{uuid4().hex[:8]}"

        path = ExecutionPath(
            path_id=path_id,
            source_queue_id=source_queue_id,
            module_sequence=module_sequence
        )

        self._execution_paths[path_id] = path

        logger.info(
            f"[CONTEXT] Execution Path 생성 | "
            f"PathID={path_id} | Modules={module_sequence}"
        )

        return path

    def update_path_status(
        self,
        path_id: str,
        status: str,
        result: Optional[dict[str, Any]] = None
    ) -> None:
        """실행 경로 상태 업데이트"""
        path = self._execution_paths.get(path_id)
        if path:
            path.status = status
            if result:
                path.results.append(result)

    # ========================================
    # 메타데이터 관리
    # ========================================

    def set_metadata(self, key: str, value: Any) -> None:
        """메타데이터 설정"""
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """메타데이터 조회"""
        return self._metadata.get(key, default)

    # ========================================
    # 요약 및 직렬화
    # ========================================

    def get_summary(self) -> dict[str, Any]:
        """실행 컨텍스트 요약"""
        return {
            "execution_id": self.execution_id,
            "flow_id": self.flow_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "original_pool_count": self.original_pool_count,
            "filtered_queues": {
                mid: {
                    "queue_id": q.queue_id,
                    "count": q.count,
                    "range": f"{q.post_range_start}-{q.post_range_end}",
                    "processed": q.processed
                }
                for mid, q in self._filtered_queues.items()
            },
            "execution_paths": {
                pid: {
                    "status": p.status,
                    "current_step": p.current_step,
                    "total_steps": len(p.module_sequence)
                }
                for pid, p in self._execution_paths.items()
            }
        }

    def to_dict(self) -> dict[str, Any]:
        """전체 컨텍스트를 딕셔너리로 변환"""
        return {
            "execution_id": self.execution_id,
            "flow_id": self.flow_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "original_blog_pool": self.get_original_pool_as_dict(),
            "filtered_queues": {
                str(mid): {
                    "queue_id": q.queue_id,
                    "module_id": q.module_id,
                    "module_type": q.module_type,
                    "range": [q.post_range_start, q.post_range_end],
                    "blogs": q.get_blogs_as_dict(),
                    "processed": q.processed
                }
                for mid, q in self._filtered_queues.items()
            },
            "metadata": self._metadata
        }


def create_execution_context(
    flow_id: int,
    user_id: int,
    execution_id: Optional[str] = None
) -> ExecutionContext:
    """
    ExecutionContext 팩토리 함수

    Args:
        flow_id: 플로우 ID
        user_id: 사용자 ID
        execution_id: 실행 ID (선택)

    Returns:
        ExecutionContext 인스턴스
    """
    return ExecutionContext(flow_id, user_id, execution_id)
