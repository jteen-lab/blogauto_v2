"""
블로그 설정 서비스

Features:
- 블로그 조회 및 권한 검증
- 파일 업로드/삭제 처리
- CSS 생성 유틸리티
"""

import shutil
from pathlib import Path
from typing import Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.blog import Blog
from ..models.user import User

logger = get_logger("blog_settings_service", "blog_settings.log")

# 허용 파일 확장자
ALLOWED_IMAGE_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_FONT_EXTENSIONS: Set[str] = {".ttf", ".otf", ".woff", ".woff2"}

# 파일 저장 기본 경로 (프로젝트 루트 기준)
MEDIA_ROOT = Path(__file__).parent.parent.parent / "media"


def sanitize_overlay_file_paths(
    blog_id: int,
    overlay_config: dict,
) -> tuple[dict, bool]:
    """오버레이 설정에서 다른 블로그 소속 file path를 안전하게 제거한다.

    template_image와 font_file은 'blogs/{blog_id}/' 접두사로 시작해야 한다.
    그 외 경로(다른 블로그/오염/외부 경로)는 자동 제거한다.

    또한 경로가 'blogs/{blog_id}/' 접두사를 만족하더라도 실제 파일이
    존재하지 않으면 함께 제거한다 (orphan 경로 자가 치유).

    Returns:
        (정리된 config 사본, 변경 발생 여부)
    """
    if not isinstance(overlay_config, dict):
        return ({}, False)
    cleaned = dict(overlay_config)
    expected_prefix = f"blogs/{blog_id}/"
    modified = False
    for key in ("template_image", "font_file"):
        path = cleaned.get(key)
        if not path:
            continue
        if not isinstance(path, str) or not path.startswith(expected_prefix):
            logger.warning(
                f"[OVERLAY_CLEAN] 다른 블로그 path 제거 | "
                f"blog_id={blog_id} | {key}={path}"
            )
            cleaned.pop(key, None)
            modified = True
            continue
        full = MEDIA_ROOT / path
        if not full.exists():
            logger.warning(
                f"[OVERLAY_CLEAN] orphan path 제거 | "
                f"blog_id={blog_id} | {key}={path}"
            )
            cleaned.pop(key, None)
            modified = True
    return (cleaned, modified)


async def get_blog_or_404(
    blog_id: int,
    user: User,
    db: AsyncSession
) -> Blog:
    """
    블로그 조회 및 권한 검증.

    Args:
        blog_id: 블로그 ID
        user: 현재 사용자
        db: 데이터베이스 세션

    Returns:
        Blog: 조회된 블로그

    Raises:
        HTTPException: 블로그가 없거나 권한이 없는 경우
    """
    result = await db.execute(
        select(Blog).where(
            Blog.id == blog_id,
            Blog.user_id == user.id,
            Blog.is_deleted == False  # noqa: E712
        )
    )
    blog = result.scalar_one_or_none()

    if not blog:
        logger.warning(f"블로그 조회 실패 | blog_id={blog_id} | user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="블로그를 찾을 수 없습니다"
        )

    return blog


def validate_file_extension(filename: str, allowed_extensions: Set[str]) -> str:
    """
    파일 확장자 검증.

    Args:
        filename: 파일명
        allowed_extensions: 허용된 확장자 집합

    Returns:
        str: 검증된 확장자

    Raises:
        HTTPException: 허용되지 않은 확장자인 경우
    """
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"허용되지 않은 파일 형식입니다. 허용: {', '.join(allowed_extensions)}"
        )
    return ext


def get_upload_path(blog_id: int, file_type: str, filename: str) -> Path:
    """
    파일 업로드 경로 생성.

    Args:
        blog_id: 블로그 ID
        file_type: 파일 타입 (template, font)
        filename: 파일명

    Returns:
        Path: 업로드 경로
    """
    upload_dir = MEDIA_ROOT / "blogs" / str(blog_id) / file_type
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / filename


def save_uploaded_file(
    file,
    blog_id: int,
    file_type: str,
    ext: str
) -> str:
    """
    업로드된 파일 저장.

    Args:
        file: 업로드된 파일 객체
        blog_id: 블로그 ID
        file_type: 파일 타입 (template, font)
        ext: 파일 확장자

    Returns:
        str: 저장된 파일의 상대 경로

    Raises:
        HTTPException: 파일 저장 실패 시
    """
    safe_filename = f"{file_type}_{blog_id}{ext}"
    file_path = get_upload_path(blog_id, file_type, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"파일 저장 실패 | blog_id={blog_id} | error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="파일 저장에 실패했습니다"
        )
    finally:
        file.file.close()

    return str(file_path.relative_to(MEDIA_ROOT))


def delete_uploaded_file(file_path_str: str, blog_id: int) -> bool:
    """
    업로드된 파일 삭제.

    Args:
        file_path_str: 파일 상대 경로
        blog_id: 블로그 ID

    Returns:
        bool: 삭제 성공 여부
    """
    full_path = MEDIA_ROOT / file_path_str
    if full_path.exists():
        try:
            full_path.unlink()
            logger.info(f"파일 삭제 완료 | blog_id={blog_id} | path={file_path_str}")
            return True
        except Exception as e:
            logger.error(f"파일 삭제 실패 | blog_id={blog_id} | error={e}")
            return False
    return False


def generate_css(style_config: dict) -> Optional[str]:
    """
    스타일 설정에서 CSS 문자열 생성.

    Args:
        style_config: 스타일 설정 딕셔너리

    Returns:
        Optional[str]: 생성된 CSS 문자열
    """
    if not style_config:
        return None

    css_lines = []
    for selector, properties in style_config.items():
        if properties:
            props = "; ".join(f"{k}: {v}" for k, v in properties.items())
            css_lines.append(f"{selector} {{ {props}; }}")

    return "\n".join(css_lines) if css_lines else None


def apply_placeholders(content: str, placeholders) -> str:
    """
    컨텐츠에 치환자 적용.

    Args:
        content: 원본 컨텐츠
        placeholders: 치환자 설정

    Returns:
        str: 치환 적용된 컨텐츠
    """
    converted = content

    # HTML 태그 치환
    for old_tag, new_tag in placeholders.html_tags.items():
        converted = converted.replace(f"<{old_tag}>", f"<{new_tag}>")
        converted = converted.replace(f"</{old_tag}>", f"</{new_tag}>")

    # CSS 클래스 치환
    for old_class, new_class in placeholders.css_classes.items():
        converted = converted.replace(f'class="{old_class}"', f'class="{new_class}"')
        converted = converted.replace(f"class='{old_class}'", f"class='{new_class}'")

    # 텍스트 치환
    for item in placeholders.text_replace:
        converted = converted.replace(item.find, item.replace)

    return converted
