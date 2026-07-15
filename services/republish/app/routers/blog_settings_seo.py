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
    """SEO 설정 저장.

    auto_seo_enabled 활성화 시 detected_plugin이 없으면
    자동으로 플러그인 감지를 시도합니다.
    """
    blog = await get_blog_or_404(blog_id, current_user, db)

    seo_config = blog.seo_config or {}

    data = request.get("seo_config", request)

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

    # auto_seo_enabled 활성화 시 detected_plugin 없으면 자동 감지
    warning = None
    if (
        seo_config.get("auto_seo_enabled")
        and not seo_config.get("detected_plugin")
        and blog.platform.value == "wordpress"
    ):
        from ..services.publishing.seo_detector import SEODetector

        detector = SEODetector()
        detect_result = await detector.detect(blog.url)
        if detect_result.get("detected_plugin"):
            seo_config["detected_plugin"] = detect_result["detected_plugin"]
            seo_config["detected_at"] = detect_result["detected_at"]
            cap = await _probe_write_capability(
                detector, blog, detect_result["detected_plugin"],
            )
            seo_config.update(cap)
            logger.info(
                f"SEO 자동 감지 성공 | blog_id={blog_id} | "
                f"plugin={detect_result['detected_plugin']} | "
                f"write_capable={cap.get('seo_write_capable')}"
            )
        else:
            warning = (
                "SEO 플러그인이 감지되지 않았습니다. "
                "WordPress에 Yoast SEO가 설치·활성화되어 있는지 확인하세요."
            )
            logger.warning(
                f"SEO 자동 감지 실패 | blog_id={blog_id} | url={blog.url}"
            )

    blog.seo_config = seo_config
    flag_modified(blog, "seo_config")
    await db.commit()
    await db.refresh(blog)

    logger.info(f"SEO 설정 저장 | blog_id={blog_id}")

    result = {
        "blog_id": blog.id,
        "seo_config": blog.seo_config or {},
    }
    if warning:
        result["warning"] = warning
    return result


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

    # 실제 SEO 메타 쓰기 가능 여부 프로브 (감지만으로는 자동입력 성공 보장 못함)
    plugin = result.get("detected_plugin")
    if plugin:
        cap = await _probe_write_capability(detector, blog, plugin)
        seo_config.update(cap)
        if cap.get("seo_write_capable") is False:
            logger.warning(
                "[SEO_DETECT] 쓰기 불가 | blog_id=%s | plugin=%s | "
                "xmlrpc 차단 + SEO 메타 REST 미등록(mu-plugin 필요)",
                blog_id, plugin,
            )

    blog.seo_config = seo_config
    flag_modified(blog, "seo_config")
    await db.commit()
    await db.refresh(blog)

    logger.info(
        f"SEO 플러그인 재감지 | blog_id={blog_id} | "
        f"plugin={result.get('detected_plugin')} | "
        f"write_capable={seo_config.get('seo_write_capable')}"
    )

    return {
        "success": True,
        "seo_config": blog.seo_config or {},
        "detected_plugin": result.get("detected_plugin"),
        "display_name": result.get("display_name"),
    }


async def _probe_write_capability(detector, blog, plugin: str) -> dict:
    """블로그 자격증명을 복호화해 SEO 쓰기 가능 여부를 검사한다.

    복호화 실패 시 capable=None(판정 보류)로 안전 처리.
    """
    from ..core.encryption import decrypt_api_key

    username = app_password = None
    try:
        if blog.api_key_encrypted:
            username = decrypt_api_key(blog.api_key_encrypted)
        if blog.api_secret_encrypted:
            app_password = decrypt_api_key(blog.api_secret_encrypted)
    except Exception as e:  # noqa: BLE001
        logger.warning("[SEO_DETECT] 자격증명 복호화 실패 | %s", e)

    return await detector.check_write_capability(
        blog.url, username, app_password, plugin,
    )
