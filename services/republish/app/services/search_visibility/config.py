"""블로그별 검색 노출 설정 로드·병합.

`blogs.search_index_config`(JSON)를 다루는 유일한 지점이다. 기존 블로그는 값이
None 이므로 항상 기본값과 병합해서 읽는다.

IndexNow 키는 설계상 **공개 값**이다(호스트 루트에 평문 .txt 로 노출되어야 검증된다).
따라서 암호화하지 않는다.
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# indexnow_enabled 기본값이 False 인 이유:
# 계획서 순서(S6 → S1)를 지키기 위해 색인율 기준선을 먼저 확보한 뒤 사용자가 켠다.
DEFAULT_SEARCH_INDEX_CONFIG: Dict[str, Any] = {
    "indexnow_enabled": False,
    "indexnow_key": None,
    "indexnow_key_verified": False,
    "indexnow_key_checked_at": None,
    "indexnow_key_error": None,
    "sitemap_check_enabled": True,
    "sitemap_url": None,
    "index_check_enabled": True,
    "index_check_daily_cap": 20,
    # X5 디스커버 — 켜지 않으면 어떤 동작도 바뀌지 않는다(진단은 항상 가능).
    "discover_enabled": False,
    "discover_min_image_width": 1200,
    "discover_block_on_fail": False,
    # X1 외부 링크 — 0이면 상한 없음(rel 표시는 항상 적용)
    "max_external_links": 0,
    # S6-N 네이버 색인 점검 — 웹문서 검색 API 사용
    "naver_check_enabled": True,
    "naver_check_daily_cap": 20,
}

# IndexNow 키 파일을 호스트 루트에 올릴 수 있는 플랫폼만 지원한다.
# 블로거는 루트에 임의 파일을 서빙할 수 없어 구조적으로 불가능하다.
INDEXNOW_SUPPORTED_PLATFORMS = {"wordpress", "other"}


def merge_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """저장된 설정을 기본값과 병합한다.

    Args:
        raw: `blogs.search_index_config` 원본(None 가능)

    Returns:
        모든 키가 채워진 설정 딕셔너리(원본을 변형하지 않는다)
    """
    merged = dict(DEFAULT_SEARCH_INDEX_CONFIG)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in merged:
                merged[key] = value
    return merged


def load_config(blog: Any) -> Dict[str, Any]:
    """블로그 객체에서 검색 노출 설정을 읽어 병합한다."""
    return merge_config(getattr(blog, "search_index_config", None))


def platform_of(blog: Any) -> str:
    """블로그 플랫폼을 문자열로 반환한다."""
    platform = getattr(blog, "platform", None)
    value = getattr(platform, "value", platform)
    return str(value or "").lower()


def indexnow_supported(blog: Any) -> bool:
    """IndexNow 키 파일을 올릴 수 있는 플랫폼인지 판정한다.

    블로거는 호스트 루트에 `{key}.txt` 를 놓을 수 없고, keyLocation 으로 하위
    경로를 지정하면 그 하위 URL 만 제출 가능해져 사실상 쓸 수 없다.
    """
    return platform_of(blog) in INDEXNOW_SUPPORTED_PLATFORMS


def generate_indexnow_key() -> str:
    """IndexNow 키를 생성한다(16진 32자)."""
    return secrets.token_hex(16)


def blog_host(blog: Any) -> Optional[str]:
    """블로그 URL 에서 호스트를 뽑는다. 실패하면 None."""
    raw = (getattr(blog, "url", "") or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    host = urlparse(raw).hostname
    return host or None


def key_file_url(blog: Any, key: str) -> Optional[str]:
    """키 파일이 있어야 할 정식 위치를 만든다."""
    host = blog_host(blog)
    if not host or not key:
        return None
    return f"https://{host}/{key}.txt"
