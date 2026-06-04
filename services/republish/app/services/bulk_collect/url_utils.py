"""대량 수집(bulk_collect) 패키지용 URL/도메인 유틸리티.

`url_ingester.py` 가 500줄 룰을 초과하여, 도메인 추출/플랫폼 추정 등
순수 함수 유틸리티를 분리한 모듈.

외부 호출자는 본 모듈을 직접 import 하지 않으며, `url_ingester.py` 내부에서
사용한다. 시그니처는 기존 private 함수와 동일하므로 동작 호환성 100%.

함수:
    - extract_domain_safe(url): URL 에서 호스트만 안전 추출.
    - guess_platform(domain): 도메인 패턴으로 플랫폼 추정.
"""
from urllib.parse import urlparse

__all__ = ["extract_domain_safe", "guess_platform"]


def extract_domain_safe(url: str) -> str:
    """URL 에서 호스트만 안전하게 추출 (실패 시 빈 문자열).

    Args:
        url: 임의의 URL 문자열 (None / 비정상 입력 허용).

    Returns:
        소문자 호스트 문자열. 추출 실패 시 빈 문자열.
    """
    try:
        parsed = urlparse(url)
        return (parsed.netloc or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def guess_platform(domain: str) -> str:
    """도메인 패턴으로 플랫폼을 추정 (CollectedUrl.platform 채우기용).

    Args:
        domain: 정규화된 호스트(소문자 권장).

    Returns:
        "tistory" | "blogger" | "naver" | "wordpress" | "unknown".
    """
    if not domain:
        return "unknown"
    if "tistory.com" in domain:
        return "tistory"
    if "blogspot.com" in domain or "blogger.com" in domain:
        return "blogger"
    if "naver.com" in domain or "blog.naver" in domain:
        return "naver"
    if "wordpress.com" in domain or "wp.com" in domain:
        return "wordpress"
    return "unknown"
