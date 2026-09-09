"""CPA 오퍼의 자산 — 이미지와 니치.

오퍼 본체(등록·규칙·검증)와 나눈다. 한 파일이 500줄을 넘으면 어디를 고쳐야
할지 찾기 어렵고, 이미 그 규칙에 걸렸다.

순서도: docs/flowcharts/cpa_offer.md
"""
from typing import List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..routers.cpa import _get

router = APIRouter(prefix="/cpa", tags=["cpa"])
logger = get_logger("cpa_assets", "app.log")


ALLOWED_IMAGE = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@router.post("/offers/{offer_id}/images")
async def upload_image(
    offer_id: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """오퍼 이미지를 올린다.

    심의 배너 외 이미지를 쓰면 위반인 오퍼가 있다. 쓸 수 있는 것만 여기
    등록해 두고, 글 생성은 이 목록에서만 고른다.
    """
    import shutil
    from pathlib import Path as _Path

    offer = await _get(db, offer_id)
    ext = _Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(
            status_code=400,
            detail=f"이미지만 올릴 수 있습니다 ({', '.join(ALLOWED_IMAGE)})")

    from ..services.blog_settings_service import MEDIA_ROOT

    folder = MEDIA_ROOT / "cpa" / str(offer_id)
    folder.mkdir(parents=True, exist_ok=True)
    seq = len(offer.images or []) + 1
    saved = folder / f"img_{seq}{ext}"
    try:
        with saved.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:  # noqa: BLE001
        logger.error("[CPA] 이미지 저장 실패 | %s", e)
        raise HTTPException(status_code=500, detail="이미지 저장에 실패했습니다")

    if saved.stat().st_size > MAX_IMAGE_BYTES:
        saved.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="8MB 를 넘습니다")

    offer.images = list(offer.images or []) + [{
        "path": str(saved.relative_to(MEDIA_ROOT)),
        "name": file.filename or saved.name,
        "note": (note or "")[:200],
    }]
    await db.commit()
    await db.refresh(offer)
    logger.info("[CPA] 이미지 등록 | %s | %s", offer.name, saved.name)
    return {"success": True, "images": offer.images}


@router.get("/offers/{offer_id}/images/{index}/file")
async def get_image(
    offer_id: int,
    index: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """등록한 이미지를 내려준다.

    /media 를 정적으로 열지 않는다 — 남의 파일까지 노출된다.
    등록된 목록에 있는 것만 준다.
    """
    from fastapi.responses import FileResponse

    from ..services.blog_settings_service import MEDIA_ROOT

    offer = await _get(db, offer_id)
    images = offer.images or []
    if not 0 <= index < len(images):
        raise HTTPException(status_code=404, detail="그 이미지가 없습니다")

    path = (MEDIA_ROOT / images[index].get("path", "")).resolve()
    # 경로 조작 방어 — 목록에 있어도 밖을 가리키면 거절한다
    if not str(path).startswith(str(MEDIA_ROOT.resolve())) or not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(path)


@router.delete("/offers/{offer_id}/images/{index}")
async def delete_image(
    offer_id: int,
    index: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """등록한 이미지를 뺀다. 파일도 함께 지운다."""
    from ..services.blog_settings_service import MEDIA_ROOT

    offer = await _get(db, offer_id)
    images = list(offer.images or [])
    if not 0 <= index < len(images):
        raise HTTPException(status_code=404, detail="그 이미지가 없습니다")
    gone = images.pop(index)
    try:
        (MEDIA_ROOT / gone.get("path", "")).unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001 — 파일이 없어도 목록에서는 뺀다
        logger.warning("[CPA] 이미지 파일 삭제 실패 | %s", e)
    offer.images = images
    await db.commit()
    return {"success": True, "images": images}


class SubtopicsIn(BaseModel):
    """오퍼가 쓸 하위주제. 소유가 아니라 참조다."""

    subtopic_ids: List[int] = []
    new_name: Optional[str] = None
    new_topic_id: Optional[int] = None


@router.post("/offers/{offer_id}/subtopics")
async def set_subtopics(
    offer_id: int,
    payload: SubtopicsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """오퍼가 쓸 하위주제를 정한다.

    **소유하지 않는다.** 애드센스 블로그도 같은 하위주제를 계속 쓴다.
    주제 단위로 잡으면 그 니치를 쓰던 블로그가 통째로 넘어간다
    (실측: '생활 정보' 제목 879건·블로그 7개).

    `new_name` 을 주면 그 이름으로 하위주제를 만들어 함께 붙인다.
    자동 생성은 하지 않는다 — 카테고리 트리가 지저분해진다.
    """
    from ..models.category import SubTopic, Topic

    offer = await _get(db, offer_id)
    picked = [int(x) for x in (payload.subtopic_ids or [])]

    if (payload.new_name or "").strip():
        if not payload.new_topic_id:
            raise HTTPException(
                status_code=400, detail="새 하위주제를 만들 주제를 고르세요")
        topic = await db.get(Topic, payload.new_topic_id)
        if not topic:
            raise HTTPException(status_code=404, detail="주제를 찾을 수 없습니다")
        made = SubTopic(topic_id=topic.id, name=payload.new_name.strip(),
                        description=f"CPA 오퍼: {offer.name}")
        db.add(made)
        await db.flush()
        picked.append(made.id)

    # 실재하는 것만 남긴다 — 지워진 하위주제를 참조하면 제목이 안 뽑힌다
    alive = {row for row in (await db.execute(
        select(SubTopic.id).where(SubTopic.id.in_(picked or [0]))
    )).scalars().all()} if picked else set()

    offer.subtopic_ids = sorted(alive)
    await db.commit()
    await db.refresh(offer)
    logger.info("[CPA] 하위주제 참조 | %s | %s", offer.name, offer.subtopic_ids)
    return {"success": True, "subtopic_ids": offer.subtopic_ids}


class PageReq(BaseModel):
    """상담 페이지 미리보기."""

    intro: str = ""
    post_id: Optional[int] = None
    blog_id: Optional[int] = None


@router.post("/offers/{offer_id}/consult-page")
async def consult_page(
    offer_id: int,
    payload: PageReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """상담 페이지 HTML 을 만든다.

    얇으면 `thin=true` 로 알린다. 얇은 중개 페이지는 검색엔진이 걸러내고,
    나중에 유료 광고를 붙일 때 승인되지 않는다.
    """
    from ..services.cpa.consult_page import build
    from ..services.cpa.subid import apply

    offer = await _get(db, offer_id)
    url = apply(offer.landing_url or "", offer,
                payload.post_id, payload.blog_id)
    found = build(offer, url, payload.intro)
    return {**found, "landing_url": url}
