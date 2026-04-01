"""
블로그 SEO 설정 API 엔드포인트

Features:
- SEO 플러그인 감지 결과 조회
- SEO 자동 입력 설정 관리
- SEO 플러그인 재감지
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db_session
from ..core.logger import get_logger
from ..models.user import User
from ..routers.auth import get_current_user
from ..services.blog_settings_service import get_blog_or_404

logger = get_logger("blog_settings_seo", "blog_settings.log")

router = APIRouter(
    prefix="/blogs/{blog_id}/settings",
    tags=["블로그 설정"],
)


@router.get(
    "/seo",
    summary="SEO 설정 조회",
    description="블로그의 SEO 플러그인 설정을 조회합니다",
)
async def get_seo_settings(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """SEO 설정 조회."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    return {
        "blog_id": blog.id,
        "seo_config": blog.seo_config or {},
    }


@router.post(
    "/seo",
    summary="SEO 설정 저장",
    description="블로그의 SEO 설정을 저장합니다",
)
async def save_seo_settings(
    blog_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """SEO 설정 저장."""
    blog = await get_blog_or_404(blog_id, current_user, db)

    seo_config = blog.seo_config or {}

    # 클라이언트가 { seo_config: {...} } 래핑으로 전송할 수 있음
    data = request.get("seo_config", request)

    # 허용 필드만 업데이트 (detected_plugin/detected_at은 감지로만 설정)
    allowed_fields = {
        "auto_seo_enabled",
        "focus_keyphrase_method",
        "slug_method",
        "meta_description_method",
        "meta_description_length",
    }

    for key, value in data.items():
        if key in allowed_fields:
            seo_config[key] = value

    blog.seo_config = seo_config
    flag_modified(blog, "seo_config")
    await db.commit()
    await db.refresh(blog)

    logger.info(f"SEO 설정 저장 | blog_id={blog_id}")

    return {
        "blog_id": blog.id,
        "seo_config": blog.seo_config or {},
    }


@router.post(
    "/seo/detect",
    summary="SEO 플러그인 재감지",
    description="WordPress SEO 플러그인을 다시 감지합니다",
)
async def detect_seo_plugin(
    blog_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """SEO 플러그인 재감지."""
    from ..services.publishing.seo_detector import SEODetector

    blog = await get_blog_or_404(blog_id, current_user, db)

    if blog.platform.value != "wordpress":
        return {
            "success": False,
            "message": "WordPress 블로그만 SEO 플러그인 감지를 지원합니다",
        }

    detector = SEODetector()
    result = await detector.detect(blog.url)

    # seo_config 업데이트 (기존 설정 유지)
    seo_config = blog.seo_config or {}
    seo_config["detected_plugin"] = result.get("detected_plugin")
    seo_config["detected_at"] = result.get("detected_at")

    blog.seo_config = seo_config
    flag_modified(blog, "seo_config")
    await db.commit()
    await db.refresh(blog)

    logger.info(
        f"SEO 플러그인 재감지 | blog_id={blog_id} | "
        f"plugin={result.get('detected_plugin')}"
    )

    return {
        "success": True,
        "seo_config": blog.seo_config or {},
        "detected_plugin": result.get("detected_plugin"),
        "display_name": result.get("display_name"),
    }
