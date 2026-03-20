"""
템플릿 기반 이미지 합성 서비스

배경 이미지 위에 제목 텍스트를 합성하여 블로그 헤더 이미지를 생성합니다.
Blog.overlay_config 설정을 완전 지원합니다.

설계 문서: generation_pipeline_enhancement_plan.md - Phase C - 5.5
"""
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple

from ...core.config import settings

logger = logging.getLogger(__name__)

# 이미지 저장 경로 (config 기반)
IMAGE_DIR = Path(settings.image_storage_dir)
IMAGE_URL_PREFIX = settings.image_url_prefix

# 미디어 파일 루트 경로 (업로드된 이미지/폰트 저장 위치)
MEDIA_ROOT = Path(__file__).parent.parent.parent.parent / "media"

# app 디렉토리 경로 (/static/ 경로 변환용)
APP_ROOT = Path(__file__).parent.parent.parent

# 기본 이미지 설정 (overlay_config 없을 때 fallback)
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 630
DEFAULT_BG_COLOR = (41, 128, 185)
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_FONT_SIZE = 48
DEFAULT_LINE_HEIGHT = 1.25
DEFAULT_PADDING = {"left": 60, "right": 60, "top": 80, "bottom": 80}


class TemplateImageService:
    """
    템플릿 기반 이미지 합성 서비스

    배경 이미지(또는 단색) 위에 제목 텍스트를 합성하여
    블로그 헤더 이미지를 생성합니다.
    overlay_config의 모든 필드를 지원합니다.
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
        logger.debug(
            f"[TEMPLATE_IMAGE] overlay_config 키 목록: {list(config.keys())}"
        )

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
        from PIL import ImageDraw

        # 설정 추출
        font_size = config.get("font_size", DEFAULT_FONT_SIZE)
        text_color = self._parse_color(
            config.get("text_color"), DEFAULT_TEXT_COLOR,
        )
        padding = self._get_padding(config)
        line_height = config.get("line_height", DEFAULT_LINE_HEIGHT)
        text_align = config.get("text_align", "center")
        vertical_align = config.get("vertical_align", "center")

        # 배경 이미지 생성/로드
        image = self._create_background(config)
        width, height = image.size

        draw = ImageDraw.Draw(image)
        font = self._load_font(config, font_size)

        max_width = width - padding["left"] - padding["right"]
        lines = self._wrap_text(draw, title, font, max_width)

        # 그림자 → 외곽선 포함 텍스트 그리기
        self._draw_text(
            draw, lines, font, text_color, width, height,
            padding, line_height, text_align, vertical_align,
            config,
        )

        return image

    def _get_padding(self, config: dict) -> dict:
        """overlay_config에서 패딩 값 추출하여 {left,right,top,bottom} 반환"""
        pad = config.get("padding", {})
        if isinstance(pad, dict):
            return {
                "left": pad.get("left", DEFAULT_PADDING["left"]),
                "right": pad.get("right", DEFAULT_PADDING["right"]),
                "top": pad.get("top", DEFAULT_PADDING["top"]),
                "bottom": pad.get("bottom", DEFAULT_PADDING["bottom"]),
            }
        return dict(DEFAULT_PADDING)

    def _parse_color(
        self, color_value, default: Tuple[int, ...],
    ) -> Tuple[int, ...]:
        """색상 값을 RGB 튜플로 변환 (#RRGGBB, rgba(), [R,G,B] 지원)"""
        if color_value is None:
            return default

        # 리스트/튜플인 경우 (레거시 호환)
        if isinstance(color_value, (list, tuple)):
            return tuple(color_value[:3])

        if not isinstance(color_value, str):
            return default

        # '#RRGGBB' 형식
        if color_value.startswith("#"):
            return self._hex_to_rgb(color_value)

        # 'rgba(r,g,b,a)' 또는 'rgb(r,g,b)' 형식
        match = re.match(
            r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", color_value,
        )
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

        return default

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """'#RRGGBB' → (R, G, B) 변환"""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return DEFAULT_TEXT_COLOR
        try:
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return DEFAULT_TEXT_COLOR

    def _resolve_media_path(self, relative_path: str) -> Optional[str]:
        """상대 경로를 절대 경로로 변환 (미존재 시 None)"""
        if not relative_path:
            return None

        path = Path(relative_path)

        # 이미 절대 경로인 경우
        if path.is_absolute():
            return str(path) if path.exists() else None

        # /static/으로 시작하는 경우 → app/ 기준으로 변환
        if relative_path.startswith(("/static/", "static/")):
            clean = relative_path.lstrip("/")
            resolved = APP_ROOT / clean
            if resolved.exists():
                return str(resolved)

        # 기본: MEDIA_ROOT 기준 상대 경로
        resolved = MEDIA_ROOT / relative_path
        if resolved.exists():
            return str(resolved)

        logger.warning(
            f"[TEMPLATE_IMAGE] 파일 경로 해석 실패: {relative_path} "
            f"(MEDIA_ROOT={MEDIA_ROOT})"
        )
        return None

    def _create_background(self, config: dict):
        """배경 이미지 로드(원본 크기) 또는 단색 배경 생성"""
        from PIL import Image

        raw_path = config.get("template_image")
        bg_path = self._resolve_media_path(raw_path) if raw_path else None
        logger.debug(
            f"[TEMPLATE_IMAGE] 배경 이미지 경로: "
            f"raw={raw_path}, resolved={bg_path}"
        )

        if bg_path and os.path.exists(bg_path):
            image = Image.open(bg_path)
            # 배경 이미지가 있으면 원본 크기 사용 (Canvas 미리보기와 일치)
            return image.convert("RGB")

        bg_color = DEFAULT_BG_COLOR
        return Image.new(
            "RGB", (DEFAULT_WIDTH, DEFAULT_HEIGHT), bg_color,
        )

    def _load_font(self, config: dict, font_size: int):
        """폰트 로드 (커스텀 → 시스템 → 기본)"""
        from PIL import ImageFont

        raw_path = config.get("font_file")
        font_path = self._resolve_media_path(raw_path) if raw_path else None
        logger.debug(
            f"[TEMPLATE_IMAGE] 폰트 경로: "
            f"raw={raw_path}, resolved={font_path}"
        )

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
        """텍스트를 max_width에 맞게 줄바꿈하여 라인 목록 반환"""
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

    def _calculate_text_positions(
        self, draw, lines: list, font, width: int, height: int,
        padding: dict, line_height: float,
        text_align: str, vertical_align: str,
    ) -> list:
        """정렬/패딩/줄간격 기반으로 각 라인의 (x, y) 좌표 계산"""
        # 각 라인의 bbox 계산
        bboxes = [
            draw.textbbox((0, 0), line, font=font) for line in lines
        ]
        font_height = bboxes[0][3] - bboxes[0][1] if bboxes else 0
        spacing = int(font_height * line_height)
        total_height = spacing * len(lines) - (spacing - font_height)

        # 수직 정렬 계산
        usable_top = padding["top"]
        usable_bottom = height - padding["bottom"]
        usable_height = usable_bottom - usable_top

        if vertical_align == "top":
            y_start = usable_top
        elif vertical_align == "bottom":
            y_start = usable_bottom - total_height
        else:  # center
            y_start = usable_top + (usable_height - total_height) // 2

        # 각 라인의 좌표 계산
        positions = []
        y = y_start
        for i, line in enumerate(lines):
            text_width = bboxes[i][2] - bboxes[i][0]

            if text_align == "left":
                x = padding["left"]
            elif text_align == "right":
                x = width - padding["right"] - text_width
            else:  # center
                usable_width = width - padding["left"] - padding["right"]
                x = padding["left"] + (usable_width - text_width) // 2

            positions.append((x, y))
            y += spacing

        return positions

    def _draw_text(
        self, draw, lines: list, font, text_color: tuple,
        width: int, height: int, padding: dict,
        line_height: float, text_align: str,
        vertical_align: str, config: dict,
    ) -> None:
        """텍스트를 이미지에 그리기 (정렬, 외곽선, 그림자 지원)"""
        positions = self._calculate_text_positions(
            draw, lines, font, width, height,
            padding, line_height, text_align, vertical_align,
        )

        # 그림자 그리기
        if config.get("shadow_enabled", False):
            self._draw_shadow(draw, lines, font, positions, config)

        # 외곽선 + 텍스트 그리기
        stroke_width = 0
        stroke_fill = None
        if config.get("stroke_enabled", False):
            stroke_width = config.get("stroke_width", 0)
            stroke_fill = self._parse_color(
                config.get("stroke_color"), (0, 0, 0),
            )

        for (x, y), line in zip(positions, lines):
            draw.text(
                (x, y), line, fill=text_color, font=font,
                stroke_width=stroke_width, stroke_fill=stroke_fill,
            )

    def _draw_shadow(
        self, draw, lines: list, font,
        positions: list, config: dict,
    ) -> None:
        """오프셋 위치에 그림자 색상으로 텍스트 그리기"""
        shadow_color = self._parse_color(
            config.get("shadow_color"), (0, 0, 0),
        )
        offset_x = config.get("shadow_offset_x", 0)
        offset_y = config.get("shadow_offset_y", 0)

        for (x, y), line in zip(positions, lines):
            draw.text(
                (x + offset_x, y + offset_y),
                line, fill=shadow_color, font=font,
            )

    def _draw_centered_text(
        self, draw, lines: list, font, text_color: tuple,
        width: int, height: int,
    ) -> None:
        """텍스트를 이미지 중앙에 그리기 (레거시 호환)"""
        padding = dict(DEFAULT_PADDING)
        self._draw_text(
            draw, lines, font, text_color, width, height,
            padding, DEFAULT_LINE_HEIGHT, "center", "center",
            {},
        )

    def _save_image(self, image, blog_id: int) -> Optional[str]:
        """이미지 파일 저장 후 정적 파일 경로 반환"""
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{blog_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        )
        filepath = IMAGE_DIR / filename

        try:
            image.save(str(filepath), "PNG")
            return f"{IMAGE_URL_PREFIX}/{filename}"
        except Exception as e:
            logger.error(f"[TEMPLATE_IMAGE] 저장 실패: {e}")
            return None
