"""쓰고 있는 모델이 사라졌거나 사라질 예정인지 알린다.

자동으로 다른 모델로 바꾸지 않는다. 모델이 바뀌면 글 품질과 요금이 달라진다
— gpt-4o-mini → gpt-4.1-mini 전환에서 같은 프롬프트로 분량이 1,618자에서
3,542자로 달라졌다. 대체 선택은 사람이 해야 한다.

순서도: docs/flowcharts/ai_model_catalog.md
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.ai_model import AIModel
from ...models.blog import Blog

logger = get_logger("model_warnings", "app.log")

SLOTS = (
    ("writing_ai", "글쓰기"),
    ("title_ai", "제목"),
    ("reference_ai", "참고자료"),
    ("image_ai", "이미지"),
)


async def collect_warnings(
    db: AsyncSession, blog_id: int | None = None,
) -> List[Dict[str, Any]]:
    """사라졌거나 종료 예정인 모델을 쓰는 블로그를 찾는다.

    Args:
        db: 세션
        blog_id: 특정 블로그만 볼 때 지정(설정 화면용). 없으면 전체.

    Returns:
        [{blog_id, blog_name, slot, slot_label, provider, model,
          reason, shutdown_date}]
    """
    rows = (await db.execute(select(AIModel))).scalars().all()
    index = {(r.provider, r.model_id): r for r in rows}
    if not index:
        # 카탈로그가 비어 있으면(동기화 전) 판단할 근거가 없다.
        # 여기서 '전부 사라짐' 으로 처리하면 오탐이 쏟아진다.
        return []

    q = select(Blog).where(Blog.is_deleted == False)  # noqa: E712
    if blog_id is not None:
        q = q.where(Blog.id == blog_id)
    blogs = (await db.execute(q)).scalars().all()

    out: List[Dict[str, Any]] = []
    for blog in blogs:
        cfg = blog.ai_config or {}
        for slot, label in SLOTS:
            v = cfg.get(slot) or {}
            provider, model = v.get("provider"), v.get("model")
            if not provider or not model:
                continue
            row = index.get((provider, model))
            if row is None:
                # 카탈로그에 아예 없다. 그 제공자를 한 번도 동기화하지 못했을
                # 수도 있어 단정하지 않는다.
                if not any(p == provider for p, _ in index):
                    continue
                reason, shutdown = "unknown", None
            elif not row.is_available:
                reason, shutdown = "gone", None
            elif row.shutdown_date:
                reason, shutdown = "shutdown_scheduled", row.shutdown_date
            else:
                continue

            out.append({
                "blog_id": blog.id, "blog_name": blog.name,
                "slot": slot, "slot_label": label,
                "provider": provider, "model": model,
                "reason": reason, "shutdown_date": shutdown,
            })
    return out


def message_for(item: Dict[str, Any]) -> str:
    """사용자에게 보여줄 한 줄."""
    base = f"{item['slot_label']} AI 로 쓰는 {item['model']}"
    if item["reason"] == "gone":
        return f"{base} 는 더 이상 제공되지 않습니다. 다른 모델로 바꿔 주세요."
    if item["reason"] == "shutdown_scheduled":
        return f"{base} 는 {item['shutdown_date']} 종료 예정입니다."
    return f"{base} 를 제공자 목록에서 찾을 수 없습니다."


async def warn_unavailable_models(db: AsyncSession) -> int:
    """동기화 후 호출 — 문제가 있으면 로그로 남긴다."""
    items = await collect_warnings(db)
    for it in items:
        logger.warning(
            "[MODEL_WARN] %s | %s", it["blog_name"], message_for(it),
        )
    if items:
        logger.warning("[MODEL_WARN] 확인이 필요한 설정 %d건", len(items))
    return len(items)
