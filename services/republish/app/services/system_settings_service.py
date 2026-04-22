"""시스템 설정 조회 서비스 (캐시 적용).

DB → .env → 기본값 순서로 조회하며, 메모리 캐시로 성능을 보장합니다.
"""
import os
import time
import logging
from typing import Optional, Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, dict] = {
    "use_celery_generation": {"value": "false", "type": "bool", "category": "celery", "desc": "글 생성 워커 사용"},
    "use_celery_publish": {"value": "false", "type": "bool", "category": "celery", "desc": "발행 워커 사용"},
    "use_celery_image": {"value": "false", "type": "bool", "category": "celery", "desc": "이미지 생성 워커 사용"},
    "use_celery_utility": {"value": "false", "type": "bool", "category": "celery", "desc": "유틸리티 워커 사용"},
    "ratelimit_openai_rpm": {"value": "60", "type": "int", "category": "ratelimit", "desc": "OpenAI 분당 요청 제한"},
    "ratelimit_openai_tpm": {"value": "90000", "type": "int", "category": "ratelimit", "desc": "OpenAI 분당 토큰 제한"},
    "ratelimit_anthropic_rpm": {"value": "50", "type": "int", "category": "ratelimit", "desc": "Anthropic 분당 요청 제한"},
    "ratelimit_anthropic_tpm": {"value": "80000", "type": "int", "category": "ratelimit", "desc": "Anthropic 분당 토큰 제한"},
    "ratelimit_google_rpm": {"value": "60", "type": "int", "category": "ratelimit", "desc": "Google 분당 요청 제한"},
    "ratelimit_google_tpm": {"value": "120000", "type": "int", "category": "ratelimit", "desc": "Google 분당 토큰 제한"},
}

_ENV_MAP = {
    "use_celery_generation": "USE_CELERY_GENERATION",
    "use_celery_publish": "USE_CELERY_PUBLISH",
    "use_celery_image": "USE_CELERY_IMAGE",
    "use_celery_utility": "USE_CELERY_UTILITY",
    "ratelimit_openai_rpm": "RATELIMIT_OPENAI_RPM",
    "ratelimit_openai_tpm": "RATELIMIT_OPENAI_TPM",
    "ratelimit_anthropic_rpm": "RATELIMIT_ANTHROPIC_RPM",
    "ratelimit_anthropic_tpm": "RATELIMIT_ANTHROPIC_TPM",
    "ratelimit_google_rpm": "RATELIMIT_GOOGLE_RPM",
    "ratelimit_google_tpm": "RATELIMIT_GOOGLE_TPM",
}


class SystemSettingsService:
    """시스템 설정 조회 서비스.

    조회 우선순위: 메모리 캐시 → DB → .env → 기본값
    """

    _cache: Dict[str, Any] = {}
    _cache_ts: float = 0
    _cache_ttl: int = 60

    @classmethod
    def invalidate_cache(cls) -> None:
        """캐시 즉시 무효화."""
        cls._cache.clear()
        cls._cache_ts = 0

    @classmethod
    async def _load_all(cls, db: AsyncSession) -> None:
        """DB에서 전체 설정 로드 → 캐시."""
        from ..models.system_settings import SystemSettings
        result = await db.execute(select(SystemSettings))
        rows = result.scalars().all()
        cls._cache = {r.key: r.value for r in rows}
        cls._cache_ts = time.time()

    @classmethod
    async def get(
        cls, key: str, db: AsyncSession, default: Any = None,
    ) -> Optional[str]:
        """설정값 조회 (캐시 → DB → .env → 기본값)."""
        if time.time() - cls._cache_ts < cls._cache_ttl and key in cls._cache:
            return cls._cache[key]

        if time.time() - cls._cache_ts >= cls._cache_ttl:
            try:
                await cls._load_all(db)
            except Exception as e:
                logger.debug(f"[SYS_SETTINGS] DB 로드 실패: {e}")

        if key in cls._cache and cls._cache[key] is not None:
            return cls._cache[key]

        env_key = _ENV_MAP.get(key, key.upper())
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val

        info = DEFAULTS.get(key)
        return info["value"] if info else (default if default is not None else None)

    @classmethod
    async def get_bool(
        cls, key: str, db: AsyncSession, default: bool = False,
    ) -> bool:
        """bool 설정값 조회."""
        val = await cls.get(key, db, str(default).lower())
        return str(val).lower() in ("true", "1", "yes")

    @classmethod
    async def get_int(
        cls, key: str, db: AsyncSession, default: int = 0,
    ) -> int:
        """int 설정값 조회."""
        val = await cls.get(key, db, str(default))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @classmethod
    async def get_all(cls, db: AsyncSession) -> Dict[str, Any]:
        """전체 설정 조회 (UI용)."""
        if time.time() - cls._cache_ts >= cls._cache_ttl:
            await cls._load_all(db)

        result = {}
        for key, info in DEFAULTS.items():
            val = cls._cache.get(key) or os.environ.get(
                _ENV_MAP.get(key, ""), info["value"]
            )
            result[key] = {
                "value": val,
                "type": info["type"],
                "category": info["category"],
                "description": info["desc"],
            }
        return result

    @classmethod
    async def set(
        cls, key: str, value: str, db: AsyncSession,
    ) -> None:
        """설정값 저장."""
        from ..models.system_settings import SystemSettings
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            info = DEFAULTS.get(key, {})
            db.add(SystemSettings(
                key=key, value=value,
                value_type=info.get("type", "string"),
                category=info.get("category", "system"),
                description=info.get("desc", ""),
            ))
        cls._cache[key] = value

    @classmethod
    async def set_many(
        cls, updates: Dict[str, str], db: AsyncSession,
    ) -> None:
        """여러 설정값 일괄 저장."""
        for key, value in updates.items():
            await cls.set(key, value, db)
        await db.commit()
        cls._cache_ts = time.time()

    @classmethod
    async def ensure_defaults(cls, db: AsyncSession) -> None:
        """DB에 기본 설정이 없으면 삽입."""
        from ..models.system_settings import SystemSettings
        for key, info in DEFAULTS.items():
            result = await db.execute(
                select(SystemSettings).where(SystemSettings.key == key)
            )
            if not result.scalar_one_or_none():
                db.add(SystemSettings(
                    key=key, value=info["value"],
                    value_type=info["type"],
                    category=info["category"],
                    description=info["desc"],
                ))
        await db.commit()
