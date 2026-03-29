"""
이미지 오버레이 헬퍼

AI 생성 이미지 위에 제목 텍스트를 오버레이하는 기능을 제공합니다.
ImageGenerator에서 분리하여 파일 크기 제한(500줄)을 준수합니다.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_image_path(image_path: str) -> Optional[Path]:
    """상대 URL을 절대 경로로 변환"""
    base_dir = Path(__file__).parent.parent.parent
    if image_path.startswith("/static/"):
        abs_path = base_dir / image_path.lstrip("/")
    else:
        abs_path = Path(image_path)
    if not abs_path.exists():
        logger.error(f"[IMAGE_GEN] 원본 이미지 없음: {abs_path}")
        return None
    return abs_path


async def overlay_title_on_image(
    template_image_svc,
    image_path: str,
    title: str,
    overlay_config: dict,
) -> Optional[str]:
    """
    AI 이미지 위에 제목 텍스트 오버레이

    TemplateImageService의 텍스트 렌더링 기능을 재사용하여
    overlay_config의 모든 설정(정렬, 외곽선, 그림자 등)을 적용합니다.

    Args:
        template_image_svc: TemplateImageService 인스턴스
        image_path: 원본 이미지 경로
        title: 오버레이할 제목 텍스트
        overlay_config: Blog.overlay_config 딕셔너리

    Returns:
        이미지 경로 또는 None (실패 시)
    """
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        logger.error("[IMAGE_GEN] Pillow 미설치 - 오버레이 불가")
        return None

    abs_path = resolve_image_path(image_path)
    if not abs_path:
        return None

    try:
        image = Image.open(str(abs_path)).convert("RGB")
        draw = ImageDraw.Draw(image)

        svc = template_image_svc
        font_size = overlay_config.get("font_size", 48)
        text_color = svc._parse_color(
            overlay_config.get("text_color"), (255, 255, 255),
        )
        font = svc._load_font(overlay_config, font_size)
        padding = svc._get_padding(overlay_config)

        width, height = image.size
        max_width = width - padding["left"] - padding["right"]
        lines = svc._wrap_text(draw, title, font, max_width)

        line_height = overlay_config.get("line_height", 1.25)
        text_align = overlay_config.get("text_align", "center")
        vertical_align = overlay_config.get("vertical_align", "center")

        svc._draw_text(
            draw, lines, font, text_color, width, height,
            padding, line_height, text_align, vertical_align,
            overlay_config,
        )

        image.save(str(abs_path), "PNG")
        logger.info(f"[IMAGE_GEN] 오버레이 저장: {image_path}")
        return image_path
    except Exception as e:
        logger.error(f"[IMAGE_GEN] 오버레이 실패: {e}")
        return None
