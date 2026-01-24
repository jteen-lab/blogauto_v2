"""
치환자 처리 서비스

마크다운 → HTML 변환 후 치환자 규칙을 적용하는 서비스입니다.

주요 기능:
1. HTML 태그 이름 치환 (예: h1 → h2)
2. CSS 클래스 추가/치환
3. 텍스트 단순 치환
4. 블로그 플랫폼별 고급 HTML 처리
"""
import html
import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)


def apply_placeholders(
    html_content: str,
    placeholders: Optional[Dict[str, Any]] = None,
    blog_url: str = ""
) -> str:
    """
    HTML 컨텐츠에 치환자 규칙을 적용합니다.

    Args:
        html_content: 원본 HTML 문자열
        placeholders: 치환자 설정 딕셔너리
            - html_tags: 태그 이름 치환 맵 {"h1": "h2"}
            - css_classes: CSS 클래스 추가 맵 {"h1": "title-main"}
            - text_replace: 텍스트 치환 리스트 [{"find": "●", "replace": "✅"}]
        blog_url: 블로그 URL (플랫폼별 처리용)

    Returns:
        치환된 HTML 문자열

    Raises:
        ValueError: 유효하지 않은 입력값

    Example:
        >>> placeholders = {
        ...     "html_tags": {"h1": "h2"},
        ...     "css_classes": {"p": "content-text"},
        ...     "text_replace": [{"find": "●", "replace": "✅"}]
        ... }
        >>> result = apply_placeholders("<h1>제목</h1>", placeholders)
    """
    if not html_content:
        return ""

    if not isinstance(html_content, str):
        raise ValueError("html_content는 문자열이어야 합니다")

    placeholders = placeholders or {}

    if not isinstance(placeholders, dict):
        logger.warning("placeholders가 딕셔너리가 아닙니다. 빈 딕셔너리로 대체합니다.")
        placeholders = {}

    result = html_content

    try:
        # 1. HTML 태그 이름 치환
        tag_map = placeholders.get("html_tags") or {}
        if tag_map:
            result = _apply_html_tag_map(result, tag_map)
            logger.debug(f"[PLACEHOLDER] HTML 태그 치환 완료: {len(tag_map)}개 규칙")

        # 2. CSS 클래스 추가
        class_map = placeholders.get("css_classes") or {}
        if class_map:
            result = _apply_css_class_map(result, class_map)
            logger.debug(f"[PLACEHOLDER] CSS 클래스 추가 완료: {len(class_map)}개 규칙")

        # 3. 링크 스타일 적용 (일반 링크 / 버튼 링크)
        link_styles = placeholders.get("link_styles") or {}
        if link_styles:
            result = _apply_link_styles(result, link_styles)
            logger.debug(f"[PLACEHOLDER] 링크 스타일 적용 완료")

        # 4. 텍스트 치환
        text_replace = placeholders.get("text_replace") or []
        if text_replace:
            result = _apply_text_replace(result, text_replace)
            logger.debug(f"[PLACEHOLDER] 텍스트 치환 완료: {len(text_replace)}개 규칙")

        # 5. 블로그 타입별 고급 처리
        if blog_url:
            result = _apply_advanced_html_processing(result, blog_url, link_styles)
            logger.debug(f"[PLACEHOLDER] 고급 HTML 처리 완료: {blog_url}")

        return result

    except Exception as e:
        logger.error(f"[PLACEHOLDER] 치환 처리 중 오류 발생: {e}")
        # 오류 발생 시 원본 반환
        return html_content


def _apply_html_tag_map(html_str: str, tag_map: Dict[str, str]) -> str:
    """
    HTML 태그 이름을 치환합니다.

    Args:
        html_str: HTML 문자열
        tag_map: 태그 치환 맵 {"old_tag": "new_tag"}

    Returns:
        태그가 치환된 HTML 문자열

    Example:
        >>> _apply_html_tag_map("<h1>제목</h1>", {"h1": "h2"})
        '<h2>제목</h2>'
    """
    if not tag_map:
        return html_str

    result = html_str

    for old_tag, new_tag in tag_map.items():
        # 입력값 정제 (XSS 방지)
        old_tag = _sanitize_tag_name(old_tag)
        new_tag = _sanitize_tag_name(new_tag)

        if not old_tag or not new_tag:
            continue

        # 여는 태그 치환: <h1> 또는 <h1 class="...">
        result = re.sub(
            rf"<{old_tag}(\s|>)",
            rf"<{new_tag}\1",
            result,
            flags=re.IGNORECASE
        )

        # 닫는 태그 치환: </h1>
        result = re.sub(
            rf"</{old_tag}\s*>",
            rf"</{new_tag}>",
            result,
            flags=re.IGNORECASE
        )

    return result


def _apply_css_class_map(html_str: str, class_map: Dict[str, str]) -> str:
    """
    HTML 태그에 CSS 클래스를 추가합니다.

    Args:
        html_str: HTML 문자열
        class_map: 태그별 클래스 맵 {"tag_name": "class_value"}

    Returns:
        클래스가 추가된 HTML 문자열

    Example:
        >>> _apply_css_class_map("<p>내용</p>", {"p": "content"})
        '<p class="content">내용</p>'
    """
    if not class_map:
        return html_str

    try:
        soup = BeautifulSoup(html_str, "html.parser")

        for tag_name, class_value in class_map.items():
            # 입력값 정제
            tag_name = _sanitize_tag_name(tag_name)
            class_value = _sanitize_class_name(class_value)

            if not tag_name or not class_value:
                continue

            # 해당 태그 모두 찾기
            tags = soup.find_all(tag_name)

            for tag in tags:
                _add_class_to_tag(tag, class_value)

        return str(soup)

    except Exception as e:
        logger.warning(f"[PLACEHOLDER] CSS 클래스 추가 중 오류: {e}")
        return html_str


def _add_class_to_tag(tag: Any, class_value: str) -> None:
    """
    BeautifulSoup 태그에 클래스를 추가합니다.

    Args:
        tag: BeautifulSoup 태그 객체
        class_value: 추가할 클래스 문자열
    """
    if "class" in tag.attrs:
        existing = tag["class"]
        if isinstance(existing, list):
            # 중복 방지
            if class_value not in existing:
                existing.append(class_value)
        else:
            if existing != class_value:
                tag["class"] = [existing, class_value]
    else:
        tag["class"] = class_value


def _apply_link_styles(html_str: str, link_styles: Dict[str, str]) -> str:
    """
    링크(a 태그)에 스타일 클래스를 적용합니다.

    - 일반 링크: default_class 적용
    - 버튼 링크: button_class 적용 (center 태그 내부 또는 특정 조건)

    Args:
        html_str: HTML 문자열
        link_styles: 링크 스타일 설정
            - default_class: 일반 링크에 적용할 CSS 클래스
            - button_class: 버튼 형식 링크에 적용할 CSS 클래스

    Returns:
        링크 스타일이 적용된 HTML 문자열
    """
    if not link_styles:
        return html_str

    default_class = link_styles.get("default_class", "")
    button_class = link_styles.get("button_class", "button-link")

    # 둘 다 비어있으면 처리 불필요
    if not default_class and not button_class:
        return html_str

    try:
        soup = BeautifulSoup(html_str, "html.parser")

        for link in soup.find_all("a"):
            # 버튼 링크 판별 조건:
            # 1. 부모가 center 태그인 경우
            # 2. 이미 button-link 클래스가 있는 경우
            # 3. 부모가 p 태그이고 해당 p 태그에 자식이 a 태그 하나뿐인 경우 (단독 링크)
            is_button_link = False

            # 조건 1: center 태그 안의 링크
            if link.parent and link.parent.name == "center":
                is_button_link = True

            # 조건 2: 이미 button 관련 클래스가 있는 경우
            existing_classes = link.get("class", [])
            if isinstance(existing_classes, str):
                existing_classes = [existing_classes]

            if any("button" in cls.lower() for cls in existing_classes):
                is_button_link = True

            # 조건 3: p 태그의 유일한 자식 링크 (CTA 스타일)
            if link.parent and link.parent.name == "p":
                # p 태그의 텍스트 노드를 제외한 자식 요소가 a 하나뿐인지 확인
                children = [
                    c for c in link.parent.children
                    if not isinstance(c, NavigableString) or c.strip()
                ]
                if len(children) == 1 and children[0] == link:
                    is_button_link = True

            # 클래스 적용
            if is_button_link and button_class:
                _add_class_to_tag(link, button_class)
            elif default_class:
                _add_class_to_tag(link, default_class)

        return str(soup)

    except Exception as e:
        logger.warning(f"[PLACEHOLDER] 링크 스타일 적용 중 오류: {e}")
        return html_str


def _apply_text_replace(html_str: str, replacements: List[Dict[str, str]]) -> str:
    """
    HTML 내 텍스트를 단순 치환합니다.

    Args:
        html_str: HTML 문자열
        replacements: 치환 규칙 리스트 [{"find": "찾을값", "replace": "바꿀값"}]

    Returns:
        텍스트가 치환된 HTML 문자열

    Example:
        >>> _apply_text_replace("● 항목", [{"find": "●", "replace": "✅"}])
        '✅ 항목'
    """
    if not replacements:
        return html_str

    result = html_str

    for item in replacements:
        if not isinstance(item, dict):
            continue

        find_str = item.get("find")
        replace_str = item.get("replace", "")

        # find는 필수
        if not isinstance(find_str, str) or not find_str:
            continue

        # replace는 빈 문자열 허용
        if not isinstance(replace_str, str):
            replace_str = str(replace_str) if replace_str is not None else ""

        result = result.replace(find_str, replace_str)

    return result


def _apply_advanced_html_processing(
    html_str: str,
    blog_url: str,
    link_styles: Optional[Dict[str, str]] = None
) -> str:
    """
    블로그 플랫폼별 고급 HTML 처리를 수행합니다.

    - 티스토리: p태그 사이에 br 추가, center 태그 처리
    - 네이버: 특수 스타일 적용

    Args:
        html_str: HTML 문자열
        blog_url: 블로그 URL
        link_styles: 링크 스타일 설정 (버튼 클래스 등)

    Returns:
        처리된 HTML 문자열
    """
    if not blog_url:
        return html_str

    link_styles = link_styles or {}
    button_class = link_styles.get("button_class", "button-link")

    try:
        soup = BeautifulSoup(html_str, "html.parser")

        # 티스토리 블로그 처리
        if ".tistory.com" in blog_url:
            soup = _process_tistory_html(soup, button_class)

        # 네이버 블로그 처리
        elif "blog.naver.com" in blog_url:
            soup = _process_naver_html(soup)

        # center 태그 제거 (공통)
        for center_tag in soup.find_all("center"):
            center_tag.unwrap()

        return str(soup)

    except Exception as e:
        logger.warning(f"[PLACEHOLDER] 고급 HTML 처리 중 오류: {e}")
        return html_str


def _process_tistory_html(
    soup: BeautifulSoup,
    button_class: str = "button-link"
) -> BeautifulSoup:
    """
    티스토리 블로그용 HTML 처리

    - 연속된 p 태그 사이에 br 태그 추가
    - center 태그 내 링크를 버튼 스타일로 변환

    Args:
        soup: BeautifulSoup 객체
        button_class: 버튼 링크에 적용할 CSS 클래스

    Returns:
        처리된 BeautifulSoup 객체
    """
    # 연속된 p 태그 사이에 br 추가
    p_tags = soup.find_all("p")
    for p_tag in p_tags:
        next_sibling = p_tag.find_next_sibling()
        if next_sibling and next_sibling.name == "p":
            br_tag = soup.new_tag("br")
            p_tag.insert_after(br_tag)

    # center 태그 내 링크를 버튼 스타일로 변환
    for center_tag in soup.find_all("center"):
        for link in center_tag.find_all("a"):
            link["class"] = button_class

    return soup


def _process_naver_html(soup: BeautifulSoup) -> BeautifulSoup:
    """
    네이버 블로그용 HTML 처리

    - 네이버 에디터 호환 스타일 적용

    Args:
        soup: BeautifulSoup 객체

    Returns:
        처리된 BeautifulSoup 객체
    """
    # 네이버 에디터 호환을 위한 처리
    # 현재는 기본 처리만 수행
    return soup


def _sanitize_tag_name(tag_name: str) -> str:
    """
    HTML 태그 이름을 정제합니다 (XSS 방지).

    Args:
        tag_name: 태그 이름

    Returns:
        정제된 태그 이름 (유효하지 않으면 빈 문자열)
    """
    if not isinstance(tag_name, str):
        return ""

    # 소문자로 변환 및 공백 제거
    tag_name = tag_name.lower().strip()

    # 알파벳과 숫자만 허용 (h1, h2, div, span 등)
    if not re.match(r"^[a-z][a-z0-9]*$", tag_name):
        return ""

    # 태그 이름 길이 제한 (최대 20자)
    if len(tag_name) > 20:
        return ""

    return tag_name


def _sanitize_class_name(class_name: str) -> str:
    """
    CSS 클래스 이름을 정제합니다 (XSS 방지).

    Args:
        class_name: 클래스 이름

    Returns:
        정제된 클래스 이름 (유효하지 않으면 빈 문자열)
    """
    if not isinstance(class_name, str):
        return ""

    # 공백 제거
    class_name = class_name.strip()

    # 허용 문자: 알파벳, 숫자, 하이픈, 언더스코어, 공백(다중 클래스)
    if not re.match(r"^[a-zA-Z0-9\-_\s]+$", class_name):
        return ""

    # 클래스 이름 길이 제한 (최대 100자)
    if len(class_name) > 100:
        return ""

    return class_name
