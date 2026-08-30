"""승인 확인 시 모듈 프롬프트를 실제로 교체한다 (S2, 2026-08-30).

런타임 해석만으로도 생성은 올바르게 동작하지만, 그러면 **모듈 화면에는 승인용
프롬프트가 보이는데 실제로는 다른 것이 쓰인다.** 이 사안의 출발점이 바로 그
"보이는 것과 쓰이는 것이 다른" 혼란이었으므로, DB 값도 함께 맞춘다.

호출 지점(승인 상태가 바뀌는 곳)
    - 수동 변경: routers/blog_settings_adsense.py
    - API 동기화: services/publishing/adsense_account_service.py

제약: 모듈이 블로그를 2개 이상 담당하면 교체하지 않는다. 블로그마다 승인 상태가
달라 모듈 값을 통째로 바꾸는 것이 성립하지 않기 때문이다(런타임 해석에 맡긴다).
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ...core.logger import get_logger
from ...models.module import Module
from . import adsense_prompt_switch as switch

logger = get_logger("adsense_prompt_sync", "app.log")


async def _modules_for_blog(db: AsyncSession, blog_id: int) -> List[Module]:
    """이 블로그를 담당하는 프롬프트 모듈들.

    settings.blogs 는 JSON 이라 SQL 로 정확히 거르기 번거롭다. 프롬프트 계열
    모듈만 가져와 파이썬에서 판정한다(모듈 수가 수십 개 수준이라 부담 없다).
    """
    from ...models.module_type import ModuleType

    stmt = (
        select(Module)
        .join(ModuleType, ModuleType.id == Module.module_type_id)
        .where(ModuleType.code.like("%prompt%"))
    )
    modules = list((await db.execute(stmt)).scalars().all())
    return [
        m for m in modules
        if blog_id in switch.module_blog_ids(m.settings or {})
    ]


async def sync_for_blog(db: AsyncSession, blog: Any) -> Dict[str, Any]:
    """블로그 승인 상태에 맞춰 모듈 프롬프트를 정리한다.

    Returns:
        {"switched": [모듈명], "blocked": [모듈명], "skipped_multi": [모듈명]}
    """
    result: Dict[str, List[str]] = {
        "switched": [], "blocked": [], "skipped_multi": [],
    }
    if not switch.is_approved(blog):
        return result

    blog_id = getattr(blog, "id", None)
    if blog_id is None:
        return result

    for module in await _modules_for_blog(db, blog_id):
        settings = module.settings or {}
        if not switch.uses_approval_prompt(settings):
            continue

        if not switch.replacement_prompt(settings):
            result["blocked"].append(module.name)
            logger.warning(
                "[PROMPT_SYNC] 승인 후 프롬프트 미지정 → 생성 정지 예정 | "
                "blog=%s | module=%s",
                getattr(blog, "name", "?"), module.name,
            )
            continue

        if not switch.can_persist_switch(settings, blog):
            result["skipped_multi"].append(module.name)
            logger.info(
                "[PROMPT_SYNC] 블로그 여러 개 담당 → DB 교체 생략(런타임 해석) | "
                "module=%s",
                module.name,
            )
            continue

        module.settings = switch.switched_settings(settings)
        flag_modified(module, "settings")
        result["switched"].append(module.name)
        logger.info(
            "[PROMPT_SYNC] 승인 후 프롬프트로 교체 | blog=%s | module=%s",
            getattr(blog, "name", "?"), module.name,
        )

    return result
