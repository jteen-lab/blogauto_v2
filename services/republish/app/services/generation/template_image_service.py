"""
템플릿 기반 이미지 합성 서비스

배경 이미지 위에 제목 텍스트를 합성하여 블로그 헤더 이미지를 생성합니다.
Blog.overlay_config 설정을 사용합니다.

설계 문서: generation_pipeline_enhancement_plan.md - Phase C - 5.5
"""
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 이미지 저장 경로
IMAGE_DIR = Path(__file__).parent.parent.parent / "static" / "generated" / "images"

# 기본 이미지 설정
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 630
DEFAULT_BG_COLOR = (41, 128, 185)
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_FONT_SIZE = 48


class TemplateImageService:
    """
    템플릿 기반 이미지 합성 서비스

    배경 이미지(또는 단색) 위에 제목 텍스트를 합성하여
    블로그 헤더 이미지를 생성합니다.
    """

    async def generate(
        self, title: str, blog, blog_id: int,
    ) -> Optional[dict]:
        """
        배경 위에 제목 텍스트를 합성하여 이미지 생성

        Args:
            title: 포스트 제목
            blog: Blog 객체 (overlay_config 사용)
            blog_id: 블로그 ID

        Returns:
            dict: {"image_url": str, "provider": str, "model": None}
            또는 None (실패 시)
        """
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        except ImportError:
            logger.error(
                "[TEMPLATE_IMAGE] Pillow 미설치 - pip install Pillow"
            )
            return None

        config = getattr(blog, "overlay_config", None) or {}

        try:
            image = self._compose_image(title, config)
            local_path = self._save_image(image, blog_id)

            if local_path:
                logger.info(
                    f"[TEMPLATE_IMAGE] 이미지 생성 완료: {local_path}"
                )
                return {
                    "image_url": local_path,
                    "provider": "template",
                    "model": None,
                }
            return None

        except Exception as e:
            logger.error(f"[TEMPLATE_IMAGE] 이미지 합성 실패: {e}")
            return None

    def _compose_image(self, title: str, config: dict):
        """
        이미지 합성 실행

        Args:
            title: 오버레이할 텍스트
            config: Blog.overlay_config 설정

        Returns:
            PIL.Image 객체
        """
        from PIL import Image, ImageDraw

        width = config.get("width", DEFAULT_WIDTH)
        height = config.get("height", DEFAULT_HEIGHT)
        bg_color = tuple(config.get("bg_color", list(DEFAULT_BG_COLOR)))
        text_color = tuple(config.get("text_color", list(DEFAULT_TEXT_COLOR)))
        font_size = config.get("font_size", DEFAULT_FONT_SIZE)

        image = self._create_background(config, width, height, bg_color)

        draw = ImageDraw.Draw(image)
        font = self._load_font(config, font_size)

        lines = self._wrap_text(draw, title, font, width - 80)
        self._draw_centered_text(draw, lines, font, text_color, width, height)

        return image

    def _create_background(
        self, config: dict, width: int, height: int, bg_color: tuple,
    ):
        """배경 이미지 생성 또는 로드"""
        from PIL import Image

        bg_path = config.get("background_image")
        if bg_path and os.path.exists(bg_path):
            image = Image.open(bg_path).resize((width, height))
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 128))
            image = image.convert("RGBA")
            image = Image.alpha_composite(image, overlay)
            return image.convert("RGB")

        return Image.new("RGB", (width, height), bg_color)

    def _load_font(self, config: dict, font_size: int):
        """폰트 로드 (커스텀 → 시스템 → 기본)"""
        from PIL import ImageFont

        font_path = config.get("font_path")
        if font_path and os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                pass

        for path in [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, font_size)
                except Exception:
                    continue

        return ImageFont.load_default()

    def _wrap_text(
        self, draw, text: str, font, max_width: int,
    ) -> list:
        """텍스트를 max_width에 맞게 줄바꿈"""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines or [text]

    def _draw_centered_text(
        self, draw, lines: list, font, text_color: tuple,
        width: int, height: int,
    ) -> None:
        """텍스트를 이미지 중앙에 그리기"""
        line_heights = [
            draw.textbbox((0, 0), line, font=font)[3] for line in lines
        ]
        total_height = sum(line_heights) + 10 * (len(lines) - 1)
        y_offset = (height - total_height) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y_offset), line, fill=text_color, font=font)
            y_offset += bbox[3] + 10

    def _save_image(self, image, blog_id: int) -> Optional[str]:
        """이미지 파일 저장"""
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{blog_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        )
        filepath = IMAGE_DIR / filename

        try:
            image.save(str(filepath), "PNG")
            return f"/static/generated/images/{filename}"
        except Exception as e:
            logger.error(f"[TEMPLATE_IMAGE] 저장 실패: {e}")
            return None
