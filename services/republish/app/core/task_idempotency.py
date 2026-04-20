"""작업 멱등성 관리 모듈.

플로우 스케줄러가 동일 blog+module 조합을
짧은 시간 내 중복 실행하는 것을 방지합니다.
"""

import redis

from .logger import get_logger

logger = get_logger("task_idempotency", "app.log")


class DuplicateTaskError(Exception):
    """중복 작업 에러.

    이미 처리 중이거나 최근 처리된 작업을 재실행하려 할 때 발생합니다.
    """

    def __init__(self, task_key: str) -> None:
        """DuplicateTaskError 초기화.

        Args:
            task_key: 중복된 작업의 고유 키
        """
        self.task_key = task_key
        super().__init__(f"중복 작업: {task_key}")


class TaskIdempotency:
    """동일 작업의 중복 실행 방지.

    플로우 스케줄러가 같은 blog+module 조합을
    짧은 시간 내 중복 발행하는 것을 방지합니다.
    Redis SET NX + EX로 중복 판단 윈도우를 구현합니다.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """TaskIdempotency 초기화.

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client
        self.key_prefix = "blogauto:task:dedup"

    def is_duplicate(self, task_key: str, window_seconds: int = 300) -> bool:
        """중복 여부 확인.

        키가 이미 존재하면 중복으로 판단합니다.
        존재하지 않으면 키를 생성하고 윈도우 시간 후 자동 만료됩니다.

        Args:
            task_key: 작업 고유 키
                예: "generate:blog_1:module_5:title_123"
            window_seconds: 중복 판단 윈도우(초). 기본 5분(300초)

        Returns:
            중복 여부 (True면 중복)
        """
        key = f"{self.key_prefix}:{task_key}"

        if self.redis.exists(key):
            logger.info(f"[DEDUP] 중복 작업 감지 | key={task_key}")
            return True

        self.redis.set(key, "1", ex=window_seconds)
        return False

    def clear(self, task_key: str) -> None:
        """중복 방지 키 수동 제거.

        작업 실패 시 재시도를 허용하기 위해 키를 삭제합니다.

        Args:
            task_key: 제거할 작업 고유 키
        """
        key = f"{self.key_prefix}:{task_key}"
        self.redis.delete(key)
        logger.debug(f"[DEDUP] 키 제거 | key={task_key}")
