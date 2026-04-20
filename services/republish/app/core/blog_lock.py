"""Redis 기반 블로그 단위 분산 락 모듈.

동일 블로그에 대한 동시 작업(생성, 발행 등)을 방지합니다.
"""

import redis

from .logger import get_logger

logger = get_logger("blog_lock", "app.log")


class BlogLock:
    """Redis 기반 블로그 단위 분산 락.

    동일 블로그에 대한 동시 작업을 방지합니다.
    SET NX + EX를 사용하여 원자적 락 획득을 보장합니다.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """BlogLock 초기화.

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client
        self.lock_prefix = "blogauto:lock:blog"
        self.default_ttl = 600  # 10분

    def acquire(self, blog_id: int, task_type: str, ttl: int = None) -> bool:
        """블로그 락 획득 시도.

        키: blogauto:lock:blog:{blog_id}:{task_type}

        Args:
            blog_id: 블로그 ID
            task_type: 작업 유형 ("generate" | "publish" | "all")
            ttl: 락 만료 시간(초). None이면 default_ttl(600초) 사용

        Returns:
            락 획득 성공 여부
        """
        key = f"{self.lock_prefix}:{blog_id}:{task_type}"
        acquired = self.redis.set(key, "locked", nx=True, ex=ttl or self.default_ttl)

        if acquired:
            logger.debug(
                f"[BLOG_LOCK] 락 획득 | blog_id={blog_id} | type={task_type}"
            )
        else:
            logger.info(
                f"[BLOG_LOCK] 락 획득 실패 (이미 잠김) | blog_id={blog_id} | type={task_type}"
            )

        return bool(acquired)

    def release(self, blog_id: int, task_type: str) -> None:
        """블로그 락 해제.

        Args:
            blog_id: 블로그 ID
            task_type: 작업 유형 ("generate" | "publish" | "all")
        """
        key = f"{self.lock_prefix}:{blog_id}:{task_type}"
        self.redis.delete(key)
        logger.debug(
            f"[BLOG_LOCK] 락 해제 | blog_id={blog_id} | type={task_type}"
        )

    def is_locked(self, blog_id: int, task_type: str) -> bool:
        """블로그 락 상태 확인.

        Args:
            blog_id: 블로그 ID
            task_type: 작업 유형 ("generate" | "publish" | "all")

        Returns:
            잠김 여부
        """
        key = f"{self.lock_prefix}:{blog_id}:{task_type}"
        return self.redis.exists(key) > 0
