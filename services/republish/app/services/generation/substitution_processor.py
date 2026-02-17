"""
치환 처리 서비스

생성된 글의 텍스트 치환, HTML 변환, HTML/CSS 치환을 수행합니다.

순서:
1. 텍스트 치환 (마크다운 상태)
2. HTML 변환
3. HTML/CSS 치환 (기존 apply_placeholders 활용)

설계 문서: generation_module_workplan.md - Phase 3 - 3.2.4
"""
import logging
import re
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ..placeholders import apply_placeholders

logger = logging.getLogger(__name__)


class SubstitutionProcessor:
    """
    치환 처리 서비스

    마크다운 → HTML 변환과 치환자 규칙 적용을 통합 처리합니다.
    HTML/CSS 치환은 기존 apply_placeholders 서비스에 위임합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process(
        self,
        content: str,
        blog_id: int,
    ) -> str:
        """
        전체 치환 파이프라인 실행

        Args:
            content: 마크다운 형태의 글 본문
            blog_id: 블로그 ID

        Returns:
            치환 완료된 최종 HTML
        """
        blog = await self.db.get(Blog, blog_id)
        if not blog:
            logger.warning(f"[SUBSTITUTION] 블로그 없음: id={blog_id}")
            return self._markdown_to_html(content)

        placeholders = blog.placeholders or {}
        blog_url = blog.url or ""

        # 1. 텍스트 치환 (마크다운 상태에서)
        text_rules = placeholders.get("text_replace", [])
        if text_rules:
            content = self._apply_text_substitutions(content, text_rules)
            logger.debug(
                f"[SUBSTITUTION] 텍스트 치환 완료: {len(text_rules)}개 규칙"
            )

        # 2. HTML 변환
        html_content = self._markdown_to_html(content)
        logger.debug(
            f"[SUBSTITUTION] 마크다운→HTML 변환 | "
            f"입력={len(content)}자 | 출력={len(html_content)}자"
        )

        # 3. HTML/CSS 치환 (기존 apply_placeholders 활용)
        final_html = apply_placeholders(html_content, placeholders, blog_url)

        logger.info("[SUBSTITUTION] 치환 처리 완료")
        return final_html

    def _apply_text_substitutions(
        self, content: str, rules: list
    ) -> str:
        """마크다운 상태에서 텍스트 치환"""
        for rule in rules:
            if not isinstance(rule, dict):
                continue

            find_str = rule.get("find")
            replace_str = rule.get("replace", "")

            if not find_str or not isinstance(find_str, str):
                continue
            if not isinstance(replace_str, str):
                replace_str = str(replace_str) if replace_str is not None else ""

            content = content.replace(find_str, replace_str)

        return content

    def _markdown_to_html(self, content: str) -> str:
        """
        마크다운을 HTML로 변환

        기본적인 마크다운 문법을 지원합니다:
        - 헤딩 (#, ##, ###, ####)
        - 볼드 (**text**)
        - 이탤릭 (*text*)
        - 링크 [text](url)
        - 리스트 (-, *)
        - 번호 리스트 (1., 2.)
        - 인용문 (>)
        - 코드 블록 (```)
        - 수평선 (---, ***)
        - 이미지 ![alt](url)
        """
        if not content:
            return ""

        lines = content.split("\n")
        html_lines = []
        in_list = False
        in_ordered_list = False
        in_code_block = False
        in_blockquote = False

        for line in lines:
            stripped = line.strip()

            # 코드 블록
            if stripped.startswith("```"):
                if in_code_block:
                    html_lines.append("</code></pre>")
                    in_code_block = False
                else:
                    html_lines.append("<pre><code>")
                    in_code_block = True
                continue

            if in_code_block:
                html_lines.append(self._escape_html(line))
                continue

            # 리스트 종료 체크
            if in_list and not re.match(r'^[\-\*]\s', stripped):
                html_lines.append("</ul>")
                in_list = False

            if in_ordered_list and not re.match(r'^\d+\.\s', stripped):
                html_lines.append("</ol>")
                in_ordered_list = False

            # 인용문 종료 체크
            if in_blockquote and not stripped.startswith(">"):
                html_lines.append("</blockquote>")
                in_blockquote = False

            # 빈 줄
            if not stripped:
                html_lines.append("")
                continue

            # 수평선
            if re.match(r'^(\-{3,}|\*{3,}|_{3,})$', stripped):
                html_lines.append("<hr>")
                continue

            # 헤딩
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = self._inline_format(heading_match.group(2))
                html_lines.append(f"<h{level}>{text}</h{level}>")
                continue

            # 인용문
            if stripped.startswith(">"):
                text = self._inline_format(stripped[1:].strip())
                if not in_blockquote:
                    html_lines.append("<blockquote>")
                    in_blockquote = True
                html_lines.append(f"<p>{text}</p>")
                continue

            # 비순서 리스트
            list_match = re.match(r'^[\-\*]\s+(.+)$', stripped)
            if list_match:
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                text = self._inline_format(list_match.group(1))
                html_lines.append(f"<li>{text}</li>")
                continue

            # 순서 리스트
            ol_match = re.match(r'^\d+\.\s+(.+)$', stripped)
            if ol_match:
                if not in_ordered_list:
                    html_lines.append("<ol>")
                    in_ordered_list = True
                text = self._inline_format(ol_match.group(1))
                html_lines.append(f"<li>{text}</li>")
                continue

            # 이미지 (단독 줄)
            img_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
            if img_match:
                alt = self._escape_html(img_match.group(1))
                src = img_match.group(2)
                html_lines.append(f'<img src="{src}" alt="{alt}">')
                continue

            # HTML 태그가 이미 있으면 그대로 유지
            if stripped.startswith("<") and stripped.endswith(">"):
                html_lines.append(stripped)
                continue

            # 일반 단락
            text = self._inline_format(stripped)
            html_lines.append(f"<p>{text}</p>")

        # 열려있는 태그 닫기
        if in_list:
            html_lines.append("</ul>")
        if in_ordered_list:
            html_lines.append("</ol>")
        if in_blockquote:
            html_lines.append("</blockquote>")
        if in_code_block:
            html_lines.append("</code></pre>")

        return "\n".join(html_lines)

    def _inline_format(self, text: str) -> str:
        """인라인 마크다운 포맷 처리"""
        # 이미지
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            r'<img src="\2" alt="\1">',
            text,
        )
        # 링크
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2">\1</a>',
            text,
        )
        # 볼드
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # 이탤릭
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        # 인라인 코드
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)

        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        """HTML 특수 문자 이스케이프"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
