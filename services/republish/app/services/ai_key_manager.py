"""
AI API 키 관리 서비스

Features:
- 우선순위 기반 키 선택
- Rate limit 시 자동 다음 키로 전환
- 사용량 및 오류 추적
- 키 상태 관리
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_api_key import AIApiKey
from ..schemas.ai_api_key import (
    AIProvider,
    AIKeyStatus,
    AIApiKeyCreate,
    AIApiKeyUpdate,
    AIApiKeyPriorityUpdate,
)

logger = logging.getLogger(__name__)


class AIKeyManager:
    """AI API 키 관리 서비스"""

    # Rate limit 복구 대기 시간 (분)
    RATE_LIMIT_COOLDOWN_MINUTES = 60

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id

    async def get_available_key(
        self,
        provider: AIProvider,
        exclude_ids: Optional[List[int]] = None
    ) -> Optional[AIApiKey]:
        """
        사용 가능한 API 키 조회 (우선순위 순)

        Args:
            provider: AI 서비스 제공자
            exclude_ids: 제외할 키 ID 목록

        Returns:
            사용 가능한 AIApiKey 또는 None
        """
        query = select(AIApiKey).where(
            and_(
                AIApiKey.user_id == self.user_id,
                AIApiKey.provider == provider.value,
                AIApiKey.is_active == True,
                AIApiKey.status == AIKeyStatus.ACTIVE.value,
            )
        ).order_by(AIApiKey.priority)

        if exclude_ids:
            query = query.where(AIApiKey.id.notin_(exclude_ids))

        # 우선순위로 정렬해 **첫 번째**를 쓴다.
        # scalar_one_or_none() 을 쓰면 키를 2개 이상 등록한 순간
        # MultipleResultsFound 가 나서 그 제공자를 아예 못 쓰게 된다.
        # 키를 여러 개 두는 것은 rate limit 대비 설계라 정상 상황이다.
        result = await self.db.execute(query.limit(1))
        return result.scalars().first()

    async def get_next_available_key(
        self,
        provider: AIProvider,
        current_key_id: int
    ) -> Optional[AIApiKey]:
        """
        현재 키 다음으로 사용 가능한 키 조회

        Args:
            provider: AI 서비스 제공자
            current_key_id: 현재 사용 중인 키 ID

        Returns:
            다음 사용 가능한 AIApiKey 또는 None
        """
        return await self.get_available_key(
            provider,
            exclude_ids=[current_key_id]
        )

    async def mark_key_used(self, key_id: int) -> None:
        """키 사용 기록"""
        await self.db.execute(
            update(AIApiKey)
            .where(AIApiKey.id == key_id)
            .values(
                last_used_at=datetime.utcnow(),
                usage_count=AIApiKey.usage_count + 1
            )
        )
        await self.db.commit()
        logger.debug(f"[AI_KEY] 키 사용 기록: id={key_id}")

    async def mark_key_rate_limited(self, key_id: int) -> Optional[AIApiKey]:
        """
        Rate limit 상태로 표시하고 다음 키 반환

        Args:
            key_id: Rate limit된 키 ID

        Returns:
            다음 사용 가능한 키 또는 None
        """
        # 현재 키 조회
        result = await self.db.execute(
            select(AIApiKey).where(AIApiKey.id == key_id)
        )
        current_key = result.scalar_one_or_none()

        if not current_key:
            logger.warning(f"[AI_KEY] 키를 찾을 수 없음: id={key_id}")
            return None

        # Rate limit 상태로 변경
        await self.db.execute(
            update(AIApiKey)
            .where(AIApiKey.id == key_id)
            .values(
                status=AIKeyStatus.RATE_LIMITED.value,
                error_count=AIApiKey.error_count + 1,
                last_error_at=datetime.utcnow(),
                last_error_message="Rate limit exceeded"
            )
        )
        await self.db.commit()
        logger.info(f"[AI_KEY] Rate limit 발생: id={key_id}, provider={current_key.provider}")

        # 다음 키 반환
        next_key = await self.get_next_available_key(
            AIProvider(current_key.provider),
            key_id
        )

        if next_key:
            logger.info(f"[AI_KEY] 다음 키로 전환: id={next_key.id}, label={next_key.label}")
        else:
            logger.warning(f"[AI_KEY] 사용 가능한 다음 키 없음: provider={current_key.provider}")

        return next_key

    async def mark_key_error(
        self,
        key_id: int,
        error_message: str
    ) -> None:
        """오류 상태로 표시"""
        await self.db.execute(
            update(AIApiKey)
            .where(AIApiKey.id == key_id)
            .values(
                status=AIKeyStatus.ERROR.value,
                error_count=AIApiKey.error_count + 1,
                last_error_at=datetime.utcnow(),
                last_error_message=error_message[:500]  # 메시지 길이 제한
            )
        )
        await self.db.commit()
        logger.error(f"[AI_KEY] 키 오류: id={key_id}, error={error_message[:100]}")

    async def reset_key_status(self, key_id: int) -> None:
        """키 상태 초기화 (활성 상태로 복구)"""
        await self.db.execute(
            update(AIApiKey)
            .where(AIApiKey.id == key_id)
            .values(
                status=AIKeyStatus.ACTIVE.value,
                last_error_message=None
            )
        )
        await self.db.commit()
        logger.info(f"[AI_KEY] 키 상태 초기화: id={key_id}")

    async def reset_rate_limited_keys(self) -> int:
        """
        쿨다운 시간이 지난 Rate limit 키들을 활성 상태로 복구

        Returns:
            복구된 키 개수
        """
        cooldown_time = datetime.utcnow() - timedelta(
            minutes=self.RATE_LIMIT_COOLDOWN_MINUTES
        )

        result = await self.db.execute(
            update(AIApiKey)
            .where(
                and_(
                    AIApiKey.user_id == self.user_id,
                    AIApiKey.status == AIKeyStatus.RATE_LIMITED.value,
                    AIApiKey.last_error_at < cooldown_time
                )
            )
            .values(status=AIKeyStatus.ACTIVE.value)
        )
        await self.db.commit()

        count = result.rowcount
        if count > 0:
            logger.info(f"[AI_KEY] Rate limit 키 복구: {count}개")
        return count

    # === CRUD 메서드 ===

    async def create_key(self, data: AIApiKeyCreate) -> AIApiKey:
        """새 API 키 생성"""
        key = AIApiKey(
            user_id=self.user_id,
            provider=data.provider.value,
            label=data.label,
            api_key=data.api_key,
            priority=data.priority,
        )
        self.db.add(key)
        await self.db.commit()
        await self.db.refresh(key)
        logger.info(f"[AI_KEY] 키 생성: id={key.id}, provider={key.provider}, label={key.label}")
        return key

    async def get_key(self, key_id: int) -> Optional[AIApiKey]:
        """특정 키 조회"""
        result = await self.db.execute(
            select(AIApiKey).where(
                and_(
                    AIApiKey.id == key_id,
                    AIApiKey.user_id == self.user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_keys_by_provider(
        self,
        provider: Optional[AIProvider] = None
    ) -> List[AIApiKey]:
        """제공자별 키 목록 조회"""
        query = select(AIApiKey).where(
            AIApiKey.user_id == self.user_id
        ).order_by(AIApiKey.provider, AIApiKey.priority)

        if provider:
            query = query.where(AIApiKey.provider == provider.value)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_keys(self) -> List[AIApiKey]:
        """모든 키 목록 조회"""
        return await self.get_keys_by_provider()

    async def update_key(
        self,
        key_id: int,
        data: AIApiKeyUpdate
    ) -> Optional[AIApiKey]:
        """키 정보 수정"""
        key = await self.get_key(key_id)
        if not key:
            return None

        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in update_data.items():
            setattr(key, field, value)

        await self.db.commit()
        await self.db.refresh(key)
        logger.info(f"[AI_KEY] 키 수정: id={key_id}, fields={list(update_data.keys())}")
        return key

    async def delete_key(self, key_id: int) -> bool:
        """키 삭제"""
        key = await self.get_key(key_id)
        if not key:
            return False

        await self.db.delete(key)
        await self.db.commit()
        logger.info(f"[AI_KEY] 키 삭제: id={key_id}, provider={key.provider}")
        return True

    async def update_priorities(
        self,
        data: AIApiKeyPriorityUpdate
    ) -> int:
        """우선순위 일괄 변경"""
        updated_count = 0
        for item in data.priorities:
            result = await self.db.execute(
                update(AIApiKey)
                .where(
                    and_(
                        AIApiKey.id == item['id'],
                        AIApiKey.user_id == self.user_id
                    )
                )
                .values(priority=item['priority'])
            )
            updated_count += result.rowcount

        await self.db.commit()
        logger.info(f"[AI_KEY] 우선순위 변경: {updated_count}개")
        return updated_count

    async def get_key_stats(self) -> Dict:
        """키 통계 조회"""
        keys = await self.get_all_keys()

        stats = {
            "total": len(keys),
            "by_provider": {},
            "by_status": {},
            "active_count": 0,
        }

        for key in keys:
            # 제공자별 집계
            if key.provider not in stats["by_provider"]:
                stats["by_provider"][key.provider] = 0
            stats["by_provider"][key.provider] += 1

            # 상태별 집계
            if key.status not in stats["by_status"]:
                stats["by_status"][key.status] = 0
            stats["by_status"][key.status] += 1

            # 활성 키 수
            if key.is_available:
                stats["active_count"] += 1

        return stats
