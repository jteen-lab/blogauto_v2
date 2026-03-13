"""
생성 파이프라인 단계별 테스트 API 라우터

각 생성 단계를 독립적으로 실행하여 결과를 확인할 수 있는 API.
실제 DB에 영향을 주지 않는 테스트 모드를 지원합니다.

설계 문서: generation_pipeline_enhancement_plan.md - Phase D - 6.2~6.3
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db_session
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.generation.pipeline_tester import PipelineTester
from ..services.generation.pipeline_full_tester import FullPipelineTester

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/generation/test",
    tags=["Generation Test"],
)


# ============================================================
# Pydantic 요청 모델
# ============================================================

class SelectTitleRequest(BaseModel):
    """제목 선택 테스트 요청"""
    blog_id: int = Field(..., description="블로그 ID")
    module_id: int = Field(..., description="프롬프트 모듈 ID")


class RecombineTitleRequest(BaseModel):
    """제목 재조합 테스트 요청"""
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    blog_id: int = Field(..., description="블로그 ID (AI provider 폴백용)")
    title_id: Optional[int] = Field(None, description="DB 제목 ID")
    title_text: Optional[str] = Field(None, description="직접 입력 제목")
    styles: Optional[list[str]] = Field(
        None, description="UI에서 선택한 제목 스타일 (None이면 DB 설정 사용)",
    )


class CollectReferencesRequest(BaseModel):
    """참조자료 수집 테스트 요청"""
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    search_query: str = Field(..., description="검색어")
    blog_id: Optional[int] = Field(
        None, description="블로그 ID (reference_ai 오버라이드용)",
    )
    # UI에서 직접 전달하는 참조 설정 (None이면 DB 설정 사용)
    ref_settings: Optional[dict] = Field(
        None, description="UI에서 전달된 참조자료 설정 (None이면 DB 설정 사용)",
    )


class GenerateContentRequest(BaseModel):
    """글 생성 테스트 요청"""
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    blog_id: int = Field(..., description="블로그 ID")
    title: str = Field(..., description="생성할 글의 제목")
    reference_text: Optional[str] = Field(
        None, description="참조자료 텍스트",
    )


class AddInternalLinksRequest(BaseModel):
    """내부링크 삽입 테스트 요청"""
    blog_id: int = Field(..., description="블로그 ID")
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    title: str = Field(..., description="현재 글 제목")
    content: str = Field(..., description="마크다운 본문")
    il_settings: Optional[dict] = Field(
        None, description="UI에서 전달된 내부링크 설정 (None이면 DB 설정 사용)",
    )


class GenerateImageRequest(BaseModel):
    """이미지 생성 테스트 요청"""
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    blog_id: int = Field(..., description="블로그 ID")
    title: str = Field(..., description="이미지 제목")
    image_settings: Optional[dict] = Field(
        None,
        description="UI에서 전달된 이미지 생성 설정 (None이면 DB 설정 사용)",
    )


class SubstitutionHtmlRequest(BaseModel):
    """치환 처리 + HTML 변환 테스트 요청"""
    blog_id: int = Field(..., description="블로그 ID")
    content: str = Field(..., description="마크다운 본문")
    text_replace_enabled: bool = Field(True, description="텍스트 치환 활성화")


class FullPipelineRequest(BaseModel):
    """전체 파이프라인 테스트 요청"""
    blog_id: int = Field(..., description="블로그 ID")
    module_id: int = Field(..., description="프롬프트 모듈 ID")
    dry_run: bool = Field(True, description="True면 DB 저장 안 함")


# ============================================================
# API 엔드포인트
# ============================================================

@router.post("/select-title")
async def test_select_title(
    req: SelectTitleRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 1: 제목 선택 테스트

    사용 가능한 제목 후보를 조회하고 랜덤으로 하나를 선택합니다.
    DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_select_title(
        blog_id=req.blog_id, module_id=req.module_id,
    )


@router.post("/recombine-title")
async def test_recombine_title(
    req: RecombineTitleRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 2: 제목 재조합 테스트

    AI를 사용하여 제목을 재조합합니다.
    DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_recombine_title(
        module_id=req.module_id,
        blog_id=req.blog_id,
        title_id=req.title_id,
        title_text=req.title_text,
        styles=req.styles,
    )


@router.post("/collect-references")
async def test_collect_references(
    req: CollectReferencesRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 3: 참조자료 수집 테스트

    검색어로 참조자료를 수집하고 요약합니다.
    DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_collect_references(
        module_id=req.module_id,
        search_query=req.search_query,
        ref_settings=req.ref_settings,
        blog_id=req.blog_id,
    )


@router.post("/generate-content")
async def test_generate_content(
    req: GenerateContentRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 4: 글 생성 테스트

    AI로 글을 생성합니다 (마크다운 반환).
    DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_generate_content(
        module_id=req.module_id,
        blog_id=req.blog_id,
        title=req.title,
        reference_text=req.reference_text,
    )


@router.post("/add-internal-links")
async def test_add_internal_links(
    req: AddInternalLinksRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 5: 내부링크 삽입 테스트

    마크다운 본문에 내부링크를 삽입합니다. DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_add_internal_links(
        blog_id=req.blog_id,
        module_id=req.module_id,
        current_title=req.title,
        content=req.content,
        il_settings=req.il_settings,
    )


@router.post("/generate-image")
async def test_generate_image(
    req: GenerateImageRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 6: 이미지 생성 테스트

    블로그 설정에 따라 AI 또는 템플릿 이미지를 생성합니다.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_generate_image(
        module_id=req.module_id,
        blog_id=req.blog_id,
        title=req.title,
        image_settings=req.image_settings,
    )


@router.post("/substitution-html")
async def test_substitution_html(
    req: SubstitutionHtmlRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Step 7: 치환 처리 + HTML 변환 테스트

    마크다운을 HTML로 변환하고 치환 처리합니다. DB 변경 없음.
    """
    tester = PipelineTester(db, user.id)
    return await tester.test_substitution_html(
        blog_id=req.blog_id,
        content=req.content,
        text_replace_enabled=req.text_replace_enabled,
    )


@router.post("/full-pipeline")
async def test_full_pipeline(
    req: FullPipelineRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """
    전체 파이프라인 테스트 (7단계)

    모든 단계를 순서대로 실행합니다.
    dry_run=True면 DB에 저장하지 않습니다.
    """
    tester = FullPipelineTester(db, user.id)
    return await tester.test_full_pipeline(
        blog_id=req.blog_id,
        module_id=req.module_id,
        dry_run=req.dry_run,
    )
