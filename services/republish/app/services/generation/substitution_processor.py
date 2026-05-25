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
        text_replace_enabled: bool = True,
    ) -> str:
        """
        전체 치환 파이프라인 실행

        Args:
            content: 마크다운 형태의 글 본문
            blog_id: 블로그 ID
            text_replace_enabled: 텍스트 치환 활성화 여부

        Returns:
            치환 완료된 최종 HTML
        """
        blog = await self.db.get(Blog, blog_id)
        if not blog:
            logger.warning(f"[SUBSTITUTION] 블로그 없음: id={blog_id}")
            return self._markdown_to_html(content)

        placeholders = blog.placeholders or {}
        blog_url = blog.url or ""

        # 1. 텍스트 치환 (마크다운 상태에서, 활성화된 경우만)
        if text_replace_enabled:
            text_rules = placeholders.get("text_replace", [])
            if text_rules:
                content = self._apply_text_substitutions(content, text_rules)
                logger.debug(
                    f"[SUBSTITUTION] 텍스트 치환 완료: {len(text_rules)}개 규칙"
                )
            else:
                logger.debug("[SUBSTITUTION] 텍스트 치환 활성화됨, 규칙 없음")
        else:
            logger.debug("[SUBSTITUTION] 텍스트 치환 비활성화")

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
        - 헤딩 (#, ##, ###, ####) + id 속성 (앵커 링크용)
        - 볼드 (**text**)
        - 이탤릭 (*text*)
        - 링크 [text](url)
        - 리스트 (-, *)
        - 번호 리스트 (1., 2.)
        - 인용문 (>)
        - 코드 블록 (```)
        - 수평선 (---, ***)
        - 이미지 ![alt](url)
        - 테이블 (| col1 | col2 |)
        - 목차 자동 네비게이션 링크
        """
        if not content:
            return ""

        # AI 응답이 ```markdown ... ``` 또는 ``` ... ``` 로 전체가
        # 감싸진 경우 unwrap (슈마즈처럼 모델이 응답 전체를 코드 펜스로
        # 감싸 보내면 마크다운 파서가 <pre><code> 로 처리해버리는 회귀
        # 방지)
        content = self._unwrap_outer_fence(content)

        lines = content.split("\n")

        # 1차 스캔: 헤딩 목록 수집 (목차 링크 생성용)
        heading_map = self._collect_headings(lines)

        html_lines = []
        in_list = False
        in_ordered_list = False
        in_code_block = False
        in_blockquote = False
        in_table = False
        in_toc = False
        heading_id_counter = {}

        for i, line in enumerate(lines):
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

            # 테이블 종료 체크
            if in_table and not stripped.startswith("|"):
                html_lines.append("</tbody></table>")
                in_table = False

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
                # 목차 섹션 종료: 자동 생성 목차 출력
                if in_toc:
                    html_lines.extend(
                        self._render_auto_toc(lines, heading_map)
                    )
                    in_toc = False
                html_lines.append("")
                continue

            # 수평선
            if re.match(r'^(\-{3,}|\*{3,}|_{3,})$', stripped):
                html_lines.append("<hr>")
                continue

            # 테이블 구분선 (|---|---|) → 건너뛰기
            if re.match(r'^\|[\s\-:]+\|', stripped):
                if not in_table:
                    in_table = True
                continue

            # 테이블 행
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [
                    c.strip()
                    for c in stripped.strip("|").split("|")
                ]
                if not in_table:
                    # 헤더 행
                    in_table = True
                    header_html = "".join(
                        f"<th>{self._inline_format(c)}</th>"
                        for c in cells
                    )
                    html_lines.append(
                        f"<table><thead><tr>{header_html}"
                        f"</tr></thead><tbody>"
                    )
                else:
                    row_html = "".join(
                        f"<td>{self._inline_format(c)}</td>"
                        for c in cells
                    )
                    html_lines.append(f"<tr>{row_html}</tr>")
                continue

            # 헤딩
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                # 목차 섹션 종료 (다음 헤딩 도달)
                if in_toc:
                    html_lines.extend(
                        self._render_auto_toc(lines, heading_map)
                    )
                    in_toc = False

                level = len(heading_match.group(1))
                raw_text = heading_match.group(2).strip()
                text = self._inline_format(raw_text)
                heading_id = self._make_heading_id(
                    raw_text, heading_id_counter
                )
                html_lines.append(
                    f'<h{level} id="{heading_id}">{text}</h{level}>'
                )

                # "목차" 헤딩이면 다음 줄부터 목차 항목 수집 시작
                if raw_text.strip() == "목차":
                    in_toc = True

                continue

            # 목차 섹션 내의 AI 작성 텍스트 → 무시 (자동 생성으로 대체)
            if in_toc and stripped and not stripped.startswith(">"):
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
        if in_toc:
            html_lines.extend(self._render_auto_toc(lines, heading_map))
        if in_table:
            html_lines.append("</tbody></table>")
        if in_list:
            html_lines.append("</ul>")
        if in_ordered_list:
            html_lines.append("</ol>")
        if in_blockquote:
            html_lines.append("</blockquote>")
        if in_code_block:
            html_lines.append("</code></pre>")

        return "\n".join(html_lines)

    def _collect_headings(self, lines: list) -> dict:
        """
        마크다운 라인에서 헤딩 텍스트 → ID 매핑 수집

        Args:
            lines: 마크다운 라인 목록

        Returns:
            {헤딩텍스트: heading_id} 딕셔너리
        """
        heading_map = {}
        counter = {}
        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if m:
                raw_text = m.group(2).strip()
                if raw_text == "목차":
                    continue
                heading_id = self._make_heading_id(raw_text, counter)
                heading_map[raw_text] = heading_id
        return heading_map

    @staticmethod
    def _make_heading_id(text: str, counter: dict) -> str:
        """
        헤딩 텍스트로 HTML id 속성 생성

        Args:
            text: 원본 헤딩 텍스트
            counter: 중복 방지용 카운터 딕셔너리

        Returns:
            고유한 heading id 문자열
        """
        slug = re.sub(r'[^\w\s가-힣-]', '', text).strip()
        slug = re.sub(r'\s+', '-', slug)
        if not slug:
            slug = "heading"
        if slug in counter:
            counter[slug] += 1
            return f"{slug}-{counter[slug]}"
        counter[slug] = 0
        return slug

    @staticmethod
    def _render_auto_toc(lines: list, heading_map: dict) -> list:
        """
        실제 문서 헤딩에서 목차를 자동 생성

        AI가 작성한 목차 텍스트를 무시하고, 문서 내 실제 헤딩을
        스캔하여 앵커 링크가 포함된 목차를 생성합니다.
        "목차" 헤딩과 동일 레벨의 헤딩만 수집하며,
        종료 섹션(자주하는 질문, 결론, FAQ, 마무리)은 제외합니다.

        Args:
            lines: 전체 마크다운 라인 목록
            heading_map: {헤딩텍스트: heading_id} 매핑

        Returns:
            HTML 라인 리스트
        """
        skip_headings = {"목차", "자주하는 질문", "결론", "FAQ", "마무리"}

        # "목차" 헤딩의 레벨을 찾아서 같은 레벨만 수집
        toc_level = None
        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if m and m.group(2).strip() == "목차":
                toc_level = len(m.group(1))
                break

        if toc_level is None:
            return []

        toc_headings = []
        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if m:
                level = len(m.group(1))
                if level != toc_level:
                    continue
                raw_text = m.group(2).strip()
                if raw_text in skip_headings:
                    continue
                heading_id = heading_map.get(raw_text)
                if heading_id:
                    toc_headings.append(
                        f'<a href="#{heading_id}">{raw_text}</a>'
                    )

        if not toc_headings:
            return []
        return [f'<p>{"<br>".join(toc_headings)}</p>']

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

    @staticmethod
    def _unwrap_outer_fence(text: str) -> str:
        """AI 응답이 전체적으로 ``` 코드 펜스로 감싸진 경우 제거.

        모델이 응답을 ```markdown ... ``` 또는 ``` ... ``` 으로 감싸는
        경우, 마크다운 파서가 본문을 통째로 <pre><code> 로 만들어버린다.
        본문 안에 다른 ``` 가 있으면 (의도된 코드 블록) 건드리지 않는다.
        """
        stripped = text.strip()
        if not stripped.startswith("```"):
            return text

        lines = stripped.split("\n")
        if len(lines) < 2:
            return text

        first_line = lines[0].strip()
        if not first_line.startswith("```"):
            return text

        # 마지막 비어있지 않은 줄이 ``` 인지 확인
        last_idx = len(lines) - 1
        while last_idx > 0 and not lines[last_idx].strip():
            last_idx -= 1
        if last_idx <= 0 or lines[last_idx].strip() != "```":
            return text

        # 가운데에 ``` 가 또 있으면 의도된 중첩이라 unwrap 하지 않음
        inner_fences = sum(
            1 for ln in lines[1:last_idx]
            if ln.strip().startswith("```")
        )
        if inner_fences > 0:
            return text

        unwrapped = "\n".join(lines[1:last_idx])
        logger.debug(
            "[SUBSTITUTION] 외부 코드 펜스 unwrap | "
            "원본=%d자 → %d자",
            len(text), len(unwrapped),
        )
        return unwrapped
