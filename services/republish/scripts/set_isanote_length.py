"""이사노트 모듈의 본문 분량 기준을 올린다.

기본값(1,800자)이 쓰이고 있어 모델에게 가는 목표가 2,500자였다.
수작업 글 26편 평균이 4,003자라 목표를 그 선에 맞춘다.

    python3 scripts/set_isanote_length.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.core.database import db_manager  # noqa: E402
from app.models.module import Module  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MODULE_NAME = "이사노트_구글 블로거"
MIN_CHARS = 3000
MIN_SECTIONS = 6


async def main() -> None:
    """분량 기준을 넣는다. 다른 설정은 건드리지 않는다."""
    await db_manager.initialize()
    async with db_manager.get_session() as db:
        module = (await db.execute(
            select(Module).where(Module.name == MODULE_NAME)
        )).scalar_one_or_none()
        if module is None:
            logger.error("모듈을 찾을 수 없습니다: %s", MODULE_NAME)
            return

        settings = dict(module.settings or {})
        gate = dict(settings.get("quality_gate") or {})
        gate["enabled"] = True
        gate["min_chars"] = MIN_CHARS
        gate["min_sections"] = MIN_SECTIONS
        settings["quality_gate"] = gate
        module.settings = settings
        flag_modified(module, "settings")
        await db.commit()

        target = round(MIN_CHARS * 1.4 / 100) * 100
        logger.info("설정 완료 | id=%s | 최소 %s자 → 목표 %s자 · 소제목 %s개",
                    module.id, f"{MIN_CHARS:,}", f"{target:,}", MIN_SECTIONS)


if __name__ == "__main__":
    asyncio.run(main())
