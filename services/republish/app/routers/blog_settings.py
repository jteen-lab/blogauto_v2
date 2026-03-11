"""
블로그 설정 API 엔드포인트

Features:
- 이미지 설정 관리
- 카테고리 설정 관리
- 치환자 설정 관리
- 스타일 설정 관리
- AI 설정 관리
- 파일 업로드 (템플릿 이미지, 폰트)
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..models.category import Topic, SubTopic, BlogCategory
from ..routers.auth import get_current_user
from ..schemas.blog_settings import (
    ImageSettingsRequest,
    ImageSettingsResponse,
    PlaceholdersRequest,
    PlaceholdersResponse,
    PlaceholderPreviewRequest,
    PlaceholderPreviewResponse,
    StyleSettingsRequest,
    StyleSettingsResponse,
    AISettingsRequest,
    AISettingsResponse,
    BlogSettingsResponse,
)
from ..services.blog_settings_service import (
    get_blog_or_404,
    validate_file_extension,
    save_uploaded_file,
    delete_uploaded_file,
    generate_css,
    apply_placeholders,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_FONT_EXTENSIONS,
    MEDIA_ROOT,
)

logger = get_logger("blog_settings_router", "blog_settings.log")

router = APIRouter(prefix="/blogs/{blog_id}/settings", tags=["블로그 설정"])


# =============================================================================
# 전체 설정 조회
# =============================================================================


@router.get(
    "",
    response_model=BlogSettingsResponse,
    summary="블로그 전체 설정 조회",
    description="블로그의 모든 설정을 조회합니다"
)
async def get_blog_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> BlogSettingsResponse:
    """블로그 전체 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    logger.info(f"블로그 설정 조회 | blog_id={blog_id} | user_id={current_user.id}")

    # overlay_config에서 ai_image_service 추출
    overlay_config = dict(blog.overlay_config or {})
    ai_image_service = overlay_config.pop("ai_image_service", "openai")

    # ai_config.image_ai에서 model 정보 조회
    ai_config_data = blog.ai_config or {}
    image_ai = ai_config_data.get("image_ai", {})
    ai_image_model = image_ai.get("model")

    return BlogSettingsResponse(
        blog_id=blog.id,
        image_settings={
            "image_mode": blog.image_mode,
            "ai_image_service": ai_image_service,
            "ai_image_model": ai_image_model,
            "overlay_config": overlay_config
        },
        category_settings=None,
        placeholders=blog.placeholders or {},
        style_config=blog.style_config or {},
        ai_config=blog.ai_config or {}
    )


# =============================================================================
# 이미지 설정
# =============================================================================


@router.get(
    "/image",
    response_model=ImageSettingsResponse,
    summary="이미지 설정 조회",
    description="블로그의 이미지 설정을 조회합니다"
)
async def get_image_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ImageSettingsResponse:
    """이미지 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)
    overlay_config = blog.overlay_config or {}

    # ai_image_service는 overlay_config 내에 저장됨
    ai_image_service = overlay_config.pop("ai_image_service", "openai")

    # ai_config.image_ai에서 model 정보 조회
    ai_config = blog.ai_config or {}
    image_ai = ai_config.get("image_ai", {})
    ai_image_model = image_ai.get("model")

    return ImageSettingsResponse(
        blog_id=blog.id,
        image_mode=blog.image_mode,
        ai_image_service=ai_image_service,
        ai_image_model=ai_image_model,
        overlay_config=overlay_config
    )


@router.post(
    "/image",
    response_model=ImageSettingsResponse,
    summary="이미지 설정 저장",
    description="블로그의 이미지 설정을 저장합니다"
)
async def save_image_settings(
    blog_id: int,
    request: ImageSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> ImageSettingsResponse:
    """이미지 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    blog.image_mode = request.image_mode

    # ai_image_service를 overlay_config에 함께 저장
    # 기존 파일 경로 보존
    existing_config = dict(blog.overlay_config or {})
    overlay_data = request.overlay_config.model_dump()
    overlay_data["ai_image_service"] = request.ai_image_service
    # 기존 파일 경로 유지
    if "template_image" in existing_config:
        overlay_data["template_image"] = existing_config["template_image"]
    if "font_file" in existing_config:
        overlay_data["font_file"] = existing_config["font_file"]
    blog.overlay_config = overlay_data
    flag_modified(blog, 'overlay_config')

    # ai_config.image_ai에 provider/model 동기화 (기존 키 보존)
    ai_config = dict(blog.ai_config or {})
    ai_config["image_ai"] = {
        "provider": request.ai_image_service,
        "model": request.ai_image_model,
    }
    blog.ai_config = ai_config
    flag_modified(blog, 'ai_config')

    await db.commit()
    await db.refresh(blog)

    logger.info(
        f"이미지 설정 저장 | blog_id={blog_id} | "
        f"mode={request.image_mode} | ai_service={request.ai_image_service} | "
        f"ai_model={request.ai_image_model}"
    )

    return ImageSettingsResponse(
        blog_id=blog.id,
        image_mode=blog.image_mode,
        ai_image_service=request.ai_image_service,
        ai_image_model=request.ai_image_model,
        overlay_config=request.overlay_config.model_dump()
    )


@router.get(
    "/image/file",
    summary="이미지/폰트 파일 조회",
    description="업로드된 템플릿 이미지 또는 폰트 파일을 제공합니다 (인증 불필요)"
)
async def get_image_file(
    blog_id: int,
    file_type: str = Query(..., pattern="^(template|font)$", description="파일 타입"),
    db: AsyncSession = Depends(get_db_session)
) -> FileResponse:
    """이미지/폰트 파일 조회 (인증 없이 접근 가능)."""
    # 블로그 존재 여부만 확인 (인증 불필요)
    from sqlalchemy import select
    from ..models.blog import Blog
    result = await db.execute(select(Blog).where(Blog.id == blog_id, Blog.is_deleted == False))
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="블로그를 찾을 수 없습니다")

    overlay_config = blog.overlay_config or {}
    config_key = "template_image" if file_type == "template" else "font_file"
    file_path_str = overlay_config.get(config_key)

    if not file_path_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_type} 파일이 존재하지 않습니다"
        )

    full_path = MEDIA_ROOT / file_path_str
    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_type} 파일을 찾을 수 없습니다"
        )

    # MIME 타입 결정
    ext = full_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(full_path),
        media_type=media_type,
        filename=full_path.name
    )


@router.post(
    "/image/upload",
    summary="이미지/폰트 파일 업로드",
    description="템플릿 이미지 또는 폰트 파일을 업로드합니다"
)
async def upload_image_file(
    blog_id: int,
    file_type: str = Query(..., pattern="^(template|font)$", description="파일 타입"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """이미지/폰트 파일 업로드."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    # 파일 타입에 따른 확장자 검증
    allowed_ext = ALLOWED_IMAGE_EXTENSIONS if file_type == "template" else ALLOWED_FONT_EXTENSIONS
    ext = validate_file_extension(file.filename, allowed_ext)

    # 파일 저장
    relative_path = save_uploaded_file(file, blog_id, file_type, ext)

    # overlay_config에 파일 경로 업데이트
    overlay_config = dict(blog.overlay_config or {})
    config_key = "template_image" if file_type == "template" else "font_file"
    overlay_config[config_key] = relative_path

    blog.overlay_config = overlay_config
    flag_modified(blog, 'overlay_config')
    await db.commit()

    logger.info(f"파일 업로드 완료 | blog_id={blog_id} | type={file_type} | path={relative_path}")

    return {
        "success": True,
        "file_type": file_type,
        "file_path": relative_path,
        "message": f"{file_type} 파일이 업로드되었습니다"
    }


@router.delete(
    "/image/file",
    summary="이미지/폰트 파일 삭제",
    description="업로드된 템플릿 이미지 또는 폰트 파일을 삭제합니다"
)
async def delete_image_file(
    blog_id: int,
    file_type: str = Query(..., pattern="^(template|font)$", description="파일 타입"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """이미지/폰트 파일 삭제."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    overlay_config = blog.overlay_config or {}
    config_key = "template_image" if file_type == "template" else "font_file"
    file_path_str = overlay_config.get(config_key)

    if not file_path_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{file_type} 파일이 존재하지 않습니다"
        )

    # 파일 삭제
    delete_uploaded_file(file_path_str, blog_id)

    # overlay_config에서 경로 제거
    overlay_config = dict(overlay_config)  # 새 dict로 복사
    overlay_config.pop(config_key, None)
    blog.overlay_config = overlay_config
    flag_modified(blog, 'overlay_config')
    await db.commit()

    return {
        "success": True,
        "file_type": file_type,
        "message": f"{file_type} 파일이 삭제되었습니다"
    }


# =============================================================================
# 치환자 설정
# =============================================================================


@router.get(
    "/placeholders",
    response_model=PlaceholdersResponse,
    summary="치환자 설정 조회",
    description="블로그의 치환자 설정을 조회합니다"
)
async def get_placeholders(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> PlaceholdersResponse:
    """치환자 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    return PlaceholdersResponse(
        blog_id=blog.id,
        placeholders=blog.placeholders or {}
    )


@router.post(
    "/placeholders",
    response_model=PlaceholdersResponse,
    summary="치환자 설정 저장",
    description="블로그의 치환자 설정을 저장합니다"
)
async def save_placeholders(
    blog_id: int,
    request: PlaceholdersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> PlaceholdersResponse:
    """치환자 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    blog.placeholders = request.placeholders.model_dump()
    await db.commit()
    await db.refresh(blog)

    logger.info(f"치환자 설정 저장 | blog_id={blog_id}")

    return PlaceholdersResponse(
        blog_id=blog.id,
        placeholders=blog.placeholders or {}
    )


@router.post(
    "/placeholders/preview",
    response_model=PlaceholderPreviewResponse,
    summary="치환자 미리보기",
    description="치환자 적용 결과를 미리보기합니다"
)
async def preview_placeholders(
    blog_id: int,
    request: PlaceholderPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> PlaceholderPreviewResponse:
    """치환자 미리보기."""
    await get_blog_or_404(blog_id, current_user, db)

    converted = apply_placeholders(request.content, request.placeholders)

    return PlaceholderPreviewResponse(
        original=request.content,
        converted=converted
    )


# =============================================================================
# 스타일 설정
# =============================================================================


@router.get(
    "/style",
    response_model=StyleSettingsResponse,
    summary="스타일 설정 조회",
    description="블로그의 스타일 설정을 조회합니다"
)
async def get_style_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StyleSettingsResponse:
    """스타일 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    return StyleSettingsResponse(
        blog_id=blog.id,
        style_config=blog.style_config or {},
        generated_css=generate_css(blog.style_config or {})
    )


@router.post(
    "/style",
    response_model=StyleSettingsResponse,
    summary="스타일 설정 저장",
    description="블로그의 스타일 설정을 저장합니다"
)
async def save_style_settings(
    blog_id: int,
    request: StyleSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> StyleSettingsResponse:
    """스타일 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    blog.style_config = request.style_config
    await db.commit()
    await db.refresh(blog)

    logger.info(f"스타일 설정 저장 | blog_id={blog_id}")

    return StyleSettingsResponse(
        blog_id=blog.id,
        style_config=blog.style_config or {},
        generated_css=generate_css(blog.style_config or {})
    )


# =============================================================================
# AI 설정
# =============================================================================


@router.get(
    "/ai",
    response_model=AISettingsResponse,
    summary="AI 설정 조회",
    description="블로그의 AI 설정을 조회합니다"
)
async def get_ai_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AISettingsResponse:
    """AI 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    return AISettingsResponse(
        blog_id=blog.id,
        ai_config=blog.ai_config or {}
    )


@router.post(
    "/ai",
    response_model=AISettingsResponse,
    summary="AI 설정 저장",
    description="블로그의 AI 설정을 저장합니다"
)
async def save_ai_settings(
    blog_id: int,
    request: AISettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> AISettingsResponse:
    """AI 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    blog.ai_config = request.ai_config.model_dump()
    await db.commit()
    await db.refresh(blog)

    logger.info(f"AI 설정 저장 | blog_id={blog_id}")

    return AISettingsResponse(
        blog_id=blog.id,
        ai_config=blog.ai_config or {}
    )


# =============================================================================
# 카테고리 설정
# =============================================================================


@router.get(
    "/categories",
    summary="카테고리 설정 조회",
    description="블로그에 설정된 카테고리 목록을 조회합니다"
)
async def get_category_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """블로그 카테고리 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    # BlogCategory에서 현재 블로그에 연결된 SubTopic ID 목록 조회
    result = await db.execute(
        select(BlogCategory.subtopic_id)
        .where(
            BlogCategory.blog_id == blog.id,
            BlogCategory.subtopic_id.isnot(None),
            BlogCategory.is_active == True  # noqa: E712
        )
    )
    selected_ids = [row[0] for row in result.fetchall()]

    logger.info(f"카테고리 설정 조회 | blog_id={blog_id} | count={len(selected_ids)}")

    return {
        "blog_id": blog.id,
        "selected_ids": selected_ids
    }


@router.post(
    "/categories",
    summary="카테고리 설정 저장",
    description="블로그에 카테고리를 설정합니다"
)
async def save_category_settings(
    blog_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """블로그 카테고리 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    selected_ids = request.get("selected_ids", [])

    # 기존 BlogCategory 삭제
    await db.execute(
        BlogCategory.__table__.delete().where(BlogCategory.blog_id == blog.id)
    )

    # 새로운 BlogCategory 생성
    for subtopic_id in selected_ids:
        # SubTopic의 topic_id 조회
        subtopic_result = await db.execute(
            select(SubTopic).where(SubTopic.id == subtopic_id)
        )
        subtopic = subtopic_result.scalar_one_or_none()

        if subtopic:
            new_category = BlogCategory(
                blog_id=blog.id,
                topic_id=subtopic.topic_id,
                subtopic_id=subtopic_id,
                is_active=True
            )
            db.add(new_category)

    await db.commit()

    logger.info(f"카테고리 설정 저장 | blog_id={blog_id} | count={len(selected_ids)}")

    return {
        "success": True,
        "message": "카테고리 설정이 저장되었습니다",
        "count": len(selected_ids)
    }
