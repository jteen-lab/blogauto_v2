"""발행 파이프라인 인라인 이미지 경로/URL 처리 유틸.

publisher_pipeline.py가 500줄 제한에 근접해 분리(CLAUDE.md 규칙 3).
"""
import re
from pathlib import Path
from typing import Optional

from ...core.config import settings
from ...core.logger import get_logger

logger = get_logger("publisher_pipeline", "app.log")


def strip_local_image_url(html: str, local_url: str) -> str:
    """업로드 실패한 로컬 이미지 URL을 HTML에서 제거한다.

    img 태그의 src를 빈 값으로 대체하고 data-upload-failed 속성을
    추가한다. href 등 나머지 참조도 제거한다.

    Args:
        html: 대상 HTML 문자열
        local_url: 제거할 로컬 URL

    Returns:
        로컬 URL이 제거된 HTML
    """
    html = re.sub(
        rf'(<img[^>]*?)src=["\']'
        + re.escape(local_url)
        + r'["\']([^>]*?>)',
        r'\1src="" data-upload-failed="true"\2',
        html,
    )
    html = html.replace(local_url, "")
    return html


def resolve_image_path(image_url: str) -> Optional[str]:
    """이미지 URL을 로컬 파일 경로로 변환한다.

    image_url 형식: /static/generated/images/xxx.webp

    Args:
        image_url: 변환할 이미지 URL

    Returns:
        존재하는 로컬 절대 경로 문자열, 없으면 None
    """
    if not image_url:
        return None

    project_root = Path(__file__).resolve().parents[3]

    if image_url.startswith("/static/"):
        local_path = project_root / "app" / image_url.lstrip("/")
    elif image_url.startswith("app/static/"):
        local_path = project_root / image_url
    else:
        local_path = (
            project_root / settings.image_storage_dir
            / Path(image_url).name
        )

    if local_path.exists():
        return str(local_path)

    logger.debug("[PIPELINE] 이미지 경로 미존재: %s", local_path)
    return None
