"""
SEO 메타 데이터 생성 서비스

Blog.seo_config의 설정에 따라 규칙 기반으로
Focus Keyphrase, Slug, Meta Description을 생성합니다.

생성 방식:
- rule(템플릿): 제목→keyphrase, 제목→slug, 서론→description

설계 문서: seo_plugin_auto_integration_plan.md - Phase 2
"""
import re
from typing import Optional

from ...models.blog import Blog
from ...core.logger import get_logger

logger = get_logger("seo_meta_builder", "app.log")

# 플러그인별 WordPress 메타 키 매핑
# seo_meta 필드명 → WordPress post_meta 키
# slug은 WordPress core 필드로 별도 전송 (매핑 불필요)
PLUGIN_META_MAP = {
    "yoast": {
        "focus_keyphrase": "_yoast_wpseo_focuskw",
        "meta_description": "_yoast_wpseo_metadesc",
    },
    "rankmath": {
        "focus_keyphrase": "rank_math_focus_keyword",
        "meta_description": "rank_math_description",
    },
    "seopress": {
        "focus_keyphrase": "_seopress_analysis_target_kw",
        "meta_description": "_seopress_titles_desc",
    },
    # AIOSEO는 별도 REST API 사용 (자체 테이블)
}

# Meta Description 기본 최대 길이
DEFAULT_META_DESC_LENGTH = 200


class SEOMetaBuilder:
    """
    SEO 메타 데이터 생성 (규칙 기반)

    Blog.seo_config 설정에 따라:
    - 규칙 기반(rule): 제목→keyphrase, 제목→slug, 서론→description
    """

    @staticmethod
    def build_plugin_meta(
        plugin: str,
        seo_meta: dict,
    ) -> dict:
        """
        SEO 메타를 플러그인별 WordPress meta 키로 변환

        Args:
            plugin: 감지된 플러그인명
            seo_meta: {"focus_keyphrase": ..., ...}

        Returns:
            {"_yoast_wpseo_focuskw": "...", ...}
        """
        mapping = PLUGIN_META_MAP.get(plugin, {})
        result = {}
        for field, meta_key in mapping.items():
            if field in seo_meta and seo_meta[field]:
                result[meta_key] = seo_meta[field]
        return result

    def build(
        self,
        blog: Blog,
        title: str,
        content_html: str,
    ) -> Optional[dict]:
        """
        Blog.seo_config 설정에 따라 SEO 메타 생성

        Args:
            blog: 대상 블로그
            title: 재조합된 포스트 제목
            content_html: 생성된 HTML 본문

        Returns:
            {"focus_keyphrase": ..., "slug": ...,
             "meta_description": ..., "generated_by": ...}
        """
        seo_config = blog.seo_config or {}
        if not seo_config.get("auto_seo_enabled"):
            return None
        if not seo_config.get("detected_plugin"):
            return None

        result = {
            "focus_keyphrase": self._build_keyphrase(
                title, seo_config,
            ),
            "slug": self._build_slug(title, seo_config),
            "meta_description": self._build_description(
                content_html, seo_config,
            ),
            "generated_by": "rule",
        }

        logger.info(
            "[SEO_META] 메타 생성 | blog=%s | "
            "keyphrase='%s' | slug_len=%d | "
            "desc_len=%d",
            blog.name,
            result["focus_keyphrase"][:30],
            len(result["slug"]),
            len(result["meta_description"]),
        )
        return result

    def _build_keyphrase(
        self, title: str, config: dict,
    ) -> str:
        """
        Focus Keyphrase 생성 (규칙 기반: 제목 사용)

        Args:
            title: 포스트 제목
            config: Blog.seo_config

        Returns:
            Focus Keyphrase 문자열
        """
        return title

    def _build_slug(
        self, title: str, config: dict,
    ) -> str:
        """
        Slug 생성 (규칙 기반: 제목에서 하이픈 변환)

        Args:
            title: 포스트 제목
            config: Blog.seo_config

        Returns:
            하이픈으로 연결된 slug 문자열
        """
        slug = re.sub(r'[^\w\s가-힣-]', '', title)
        slug = re.sub(r'\s+', '-', slug.strip())
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug

    def _build_description(
        self, content_html: str, config: dict,
    ) -> str:
        """
        Meta Description 생성 (규칙 기반: 서론 추출)

        Args:
            content_html: 생성된 HTML 본문
            config: Blog.seo_config

        Returns:
            Meta Description 문자열
        """
        max_len = config.get(
            "meta_description_length",
            DEFAULT_META_DESC_LENGTH,
        )
        return self._extract_intro(
            content_html, max_len,
        )

    @staticmethod
    def _extract_intro(
        content_html: str, max_length: int,
    ) -> str:
        """
        HTML에서 서론 도입부 텍스트 추출

        1차: 첫 h2/h3 태그 이전의 텍스트
        2차: 비어있으면 첫 번째 <p> 태그의 텍스트
        """
        if not content_html:
            return ""

        h2_match = re.search(
            r'<h[23][^>]*>', content_html,
            re.IGNORECASE,
        )
        intro_html = (
            content_html[:h2_match.start()]
            if h2_match else content_html
        )

        text = re.sub(r'<[^>]+>', '', intro_html)
        text = re.sub(r'\s+', ' ', text).strip()

        if not text:
            p_match = re.search(
                r'<p[^>]*>(.*?)</p>',
                content_html,
                re.IGNORECASE | re.DOTALL,
            )
            if p_match:
                text = re.sub(
                    r'<[^>]+>', '', p_match.group(1),
                )
                text = re.sub(r'\s+', ' ', text).strip()

        if not text or len(text) <= max_length:
            return text

        return SEOMetaBuilder._truncate_by_sentence(
            text, max_length,
        )

    @staticmethod
    def _truncate_by_sentence(
        text: str, max_length: int,
    ) -> str:
        """온전한 문장 단위로 텍스트를 자름"""
        truncated = text[:max_length]
        last_end = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?'),
            truncated.rfind('다.'),
        )
        if last_end > max_length * 0.5:
            return truncated[:last_end + 1].strip()
        return truncated.strip()
