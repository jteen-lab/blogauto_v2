"""D 방식 거르기 켜고 끄기 — 시스템 설정 ``title_screen_enabled``(기본 켜짐).

끄면: 정식 이동이 판정(pass)을 요구하지 않고, 수집 회차 뒤 거르기를 돌리지 않는다.
되돌리기 스위치다. 워커마다 설정 캐시가 따로라 DB 를 바로 읽는다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

KEY = "title_screen_enabled"


async def enabled(db: AsyncSession) -> bool:
    """켜져 있나(값이 없으면 켜짐)."""
    from ...models.system_settings import SystemSettings

    try:
        raw = (await db.execute(select(SystemSettings.value).where(
            SystemSettings.key == KEY))).scalar_one_or_none()
    except Exception:  # noqa: BLE001 — 설정 조회 실패로 수집을 막지 않는다
        return True
    return raw is None or str(raw).strip().lower() not in ("0", "false", "off", "no")
