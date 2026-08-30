"""AI 모델 카탈로그 API — 화면이 하드코딩 대신 이 목록을 받아 쓴다.

계획서: docs/plans/ai_model_catalog_sync.md
순서도: docs/flowcharts/ai_model_catalog.md
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.ai_model import AIModel, AIModelPrice
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.ai.model_prices import estimate_per_post

logger = get_logger("ai_models", "app.log")

router = APIRouter(prefix="/api/v1/ai-models", tags=["AI 모델 카탈로그"])


@router.get("")
async def list_models(
    provider: Optional[str] = Query(default=None),
    capability: Optional[str] = Query(default="text"),
    include_unavailable: bool = Query(default=False),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    """모델 목록 + 요금 + 추천 배지.

    기본은 사용 가능한 글 생성용만 준다. `include_unavailable=true` 를 주면
    사라진 모델도 함께 오는데, 저장된 설정이 이미 사라진 모델을 가리킬 때
    화면에서 '지원 종료' 로 보여주기 위한 것이다.
    """
    q = select(AIModel)
    if provider:
        q = q.where(AIModel.provider == provider)
    if capability:
        q = q.where(AIModel.capability == capability)
    if not include_unavailable:
        q = q.where(AIModel.is_available == True)  # noqa: E712
    q = q.order_by(AIModel.provider, AIModel.model_id)

    rows = (await db.execute(q)).scalars().all()

    prices = {
        (p.provider, p.model_id): p
        for p in (await db.execute(select(AIModelPrice))).scalars().all()
    }

    items = []
    for m in rows:
        price = prices.get((m.provider, m.model_id))
        items.append({
            "provider": m.provider,
            "model_id": m.model_id,
            "display_name": m.display_name or m.model_id,
            "capability": m.capability,
            "is_available": m.is_available,
            "shutdown_date": m.shutdown_date,
            "tier": m.tier,
            "price": None if not price else {
                "input_per_1m": price.input_per_1m,
                "output_per_1m": price.output_per_1m,
                "cached_input_per_1m": price.cached_input_per_1m,
                "currency": price.currency,
                "note": price.note,
                "per_post_estimate": round(
                    estimate_per_post(price.input_per_1m, price.output_per_1m), 4
                ),
                "updated_at": price.updated_at.isoformat()
                if price.updated_at else None,
            },
        })

    last_sync = max(
        (m.synced_at for m in rows if m.synced_at), default=None,
    )
    return {
        "items": items,
        "total": len(items),
        "last_synced_at": last_sync.isoformat() if last_sync else None,
    }


@router.post("/sync")
async def sync_models(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """지금 갱신 — 제공자 목록을 받아 카탈로그에 반영한다.

    한 제공자가 실패해도 나머지는 진행한다. 키가 없는 제공자는 건너뛴다.
    """
    from ..services.ai.model_catalog import ModelCatalogService

    out = await ModelCatalogService(db, current_user.id).sync_all()

    from ..services.blog_service import add_action_log

    t = out["total"]
    await add_action_log(
        db, "SUCCESS",
        f"AI 모델 목록 갱신: 신규 {t['added']} / 사라짐 {t['gone']} / "
        f"유지 {t['kept']}",
        category="ai_models",
    )
    return out


@router.get("/warnings")
async def model_warnings(
    blog_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    """쓰고 있는 모델이 사라졌거나 종료 예정인지 알려준다.

    자동으로 바꾸지 않고 알리기만 한다 — 모델이 바뀌면 글 품질과 요금이
    달라지므로 대체 선택은 사람이 해야 한다.
    """
    from ..services.ai.model_warnings import collect_warnings, message_for

    items = await collect_warnings(db, blog_id)
    return {
        "items": [{**it, "message": message_for(it)} for it in items],
        "total": len(items),
    }
