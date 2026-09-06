"""외부 자료원 등록 API — 1차 출처를 화면에서 관리한다.

새 API 를 붙일 때 코드를 고치지 않게 하려고 만든 표(external_sources)를
사람이 채울 수 있게 한다. 프리셋을 고르면 주소·응답 경로가 채워지고,
사용자는 인증키만 넣는다.

**연결 테스트가 핵심이다.** 키가 틀렸는지, 활용신청이 안 됐는지, 응답
구조가 다른지는 실제로 불러 봐야 안다. 등록만 해 두고 글 생성 때 조용히
실패하면 아무도 모른다.

순서도: docs/flowcharts/reference_accuracy.md
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.external_source import ADAPTERS, ExternalSource
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.reference.sources import presets

router = APIRouter(prefix="/external-sources", tags=["external-sources"])
logger = get_logger("external_sources_api", "app.log")

MASK = "****"


class SourceRequest(BaseModel):
    """등록·수정 요청. 프리셋을 고르면 대부분이 자동으로 찬다."""

    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    # 프리셋을 고르면 adapter·endpoint·options 는 서버가 채운다.
    # 화면에서 items_path·field_map 같은 값을 손으로 적게 하면 아무도 못 쓴다.
    preset: str = ""
    adapter: str = ""
    endpoint: str = ""
    auth_key: str = ""                       # 빈 값이면 기존 키를 유지
    options: Dict[str, Any] = Field(default_factory=dict)
    match_topics: List[str] = Field(default_factory=list)
    match_keywords: List[str] = Field(default_factory=list)
    enabled: bool = True
    daily_limit: int = Field(1000, ge=1, le=1000000)
    note: str = ""


class TestRequest(BaseModel):
    """연결 테스트. 등록 전에도 눌러 볼 수 있어야 한다."""

    source_id: Optional[int] = None
    query: str = Field("주택담보대출", min_length=1)
    # 미등록 상태에서 테스트할 때 쓰는 값
    adapter: str = ""
    endpoint: str = ""
    auth_key: str = ""
    options: Dict[str, Any] = Field(default_factory=dict)
    preset: str = ""
    # 화면이 등록 폼 값을 그대로 보내므로 남는 필드를 허용한다
    code: str = ""
    name: str = ""
    match_topics: List[str] = Field(default_factory=list)
    match_keywords: List[str] = Field(default_factory=list)
    enabled: bool = True
    daily_limit: int = 1000
    note: str = ""


@router.get("/presets")
async def list_presets(
    current_user: User = Depends(get_current_user),
) -> dict:
    """고를 수 있는 프리셋과 어댑터 목록."""
    return {"presets": presets.listing(), "adapters": list(ADAPTERS)}


@router.get("")
async def list_sources(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """등록된 소스. **인증키는 마스킹해서** 내보낸다."""
    rows = (await db.execute(
        select(ExternalSource).order_by(ExternalSource.id)
    )).scalars().all()
    return {"sources": [_serialize(row) for row in rows]}


@router.post("")
async def create_source(
    request: SourceRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """새 소스 등록."""
    exists = (await db.execute(
        select(ExternalSource).where(ExternalSource.code == request.code)
    )).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 있는 코드입니다")

    _resolve_preset(request)
    if request.adapter not in ADAPTERS:
        raise HTTPException(status_code=422,
                            detail=f"모르는 어댑터: {request.adapter}")
    if not request.endpoint or len(request.endpoint) < 8:
        raise HTTPException(status_code=422, detail="주소를 입력하세요")
    if not request.match_topics and not request.match_keywords:
        # 조건이 없으면 영영 안 불린다. 등록해 놓고 왜 안 되는지 묻게 된다.
        raise HTTPException(
            status_code=422,
            detail="주제 또는 제목 낱말 중 하나는 지정해야 합니다")

    row = ExternalSource(code=request.code)
    _apply(row, request)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("[EXT_SOURCE] 등록 | %s | adapter=%s", row.code, row.adapter)
    return {"success": True, "source": _serialize(row)}


@router.put("/{source_id}")
async def update_source(
    source_id: int,
    request: SourceRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """수정. 인증키를 비워 보내면 기존 키를 유지한다."""
    row = await db.get(ExternalSource, source_id)
    if not row:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")
    _resolve_preset(request)
    if request.adapter not in ADAPTERS:
        raise HTTPException(status_code=422,
                            detail=f"모르는 어댑터: {request.adapter}")
    _apply(row, request)
    await db.commit()
    await db.refresh(row)
    logger.info("[EXT_SOURCE] 수정 | %s", row.code)
    return {"success": True, "source": _serialize(row)}


@router.delete("/{source_id}")
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """삭제. 인증키도 함께 사라진다."""
    row = await db.get(ExternalSource, source_id)
    if not row:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")
    code = row.code
    await db.delete(row)
    await db.commit()
    logger.info("[EXT_SOURCE] 삭제 | %s", code)
    return {"success": True}


@router.post("/test")
async def test_source(
    request: TestRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """실제로 한 번 불러 본다.

    등록만 해 두고 글 생성 때 조용히 실패하면 아무도 모른다. 여기서
    키·주소·응답 구조를 한 번에 확인한다.
    """
    from ..core.encryption import encrypt_api_key
    from ..services.reference.query_builder import build as build_plan
    from ..services.reference.sources.registry import _adapter

    if request.source_id:
        row = await db.get(ExternalSource, request.source_id)
        if not row:
            raise HTTPException(status_code=404,
                                detail="소스를 찾을 수 없습니다")
    else:
        if not request.auth_key.strip():
            raise HTTPException(status_code=422, detail="인증키를 입력하세요")
        adapter_code, endpoint, options = request.adapter, request.endpoint, \
            (request.options or {})
        if request.preset:
            found = presets.get(request.preset)
            if not found:
                raise HTTPException(status_code=422, detail="모르는 프리셋")
            adapter_code = found["adapter"]
            endpoint = found["endpoint"]
            options = found.get("options") or {}
        row = ExternalSource(
            code="_test", name="테스트", adapter=adapter_code,
            endpoint=endpoint,
            auth_key_encrypted=encrypt_api_key(request.auth_key.strip()),
            options=options)

    # 질의는 먼저 만든다. 오류로 빠져나가는 길에서도 화면이 무엇을 물었는지
    # 보여줘야 한다 — 예전에는 오류 응답에 query 가 없어 "undefined" 가 떴다.
    plan = build_plan(request.query)
    base = {"query": plan.primary, "entities": plan.entities, "count": 0,
            "preview": ""}

    if not (row.adapter or "").strip():
        return {**base, "ok": False,
                "error": "어댑터를 고르지 않았습니다. 프리셋을 선택하거나 "
                         "어댑터를 직접 지정하세요."}
    adapter = _adapter(row.adapter)
    if adapter is None:
        return {**base, "ok": False,
                "error": f"모르는 어댑터: {row.adapter}"}
    if not (row.endpoint or "").strip():
        return {**base, "ok": False, "error": "주소가 비어 있습니다"}

    try:
        result = await adapter.fetch(row, plan.primary, plan.entities)
    except Exception as e:  # noqa: BLE001
        return {**base, "ok": False, "error": f"호출 실패: {e}"}

    return {
        **base,
        "ok": result.ok,
        "error": result.error,
        "count": len(result.facts),
        # 실제로 무엇이 왔는지 보여 준다. 건수만으로는 맞는지 알 수 없다.
        "preview": "\n".join(result.to_prompt().splitlines()[:14]),
    }


def _resolve_preset(request: SourceRequest) -> None:
    """프리셋을 골랐으면 주소·어댑터·옵션을 채운다.

    화면은 인증키와 매칭 조건만 받는다. 나머지를 사용자가 적게 하면
    오타 하나로 조용히 실패하는 소스가 생긴다.
    """
    if not request.preset:
        return
    found = presets.get(request.preset)
    if not found:
        raise HTTPException(status_code=422,
                            detail=f"모르는 프리셋: {request.preset}")
    request.adapter = found["adapter"]
    request.endpoint = found["endpoint"]
    request.options = found.get("options") or {}
    if not request.match_topics:
        request.match_topics = list(found.get("match_topics") or [])
    if not request.match_keywords:
        request.match_keywords = list(found.get("match_keywords") or [])


def _apply(row: ExternalSource, request: SourceRequest) -> None:
    """요청을 행에 반영. 인증키는 값이 있을 때만 덮어쓴다."""
    from ..core.encryption import encrypt_api_key

    row.name = request.name
    row.adapter = request.adapter
    row.endpoint = request.endpoint
    row.options = request.options or {}
    row.match_topics = [t.strip() for t in request.match_topics if t.strip()]
    row.match_keywords = [k.strip() for k in request.match_keywords
                          if k.strip()]
    row.enabled = request.enabled
    row.daily_limit = request.daily_limit
    row.note = request.note or ""

    key = (request.auth_key or "").strip()
    if key and MASK not in key:
        row.auth_key_encrypted = encrypt_api_key(key)


def _serialize(row: ExternalSource) -> dict:
    """화면용. 인증키는 등록 여부만 알려 준다."""
    return {
        "id": row.id, "code": row.code, "name": row.name,
        "adapter": row.adapter, "endpoint": row.endpoint,
        "has_key": bool(row.auth_key_encrypted),
        "options": row.options or {},
        "match_topics": row.match_topics or [],
        "match_keywords": row.match_keywords or [],
        "enabled": bool(row.enabled), "daily_limit": row.daily_limit,
        "note": row.note or "",
    }
