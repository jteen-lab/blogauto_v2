"""Redis 기반 AI 프로바이더 Rate Limiter 모듈.

슬라이딩 윈도우 방식으로 AI 프로바이더별 분당 호출 수를 제한합니다.
환경변수로 제한값을 오버라이드할 수 있습니다:
  - RATELIMIT_OPENAI_RPM / RATELIMIT_OPENAI_TPM
  - RATELIMIT_ANTHROPIC_RPM / RATELIMIT_ANTHROPIC_TPM
  - RATELIMIT_GOOGLE_RPM / RATELIMIT_GOOGLE_TPM
"""

import os
import redis
from typing import Dict, Tuple

from .logger import get_logger

logger = get_logger("rate_limiter", "app.log")

# 모듈 레벨 상수: 환경변수로 오버라이드 가능
DEFAULT_LIMITS: Dict[str, Dict[str, int]] = {
    "openai": {
        "rpm": int(os.getenv("RATELIMIT_OPENAI_RPM", "60")),
        "tpm": int(os.getenv("RATELIMIT_OPENAI_TPM", "90000")),
    },
    "anthropic": {
        "rpm": int(os.getenv("RATELIMIT_ANTHROPIC_RPM", "50")),
        "tpm": int(os.getenv("RATELIMIT_ANTHROPIC_TPM", "80000")),
    },
    "google": {
        "rpm": int(os.getenv("RATELIMIT_GOOGLE_RPM", "60")),
        "tpm": int(os.getenv("RATELIMIT_GOOGLE_TPM", "120000")),
    },
}


class AIRateLimiter:
    """Redis 기반 슬라이딩 윈도우 Rate Limiter.

    AI 프로바이더별 분당 호출 수(RPM)를 추적하고 제한합니다.
    Redis INCR + EXPIRE로 1분 윈도우 카운터를 구현합니다.

    제한값은 모듈 로드 시 환경변수에서 읽어옵니다 (DEFAULT_LIMITS 참조).
    """

    LIMITS: Dict[str, Dict[str, int]] = DEFAULT_LIMITS

    def __init__(self, redis_client: redis.Redis) -> None:
        """AIRateLimiter 초기화.

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client
        self.key_prefix = "blogauto:ratelimit"

    def can_call(self, provider: str) -> Tuple[bool, int]:
        """호출 가능 여부 확인.

        Args:
            provider: AI 프로바이더명 ("openai" | "anthropic" | "google")

        Returns:
            (호출 가능 여부, 대기 필요 시간(초))
            호출 가능하면 (True, 0), 불가하면 (False, 남은 대기 초)
        """
        key = f"{self.key_prefix}:{provider}:rpm"
        current = self.redis.get(key)
        limit = self.LIMITS.get(provider, {}).get("rpm", 60)

        if current and int(current) >= limit:
            ttl = self.redis.ttl(key)
            logger.info(
                f"[RATE_LIMIT] 제한 초과 | provider={provider} "
                f"| current={current}/{limit} | wait={ttl}s"
            )
            return False, max(ttl, 1)

        return True, 0

    def record_call(self, provider: str, tokens_used: int = 0) -> None:
        """호출 기록.

        RPM 카운터를 증가시키고 1분 만료를 설정합니다.

        Args:
            provider: AI 프로바이더명
            tokens_used: 사용된 토큰 수 (향후 TPM 제한용)
        """
        rpm_key = f"{self.key_prefix}:{provider}:rpm"
        pipe = self.redis.pipeline()
        pipe.incr(rpm_key)
        pipe.expire(rpm_key, 60)  # 1분 윈도우
        pipe.execute()

    def get_usage(self, provider: str) -> Dict[str, object]:
        """현재 사용량 조회.

        Args:
            provider: AI 프로바이더명

        Returns:
            사용량 정보 딕셔너리
            (provider, current, limit, remaining, reset_in_seconds)
        """
        rpm_key = f"{self.key_prefix}:{provider}:rpm"
        current = self.redis.get(rpm_key)
        limit = self.LIMITS.get(provider, {}).get("rpm", 60)
        ttl = self.redis.ttl(rpm_key) if current else 0

        return {
            "provider": provider,
            "current": int(current) if current else 0,
            "limit": limit,
            "remaining": limit - (int(current) if current else 0),
            "reset_in_seconds": max(ttl, 0),
        }
