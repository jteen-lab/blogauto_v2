"""
HTML 이미지 주입 서비스

업로드된 이미지 URL을 생성된 HTML 콘텐츠에 삽입합니다.
에디터 타입별 (Classic/Gutenberg/Blogger) 포맷을 지원합니다.

설계 문서: publish_module_implementation_plan.md - Phase 2
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class HtmlInjector:
    """
    생성된 HTML에 업로드된 이미지 URL 삽입

    에디터 타입별 처리:
    - classic: 표준 <img> 태그
    - block/gutenberg: WordPress Gutenberg 블록 형식
    - blogger: Blogger 스타일 이미지 래퍼
    """

    def inject_featured_image(
        self,
        html: str,
        image_url: str,
        title: str = "",
        editor_type: str = "classic",
        media_id: Optional[int] = None,
        platform: str = "wordpress",
    ) -> str:
        """
        대표 이미지를 HTML 상단에 삽입합니다.

        Args:
            html: 원본 HTML 콘텐츠
            image_url: 업로드된 이미지 URL
            title: 이미지 alt 텍스트
            editor_type: 에디터 타입 (classic/block/gutenberg)
            media_id: WordPress 미디어 ID (Gutenberg용)
            platform: 플랫폼 (wordpress/blogger)

        Returns:
            이미지가 삽입된 HTML
        """
        if not image_url:
            return html

        safe_title = self._escape_html(title)

        if platform == "blogger":
            image_block = self._blogger_image(
                image_url, safe_title
            )
        else:
            # WordPress: classic/gutenberg 모두 caption shortcode 사용
            image_block = self._classic_image(
                image_url, safe_title, media_id
            )

        result = image_block + "\n" + html

        logger.info(
            "[HTML_INJECT] 대표 이미지 삽입 | "
            "platform=%s | editor=%s | url=%s",
            platform, editor_type, image_url[:60],
        )
        return result

    def _classic_image(
        self,
        image_url: str,
        alt: str,
        media_id: Optional[int] = None,
    ) -> str:
        """
        WordPress [caption] shortcode 형식 이미지 HTML

        Args:
            image_url: 업로드된 이미지 URL
            alt: 이미지 alt 텍스트 (포스트 제목)
            media_id: WordPress 미디어 ID

        Returns:
            [caption] shortcode 형식 이미지 HTML
        """
        caption_id = (
            f'id="attachment_{media_id}" '
            if media_id else ""
        )
        wp_class = (
            f"size-full wp-image-{media_id}"
            if media_id else "size-full"
        )
        return (
            f'[caption {caption_id}'
            f'align="aligncenter" width="500"]'
            f'<img src="{image_url}" alt="{alt}" '
            f'width="500" height="500" '
            f'class="{wp_class}" /> '
            f'{alt}[/caption]'
        )

    def _gutenberg_image(
        self,
        image_url: str,
        alt: str,
        media_id: Optional[int] = None,
    ) -> str:
        """
        WordPress Gutenberg 에디터용 이미지 블록

        Note:
            현재 classic/gutenberg 모두 _classic_image()의
            [caption] shortcode를 사용합니다.
            이 메서드는 하위 호환성을 위해 유지됩니다.
        """
        return self._classic_image(image_url, alt, media_id)

    def _blogger_image(
        self, image_url: str, alt: str
    ) -> str:
        """Blogger 스타일 이미지 HTML"""
        return (
            f'<div class="separator" '
            f'style="clear:both;text-align:center;">\n'
            f'    <img border="0" src="{image_url}" '
            f'alt="{alt}" '
            f'style="max-width:100%;height:auto;">\n'
            f'</div>\n'
            f'<br/>'
        )

    def inject_section_images(
        self,
        html: str,
        section_images: list,
        platform: str = "wordpress",
    ) -> str:
        """
        본문 h2/h3 섹션 사이에 이미지 삽입 (향후 확장)

        Args:
            html: 원본 HTML
            section_images: [{"url": str, "alt": str}, ...]
            platform: 플랫폼

        Returns:
            섹션 이미지가 삽입된 HTML
        """
        if not section_images:
            return html

        # h2 태그 위치 찾기
        pattern = re.compile(r'(<h[23][^>]*>)', re.IGNORECASE)
        positions = [
            m.start() for m in pattern.finditer(html)
        ]

        if not positions or len(positions) < 2:
            return html

        # 첫 번째 h2 이후 섹션들 사이에 이미지 삽입
        result_parts = []
        last_pos = 0
        img_idx = 0

        for i, pos in enumerate(positions):
            if i == 0:
                continue
            if img_idx >= len(section_images):
                break

            result_parts.append(html[last_pos:pos])
            img = section_images[img_idx]
            img_url = img.get("url", "")
            img_alt = self._escape_html(img.get("alt", ""))

            if platform == "blogger":
                img_html = self._blogger_image(img_url, img_alt)
            else:
                img_html = (
                    f'<div style="margin:20px 0;">\n'
                    f'    <img src="{img_url}" alt="{img_alt}" '
                    f'style="width:100%;height:auto;">\n'
                    f'</div>\n'
                )

            result_parts.append(img_html + "\n")
            last_pos = pos
            img_idx += 1

        result_parts.append(html[last_pos:])
        return "".join(result_parts)

    @staticmethod
    def _escape_html(text: str) -> str:
        """HTML 특수문자 이스케이프"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
