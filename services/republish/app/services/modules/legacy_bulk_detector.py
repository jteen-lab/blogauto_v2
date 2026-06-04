"""
레거시 대량 수집 옵션 감지 서비스 (Phase E).

기존 ``collect`` 모듈은 ``Module.settings`` JSONB 안에 ``enable_bulk_collect``
플래그를 두고 대량 수집을 옵션으로 제공해 왔다. Phase A~D 작업으로
대량 수집은 별도의 ``bulk_collect`` 모듈 타입으로 분리되었지만, 운영 중인
사용자가 직접 마이그레이션해야 하는 정책(옵션 C)을 채택했기 때문에
기존 데이터에는 ``enable_bulk_collect = True`` 가 남아 있을 수 있다.

본 서비스는 다음 두 가지 작업을 담당한다.

1. 사용자가 보유한 모듈 중 "레거시 대량 수집 옵션이 켜져 있는"
   ``collect`` 모듈을 일괄 조회한다(목록 페이지 배지 표시용).
2. 단일 모듈에 대해 동일한 상태인지 빠르게 확인한다(상세 API용).

성능 고려사항:
    모듈 목록 API 에서 N+1 을 회피하기 위해 라우터/서비스는 SELECT 결과에
    이미 포함된 ``settings`` JSONB 를 그대로 활용하는 것을 권장한다.
    본 검출기의 ``detect`` 메서드는 그 자체로도 단일 쿼리만 실행한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.module import Module
from ...models.module_type import ModuleType

logger = get_logger("legacy_bulk_detector", "app.log")


class LegacyBulkDetector:
    """레거시 ``collect`` 모듈의 대량 수집 옵션을 감지한다.

    Attributes:
        TARGET_TYPE_CODE: 감지 대상 모듈 타입 코드 (``collect`` 고정).
        WARNING_TYPE: 응답 페이로드에 채워질 경고 식별자.
    """

    TARGET_TYPE_CODE: str = "collect"
    WARNING_TYPE: str = "legacy_bulk"

    @staticmethod
    def _is_legacy_bulk_settings(settings: Optional[Dict[str, Any]]) -> bool:
        """settings JSONB 에 레거시 대량 수집 플래그가 켜져 있는지 판정한다.

        Args:
            settings: ``Module.settings`` JSONB 값. None / 빈 dict 도 허용.

        Returns:
            ``enable_bulk_collect`` 가 truthy 이면 True, 그 외엔 False.
        """
        if not settings or not isinstance(settings, dict):
            return False
        return bool(settings.get("enable_bulk_collect"))

    async def detect(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """사용자의 모든 모듈 중 레거시 대량 수집 옵션이 켜진 항목을 반환한다.

        대량 수집은 별도 모듈로 분리되었으므로, 본 메서드가 빈 리스트가 아닌
        결과를 돌려준다는 것은 사용자에게 마이그레이션 안내가 필요하다는
        의미다.

        Args:
            db: 비동기 DB 세션.
            user_id: 검사 대상 사용자 ID.

        Returns:
            ``[{"module_id": int, "module_name": str,
                "warning_type": "legacy_bulk"}, ...]`` 형식의 목록.
            해당 사항이 없으면 빈 리스트.
        """
        try:
            stmt = (
                select(Module.id, Module.name, Module.settings)
                .join(ModuleType, Module.module_type_id == ModuleType.id)
                .where(
                    ModuleType.code == self.TARGET_TYPE_CODE,
                    Module.user_id == user_id,
                )
            )
            result = await db.execute(stmt)
            rows = result.all()

            legacy: List[Dict[str, Any]] = []
            for module_id, module_name, settings in rows:
                if self._is_legacy_bulk_settings(settings):
                    legacy.append(
                        {
                            "module_id": module_id,
                            "module_name": module_name,
                            "warning_type": self.WARNING_TYPE,
                        }
                    )

            logger.info(
                "[LEGACY_BULK_DETECT] user_id=%s, scanned=%s, legacy=%s",
                user_id,
                len(rows),
                len(legacy),
            )
            return legacy
        except Exception as e:  # pragma: no cover - 예외 케이스 보호 로깅
            logger.error(
                "[LEGACY_BULK_DETECT] 감지 실패 user_id=%s error=%s",
                user_id,
                e,
            )
            # 검출 실패 시 빈 리스트 반환 — 모듈 목록 응답 자체는 살린다.
            return []

    async def has_legacy_bulk(
        self,
        db: AsyncSession,
        module_id: int,
    ) -> bool:
        """단일 모듈이 레거시 대량 수집 상태인지 즉시 확인한다.

        모듈 상세 API 등 단건 응답에 ``legacy_bulk_warning`` 플래그를
        채울 때 사용한다. 비효율을 막기 위해 ``Module.settings`` 컬럼만
        조회한다.

        Args:
            db: 비동기 DB 세션.
            module_id: 검사 대상 모듈 ID.

        Returns:
            대상 모듈이 ``collect`` 타입이며 ``enable_bulk_collect`` 가
            True 이면 True, 그 외 (모듈 없음 / 다른 타입 / 옵션 꺼짐) False.
        """
        try:
            stmt = (
                select(Module.settings, ModuleType.code)
                .join(ModuleType, Module.module_type_id == ModuleType.id)
                .where(Module.id == module_id)
            )
            result = await db.execute(stmt)
            row = result.first()
            if not row:
                return False
            settings, type_code = row
            if type_code != self.TARGET_TYPE_CODE:
                return False
            return self._is_legacy_bulk_settings(settings)
        except Exception as e:  # pragma: no cover
            logger.error(
                "[LEGACY_BULK_DETECT] 단건 검사 실패 module_id=%s error=%s",
                module_id,
                e,
            )
            return False
