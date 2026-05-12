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
    sanitize_overlay_file_paths,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_FONT_EXTENSIONS,
    MEDIA_ROOT,
)

logger = get_logger("blog_settings_router", "blog_settings.log")

router = APIRouter(prefix="/blogs/{blog_id}/settings", tags=["블로그 설정"])


def _mask_api_key(key: str) -> str:
    """API 키를 마스킹 처리한다.

    Args:
        key: 원본 API 키 문자열

    Returns:
        마스킹된 문자열 (예: "abc***xyz"). 6자 이하면 전체 마스킹.
    """
    if not key:
        return ""
    if len(key) <= 6:
        return "***"
    return key[:3] + "***" + key[-3:]


def _get_imgbb_api_key(placeholders: dict) -> str:
    """placeholders에서 imgBB API 키를 추출한다.

    Args:
        placeholders: Blog.placeholders JSON 딕셔너리

    Returns:
        imgBB API 키 문자열. 없으면 빈 문자열.
    """
    image_hosting = (placeholders or {}).get("image_hosting", {})
    return (image_hosting or {}).get("imgbb_api_key", "")


def _save_imgbb_api_key(blog, raw_key: str, blog_id: int) -> str:
    """imgBB API 키를 Blog.placeholders에 저장/삭제한다.

    Args:
        blog: Blog ORM 인스턴스
        raw_key: 저장할 API 키. 빈 문자열이면 삭제.
        blog_id: 로깅용 블로그 ID

    Returns:
        마스킹된 키 문자열. 삭제 시 빈 문자열.
    """
    placeholders = dict(blog.placeholders or {})

    if raw_key == "":
        # 빈 문자열이면 키 삭제
        image_hosting = placeholders.get("image_hosting", {})
        if isinstance(image_hosting, dict):
            image_hosting.pop("imgbb_api_key", None)
            if not image_hosting:
                placeholders.pop("image_hosting", None)
            else:
                placeholders["image_hosting"] = image_hosting
        blog.placeholders = placeholders
        flag_modified(blog, 'placeholders')
        logger.info(f"imgBB API 키 삭제 | blog_id={blog_id}")
        return ""

    # 키 저장
    image_hosting = placeholders.get("image_hosting", {})
    if not isinstance(image_hosting, dict):
        image_hosting = {}
    image_hosting["imgbb_api_key"] = raw_key
    placeholders["image_hosting"] = image_hosting
    blog.placeholders = placeholders
    flag_modified(blog, 'placeholders')
    logger.info(f"imgBB API 키 저장 | blog_id={blog_id}")
    return _mask_api_key(raw_key)


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

    # 자가치유: 다른 블로그 path / orphan 경로 자동 제거
    raw_overlay = dict(blog.overlay_config or {})
    cleaned_overlay, was_cleaned = sanitize_overlay_file_paths(
        blog_id, raw_overlay,
    )
    if was_cleaned:
        blog.overlay_config = cleaned_overlay
        flag_modified(blog, 'overlay_config')
        await db.commit()
        await db.refresh(blog)
    # overlay_config에서 ai_image_service, cover/section_source 추출
    overlay_config = dict(cleaned_overlay)
    ai_image_service = overlay_config.pop("ai_image_service", "openai")
    cover_source = overlay_config.pop("cover_source", "ai")
    section_source = overlay_config.pop("section_source", "template")

    # ai_config.image_ai에서 model 정보 조회
    ai_config_data = blog.ai_config or {}
    image_ai = ai_config_data.get("image_ai", {})
    ai_image_model = image_ai.get("model")

    # imgBB API 키 마스킹 처리
    raw_imgbb_key = _get_imgbb_api_key(blog.placeholders)
    masked_imgbb_key = _mask_api_key(raw_imgbb_key) if raw_imgbb_key else None

    return BlogSettingsResponse(
        blog_id=blog.id,
        image_settings={
            "image_mode": blog.image_mode,
            "ai_image_service": ai_image_service,
            "ai_image_model": ai_image_model,
            "cover_source": cover_source,
            "section_source": section_source,
            "overlay_config": overlay_config,
            "imgbb_api_key": masked_imgbb_key
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
    # 자가치유: 다른 블로그 path / orphan 경로 자동 제거
    raw_overlay = dict(blog.overlay_config or {})
    cleaned_overlay, was_cleaned = sanitize_overlay_file_paths(
        blog_id, raw_overlay,
    )
    if was_cleaned:
        blog.overlay_config = cleaned_overlay
        flag_modified(blog, 'overlay_config')
        await db.commit()
        await db.refresh(blog)
    overlay_config = dict(cleaned_overlay)

    # ai_image_service는 overlay_config 내에 저장됨
    ai_image_service = overlay_config.pop("ai_image_service", "openai")
    # both 모드 소스 설정도 overlay_config에 저장됨
    cover_source = overlay_config.pop("cover_source", "ai")
    section_source = overlay_config.pop("section_source", "template")

    # ai_config.image_ai에서 model 정보 조회
    ai_config = blog.ai_config or {}
    image_ai = ai_config.get("image_ai", {})
    ai_image_model = image_ai.get("model")

    # imgBB API 키 마스킹 처리
    raw_key = _get_imgbb_api_key(blog.placeholders)
    masked_key = _mask_api_key(raw_key) if raw_key else None

    return ImageSettingsResponse(
        blog_id=blog.id,
        image_mode=blog.image_mode,
        ai_image_service=ai_image_service,
        ai_image_model=ai_image_model,
        cover_source=cover_source,
        section_source=section_source,
        overlay_config=overlay_config,
        imgbb_api_key=masked_key
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

    # ai_image_service, cover_source, section_source를 overlay_config에 함께 저장.
    # file path(template_image/font_file)는 이 엔드포인트에서 절대 변경 불가:
    # 항상 DB의 기존 값을 강제 사용한다. 변경은 image/upload, image/file
    # 엔드포인트에서만 가능. (블로그 간 stale state 오염 회귀 방지)
    existing_config_raw = dict(blog.overlay_config or {})
    existing_config, _ = sanitize_overlay_file_paths(
        blog_id, existing_config_raw,
    )
    overlay_data = request.overlay_config.model_dump()
    overlay_data["ai_image_service"] = request.ai_image_service
    overlay_data["cover_source"] = request.cover_source
    overlay_data["section_source"] = request.section_source
    # file path는 무조건 DB 값으로 덮어씀 (없으면 키 제거).
    # 요청의 template_image/font_file은 무시한다.
    if existing_config.get("template_image"):
        overlay_data["template_image"] = existing_config["template_image"]
    else:
        overlay_data.pop("template_image", None)
    if existing_config.get("font_file"):
        overlay_data["font_file"] = existing_config["font_file"]
    else:
        overlay_data.pop("font_file", None)
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

    # imgBB API 키 저장/삭제 (placeholders.image_hosting.imgbb_api_key)
    if request.imgbb_api_key is not None:
        result = _save_imgbb_api_key(blog, request.imgbb_api_key, blog_id)
        masked_key = result if result else None
    else:
        # 요청에 키가 없으면 기존 값 유지 (마스킹해서 반환)
        raw_key = _get_imgbb_api_key(blog.placeholders)
        masked_key = _mask_api_key(raw_key) if raw_key else None

    await db.commit()
    await db.refresh(blog)

    logger.info(
        f"이미지 설정 저장 | blog_id={blog_id} | "
        f"mode={request.image_mode} | ai_service={request.ai_image_service} | "
        f"ai_model={request.ai_image_model} | "
        f"cover={request.cover_source} | section={request.section_source}"
    )

    return ImageSettingsResponse(
        blog_id=blog.id,
        image_mode=blog.image_mode,
        ai_image_service=request.ai_image_service,
        ai_image_model=request.ai_image_model,
        cover_source=request.cover_source,
        section_source=request.section_source,
        overlay_config=request.overlay_config.model_dump(),
        imgbb_api_key=masked_key
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
