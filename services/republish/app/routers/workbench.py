"""모듈 테스터 — 모듈을 담아 돌려본 뒤, 반영할지 버릴지 정하는 화면.

계획서: docs/plans/test_workbench_plan.md
순서도: docs/flowcharts/test_workbench.md
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.module import Module
from ..models.module_type import ModuleType
from ..models.user import User
from ..models.user_settings import UserSettings
from ..routers.auth import get_current_user
from ..services.promo import link_service
from ..services.workbench import apply as apply_svc
from ..services.workbench import presets as preset_svc
from ..services.workbench import sources as source_svc
from ..services.workbench.runner import EXCLUDED, SUPPORTED, WorkbenchRunner

logger = get_logger("workbench_router", "app.log")

router = APIRouter(prefix="/api/v1/workbench", tags=["모듈 테스터"])
page_router = APIRouter(tags=["페이지"])
templates = Jinja2Templates(directory="app/templates")

# 발행 HTML 에 px 를 붙이는 속성 — style-tab-css-utils.js 와 같게 맞춘다
_PX_PROPS = {
    "font-size", "border-width", "border-radius",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border-top-width", "border-right-width",
    "border-bottom-width", "border-left-width",
}


class RunRequest(BaseModel):
    module_type: str = Field(..., description="keyword|title_gen|generate|data")
    module_id: int
    blog_id: Optional[int] = None
    settings_override: Optional[Dict[str, Any]] = None
    title_texts: Optional[List[str]] = None
    chain_keywords: Optional[List[str]] = None
    questions: Optional[List[Dict[str, Any]]] = Field(
        None, description="제목과 같은 순서의 질문 본문")


class QuestionBodyRequest(BaseModel):
    """고른 질문의 본문을 가져온다."""

    links: List[str] = Field(..., description="질문 페이지 주소 (최대 5건)")


class ApplyKeywordsRequest(BaseModel):
    keywords: List[str]
    blog_id: Optional[int] = None


class ApplyTitlesRequest(BaseModel):
    titles: List[str]


class ApplyPostRequest(BaseModel):
    blog_id: int
    title: str
    html: str
    image_url: Optional[str] = None
    module_id: Optional[int] = None
    mode: str = Field("save", description="save=발행대기글 | now=즉시 발행")
    link_id: Optional[Any] = Field(
        None, description='붙인 홍보 링크. "auto" 면 제목의 키워드로 고른다')


class AssembleRequest(BaseModel):
    """미리보기용 조립 요청."""

    html: str
    title: str = ""
    image_url: Optional[str] = None
    link_id: Optional[Any] = None
    blog_id: Optional[int] = None


class PresetSaveRequest(BaseModel):
    name: str
    config: Dict[str, Any]


@page_router.get("/module-tester")
async def module_tester_page(request: Request):
    """모듈 테스터 화면."""
    return templates.TemplateResponse(
        "workbench/index.html", {"request": request})


@page_router.get("/workbench", include_in_schema=False)
async def workbench_redirect():
    """옛 주소 — 즐겨찾기·링크를 살린다."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/module-tester", status_code=307)


#: 화면에 보일 모듈 타입 이름
TYPE_LABELS = {
    "keyword": "키워드",
    "title_gen": "제목 생성/수집",
    "data": "제목 이관",
    "generate": "글 생성",
    "prompt": "글 생성",
    "contact_form": "문의폼",
    "growth_profile": "성장 프로파일",
}


def _unsupported_reason(code: str) -> str:
    """담을 수 없는 이유. 담기 버튼 옆에 그대로 보여준다."""
    if code in EXCLUDED:
        return "되돌릴 수 없어 지원하지 않습니다"
    if code not in SUPPORTED:
        return "테스터에서 돌릴 수 없는 종류입니다"
    return ""


@router.get("/catalog", summary="담을 수 있는 모듈·블로그 목록")
async def catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """담기 시트가 보여줄 재료 — 타입별 모듈과 블로그."""
    rows = (await db.execute(
        select(Module, ModuleType.code)
        .join(ModuleType, Module.module_type_id == ModuleType.id)
        .where(Module.user_id == current_user.id)
        .order_by(ModuleType.code, Module.name))).all()

    # 타입별 묶음(옛 화면 호환)과 전체 목록을 함께 준다. 전체 목록이
    # 있어야 타입 하나가 빠져도 모듈이 화면에서 사라지지 않는다.
    modules: Dict[str, list] = {}
    all_modules: List[dict] = []
    for module, code in rows:
        item = {"id": module.id, "name": module.name, "type": code,
                "type_label": TYPE_LABELS.get(code, code),
                "description": (module.description or "")[:120],
                "supported": code in SUPPORTED,
                "reason": _unsupported_reason(code)}
        all_modules.append(item)
        if code in SUPPORTED:
            modules.setdefault(code, []).append(
                {"id": module.id, "name": module.name})

    blogs = (await db.execute(
        select(Blog).where(Blog.user_id == current_user.id,
                           Blog.is_deleted == False)  # noqa: E712
        .order_by(Blog.name))).scalars().all()
    return {
        "modules": modules,
        "all_modules": all_modules,
        "blogs": [{"id": b.id, "name": b.name,
                   "platform": getattr(b, "platform", "")} for b in blogs],
        "excluded": list(EXCLUDED),
    }


@router.post("/run", summary="리허설 실행 — 반영 전에는 아무것도 남지 않음")
async def run_module(
    body: RunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """모듈 하나를 실제 발행 길로 돌리고 전량 결과를 돌려준다."""
    runner = WorkbenchRunner(db, current_user.id)
    outcome = await runner.run(
        body.module_type, body.module_id, body.blog_id,
        settings_override=body.settings_override,
        title_texts=body.title_texts,
        chain_keywords=body.chain_keywords,
        questions=body.questions,
        keep=False)
    return outcome.to_dict()


@router.get("/sources", summary="지식iN·카페 질문 검색")
async def search_sources(
    query: str = Query(..., min_length=1),
    sources: Optional[str] = Query(None, description="쉼표 구분 소스 코드"),
    limit: int = Query(30, ge=1, le=100),
    start: int = Query(1, ge=1, le=1000,
                       description="몇 번째 결과부터 — 더 보기에 쓴다"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )).scalar_one_or_none()
    picked = [s.strip() for s in (sources or "").split(",") if s.strip()]
    return await source_svc.search_questions(
        settings, query, picked or None, limit, start)


@router.post("/question-body", summary="고른 질문의 본문 가져오기")
async def fetch_question_body(
    body: QuestionBodyRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """질문 페이지를 열어 질문 본문과 답변을 뽑는다.

    **고른 것만** 부른다 — 목록을 통째로 긁으면 한 번에 수 MB 를 받고
    차단 위험도 생긴다. 실패해도 오류를 올리지 않는다(제목만으로도
    글은 나온다).
    """
    from ..services.workbench.question_body import fetch_bodies

    rows = await fetch_bodies(body.links)
    got = len([r for r in rows if r.get("question") or r.get("answer")])
    return {"success": True, "items": rows, "fetched": got}


@router.post("/apply/keywords", summary="반영 — 키워드를 풀에 채택")
async def apply_keywords(
    body: ApplyKeywordsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return await apply_svc.apply_keywords(
        db, current_user.id, body.keywords, body.blog_id)


@router.post("/apply/titles", summary="반영 — 제목을 재고에 투입")
async def apply_titles(
    body: ApplyTitlesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return await apply_svc.apply_titles(db, current_user.id, body.titles)


@router.post("/assemble", summary="고지문·표지·버튼을 붙인 완성본")
async def assemble_post(
    body: AssembleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """미리보기가 쓰는 조립. 저장도 같은 결과를 쓴다.

    링크를 고르지 않으면 고지문·버튼이 둘 다 빠진다(정보성 글).
    """
    html, link = await link_service.build_html(
        db, body.html, link_id=body.link_id, image_url=body.image_url,
        title=body.title, blog_id=body.blog_id)
    return {"success": True, "html": html,
            "link_name": link.name if link else ""}


@router.post("/apply/post", summary="반영 — 글을 발행대기글로(선택 시 즉시 발행)")
async def apply_post(
    body: ApplyPostRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    blog = await db.get(Blog, body.blog_id)
    if blog is None or blog.user_id != current_user.id:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")
    return await apply_svc.apply_post(
        db, body.blog_id, body.title, body.html,
        image_url=body.image_url, module_id=body.module_id, mode=body.mode,
        link_id=body.link_id)


def _preview_selectors(selector: str, cfg: dict) -> List[str]:
    """미리보기에 쓸 선택자들.

    버튼 스타일은 `a.button` 으로 저장돼 있는데 글에 붙는 버튼은
    `div.button-link` 안의 링크다. 그대로 두면 미리보기에서만 버튼이
    맨몸으로 보인다 — 같은 스타일을 양쪽에 건다.
    """
    out = [selector]
    if selector == "a.button" and ".button-link" not in cfg:
        out.append(".button-link a")
    elif selector == "a.button:hover" and ".button-link" not in cfg:
        out.append(".button-link a:hover")
    return out


@router.get("/preview-css", summary="블로그 스타일 CSS (미리보기용)")
async def preview_css(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """블로그 style_config 를 미리보기 틀에 주입할 CSS 로 바꾼다."""
    blog = await db.get(Blog, blog_id)
    if blog is None or blog.user_id != current_user.id:
        raise HTTPException(404, "블로그를 찾을 수 없습니다")
    cfg = getattr(blog, "style_config", None) or {}
    lines = []
    for selector, props in cfg.items():
        if not isinstance(props, dict) or not props:
            continue
        decls = "; ".join(
            f"{k}: {v}px" if k in _PX_PROPS else f"{k}: {v}"
            for k, v in props.items())
        for target in _preview_selectors(selector, cfg):
            lines.append(f".wb-preview {target} {{ {decls}; }}")
    return {"css": "\n".join(lines)}


@router.get("/presets", summary="프리셋 목록")
async def list_presets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return {"presets": await preset_svc.list_presets(db)}


@router.post("/presets", summary="프리셋 저장(구성만 — 결과물은 저장 안 됨)")
async def save_preset(
    body: PresetSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return await preset_svc.save_preset(db, body.name, body.config)


@router.delete("/presets/{name}", summary="프리셋 삭제")
async def delete_preset(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    return await preset_svc.delete_preset(db, name)
