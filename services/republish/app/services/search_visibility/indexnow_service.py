"""S1 — IndexNow 제출.

네이버·빙 등 IndexNow 참여 엔진에 발행 URL을 알린다. 구글은 참여하지 않는다.

핵심 제약(공식 문서 확인):
    키 파일은 **호스트 루트**에 `{key}.txt` 로 있어야 한다. keyLocation 으로 하위
    경로를 지정하면 그 경로 하위 URL 만 제출할 수 있어 블로그 글에는 쓸 수 없다.
    → 키 파일 검증을 통과한 블로그만 제출한다(403 반복 방지).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import httpx

from .config import blog_host, indexnow_supported, key_file_url, load_config

logger = logging.getLogger(__name__)

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT_SECONDS = 15.0

# 스킵 사유(원장 indexnow_error 에 그대로 기록된다)
SKIP_DISABLED = "disabled"
SKIP_UNSUPPORTED = "platform_unsupported"
SKIP_NO_KEY = "no_key"
SKIP_KEY_UNVERIFIED = "key_unverified"
SKIP_HOST_MISMATCH = "host_mismatch"


@dataclass
class SubmitOutcome:
    """IndexNow 제출 1건의 결과."""

    submitted: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    # 403 처럼 키 파일 자체가 문제라 검증 상태를 되돌려야 하는 경우 True
    invalidate_key: bool = False
    # 429·네트워크 오류처럼 뒤에 다시 시도할 가치가 있으면 True
    retryable: bool = False


async def verify_key(blog: Any, key: str) -> Tuple[bool, Optional[str]]:
    """키 파일이 호스트 루트에 올바르게 올라갔는지 확인한다.

    Args:
        blog: 대상 블로그
        key: 검증할 IndexNow 키

    Returns:
        (통과 여부, 실패 사유). 통과면 (True, None).
    """
    url = key_file_url(blog, key)
    if not url:
        return False, "블로그 URL에서 호스트를 확인할 수 없습니다"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url)
    except Exception as exc:  # 네트워크·DNS·TLS 전부 여기로
        return False, f"키 파일 요청 실패: {exc}"

    if response.status_code != 200:
        return False, f"키 파일 응답 {response.status_code} (루트에 업로드했는지 확인)"

    body = (response.text or "").strip()
    if body != key:
        preview = body[:40].replace("\n", " ")
        return False, f"키 파일 내용이 키와 다릅니다 (읽은 값: '{preview}')"

    return True, None


def _skip_reason(blog: Any, url: str, config: dict) -> Optional[str]:
    """제출을 건너뛸 사유를 판정한다. 제출 가능하면 None."""
    if not config.get("indexnow_enabled"):
        return SKIP_DISABLED
    if not indexnow_supported(blog):
        return SKIP_UNSUPPORTED
    if not config.get("indexnow_key"):
        return SKIP_NO_KEY
    if not config.get("indexnow_key_verified"):
        return SKIP_KEY_UNVERIFIED

    host = blog_host(blog)
    target = urlparse(url).hostname
    if not host or not target or host.lower() != target.lower():
        return SKIP_HOST_MISMATCH
    return None


def _classify(status_code: int) -> SubmitOutcome:
    """IndexNow 응답 코드를 결과로 변환한다."""
    if status_code in (200, 202):
        return SubmitOutcome(submitted=True, status_code=status_code)
    if status_code == 403:
        return SubmitOutcome(
            submitted=False, status_code=403, invalidate_key=True,
            error="403 — 키 파일을 찾을 수 없거나 키가 다릅니다. 루트 파일을 다시 확인하세요",
        )
    if status_code == 422:
        return SubmitOutcome(
            submitted=False, status_code=422,
            error="422 — URL이 해당 호스트에 속하지 않거나 키 형식이 맞지 않습니다",
        )
    if status_code == 429:
        return SubmitOutcome(
            submitted=False, status_code=429, retryable=True,
            error="429 — 제출이 너무 잦습니다. 뒤에 다시 시도합니다",
        )
    return SubmitOutcome(
        submitted=False, status_code=status_code,
        error=f"예상치 못한 응답 {status_code}",
    )


async def submit_url(blog: Any, url: str, config: Optional[dict] = None) -> SubmitOutcome:
    """URL 1건을 IndexNow에 제출한다.

    Args:
        blog: 대상 블로그
        url: 발행된 정식 URL
        config: 미리 읽어둔 설정(없으면 블로그에서 읽는다)

    Returns:
        SubmitOutcome — 호출자가 원장에 그대로 기록한다.
    """
    cfg = config if config is not None else load_config(blog)

    skip = _skip_reason(blog, url, cfg)
    if skip:
        return SubmitOutcome(submitted=False, error=skip)

    payload = {
        "host": blog_host(blog),
        "key": cfg["indexnow_key"],
        "urlList": [url],
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(INDEXNOW_ENDPOINT, json=payload)
    except Exception as exc:
        logger.warning("[INDEXNOW] 제출 예외 | blog=%s | %s", getattr(blog, "name", "?"), exc)
        return SubmitOutcome(
            submitted=False, retryable=True, error=f"요청 실패: {exc}",
        )

    outcome = _classify(response.status_code)
    logger.info(
        "[INDEXNOW] blog=%s | url=%s | code=%s | ok=%s",
        getattr(blog, "name", "?"), url, response.status_code, outcome.submitted,
    )
    return outcome
