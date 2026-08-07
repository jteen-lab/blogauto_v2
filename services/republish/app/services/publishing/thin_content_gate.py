"""발행 직전 최소 분량 게이트 (F6).

계획서: docs/plans/adsense_approval_features_plan.md §3 Phase 2 F6
순서도: docs/flowcharts/adsense_sprint2_f6.md

HTML 태그/마크업을 제외한 순수 텍스트 기준으로 글자수를 세어, 애드센스
"thin content" 반려 기준(600자 미만)에 못 미치는 글의 발행을 차단한다.
"""
from bs4 import BeautifulSoup

THIN_CONTENT_MIN_CHARS: int = 600


def extract_text_length(html: str) -> int:
    """HTML에서 태그를 제외한 순수 텍스트 길이를 반환한다.

    Args:
        html: 발행 직전 최종 본문 HTML

    Returns:
        공백 정규화된 순수 텍스트의 글자수
    """
    if not html:
        return 0
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return len(text)


def check_thin_content(html: str) -> str | None:
    """분량 미달 여부를 판정한다.

    Args:
        html: 발행 직전 최종 본문 HTML

    Returns:
        미달 시 발행 차단 사유 메시지, 기준 충족 시 None
    """
    text_length = extract_text_length(html)
    if text_length >= THIN_CONTENT_MIN_CHARS:
        return None
    return (
        f"본문 분량 미달로 발행을 중단합니다: "
        f"{text_length}자 (최소 {THIN_CONTENT_MIN_CHARS}자)"
    )
