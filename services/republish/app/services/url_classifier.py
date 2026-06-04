"""
URL 분류기 (Phase B)

대량 수집 모듈에서 입력받은 URL이
- 단일 포스트(post)인지
- 블로그 루트(blog)인지
- 모호한지(unknown)

를 빠르게 판별한다.

판별 우선순위:
    1) 정규식 기반 동기 분류 (가장 빠름)
    2) 그래도 모호하면 호출자가 `try_sitemap()`을 비동기로 호출해 사이트맵 존재 여부로
       블로그 루트 가능성을 확인할 수 있다.

이 모듈은 외부 HTTP 호출을 최소화하기 위해 일단 정규식만으로
충분히 분류 가능한 케이스는 사이트맵 조회 없이 끝낸다.
사이트맵 조회는 비용이 크므로 호출자(ChunkProcessor 등)가 명시적으로 요청할 때만 수행한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 정규식 모음 (모듈 레벨에서 1회 컴파일하여 재사용)
# ---------------------------------------------------------------------------

# 포스트로 판단할 수 있는 일반 패턴
# - /post/<id> /entry/<id> /p/<slug> 등 보편적 블로그 포스트 경로
# - /YYYY/MM/DD/slug 형태 (WordPress 등의 데이트 퍼머링크)
# - 쿼리스트링 ?p=숫자 (WordPress 기본 퍼머링크)
# - 마지막 path segment가 숫자 ID (tistory /숫자, blogger /숫자.html)
_POST_PATTERNS = (
    re.compile(r"/post/\d+/?$", re.IGNORECASE),
    re.compile(r"/entry/[^/]+/?$", re.IGNORECASE),
    re.compile(r"/p/[A-Za-z0-9_\-]+/?$", re.IGNORECASE),
    re.compile(r"/\d{4}/\d{1,2}/\d{1,2}/[^/]+/?$"),
    re.compile(r"[?&]p=\d+(&|$)"),
    re.compile(r"/\d+(?:\.html)?/?$"),  # tistory /123, blogger /123.html
    re.compile(r"/archives/\d+/?$", re.IGNORECASE),
)

# 블로그 루트로 판단할 수 있는 패턴
# - 도메인만 있고 path가 비어있거나 "/" 만 있음
# - /blog/ /category/ /tag/ 같은 인덱스성 path 만 있음
_BLOG_ROOT_PATHS = (
    re.compile(r"^/?$"),
    re.compile(r"^/blog/?$", re.IGNORECASE),
    re.compile(r"^/index(\.html?)?/?$", re.IGNORECASE),
    re.compile(r"^/category/[^/]*/?$", re.IGNORECASE),
    re.compile(r"^/tag/[^/]*/?$", re.IGNORECASE),
)


@dataclass(frozen=True)
class ClassifyResult:
    """URL 분류 결과 데이터 클래스.

    Attributes:
        kind: 분류 결과("post" | "blog" | "unknown").
        confidence: 0.0 ~ 1.0 사이의 확신도.
            - 1.0: 정규식이 명확히 매치되어 거의 확실.
            - 0.6: 휴리스틱이 약간 매치, 다른 신호와 결합 필요.
            - 0.3 이하: 거의 모름.
        reason: 분류 사유(로그/디버깅용 한국어 짧은 설명).
    """

    kind: Literal["post", "blog", "unknown"]
    confidence: float
    reason: str


class URLClassifier:
    """대량 수집 입력 URL을 분류하는 단순 정규식 분류기.

    설계 의도:
        - 동기 메서드(`classify`, `looks_like_post`, `looks_like_blog_root`)는
          네트워크 호출 없이 빠르게 답을 준다.
        - 비동기 `try_sitemap()`은 사이트맵 존재 여부만 확인해 블로그 루트
          가능성을 보강한다. (HEAD 요청 1회만, 호출자가 옵션으로 사용)
    """

    # 사이트맵 검사 시 시도해볼 후보 path
    _SITEMAP_CANDIDATES = (
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-posts.xml",
    )

    def __init__(self) -> None:
        """별다른 상태가 없는 stateless 분류기."""
        # 정규식은 모듈 레벨에 컴파일되어 있음
        pass

    # ------------------------------------------------------------------
    # 동기 분류 메서드
    # ------------------------------------------------------------------

    def looks_like_post(self, url: str) -> bool:
        """URL이 단일 포스트 형태인지 정규식으로 판별.

        Args:
            url: 검사할 URL 문자열.

        Returns:
            포스트로 보이면 True, 아니면 False.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            path = parsed.path or ""
            query = parsed.query or ""
            target = f"{path}?{query}" if query else path
            for pattern in _POST_PATTERNS:
                if pattern.search(target):
                    return True
            return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("looks_like_post 파싱 실패 url=%s err=%s", url, exc)
            return False

    def looks_like_blog_root(self, url: str) -> bool:
        """URL이 블로그 루트/얕은 인덱스 페이지인지 정규식으로 판별.

        Args:
            url: 검사할 URL 문자열.

        Returns:
            루트로 보이면 True, 아니면 False.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = parsed.netloc or ""
            path = parsed.path or ""
            # 호스트가 없으면 분류 불가
            if not host:
                return False
            # 쿼리스트링이 있는 루트는 보통 검색 페이지 → 루트로 보지 않음
            if parsed.query:
                return False
            for pattern in _BLOG_ROOT_PATHS:
                if pattern.match(path):
                    return True
            return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("looks_like_blog_root 파싱 실패 url=%s err=%s", url, exc)
            return False

    def classify(self, url: str) -> ClassifyResult:
        """주어진 URL을 post/blog/unknown 중 하나로 동기 분류.

        Args:
            url: 검사할 URL.

        Returns:
            ClassifyResult: 분류 결과와 확신도.
        """
        if not url or not isinstance(url, str):
            return ClassifyResult("unknown", 0.0, "빈 입력")

        if self.looks_like_post(url):
            return ClassifyResult(
                "post",
                0.95,
                "포스트 패턴 매치(정규식)",
            )

        if self.looks_like_blog_root(url):
            return ClassifyResult(
                "blog",
                0.85,
                "루트/얕은 인덱스 path 매치",
            )

        # 위 두 패턴 모두 매치 못 한 경우
        # - 너무 짧은 path 는 약한 신호로 blog 추정
        try:
            parsed = urlparse(url)
            path_depth = len([p for p in (parsed.path or "").split("/") if p])
            if path_depth <= 1 and parsed.netloc:
                return ClassifyResult(
                    "blog",
                    0.5,
                    "path 깊이 얕음(추정)",
                )
        except Exception:  # noqa: BLE001
            pass

        return ClassifyResult(
            "unknown",
            0.3,
            "정규식 미매치 — 사이트맵 보강 필요",
        )

    # ------------------------------------------------------------------
    # 비동기 보강 메서드
    # ------------------------------------------------------------------

    async def try_sitemap(
        self,
        url: str,
        timeout: float = 5.0,
    ) -> bool:
        """사이트맵 존재 여부를 HEAD 요청으로 확인해 블로그 가능성을 보강한다.

        해당 호스트에 `/sitemap.xml` 등 후보 path 중 하나라도 200/3xx 응답을
        내면 블로그(루트)일 가능성이 높다고 판단해 True 를 반환한다.

        Args:
            url: 검사할 URL (호스트만 사용).
            timeout: HTTP 타임아웃 (초).

        Returns:
            사이트맵이 하나라도 존재하면 True, 아니면 False.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = parsed.netloc
            scheme = parsed.scheme or "https"
            if not host:
                return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("try_sitemap URL 파싱 실패 url=%s err=%s", url, exc)
            return False

        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True,
        ) as client:
            for candidate in self._SITEMAP_CANDIDATES:
                target = f"{scheme}://{host}{candidate}"
                try:
                    resp = await client.head(target)
                    # 일부 서버는 HEAD 를 막아두므로 GET 으로 폴백
                    if resp.status_code == 405:
                        resp = await client.get(target)
                    if 200 <= resp.status_code < 400:
                        logger.debug(
                            "sitemap 존재 확인 url=%s candidate=%s status=%d",
                            url, candidate, resp.status_code,
                        )
                        return True
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "sitemap 후보 조회 실패 target=%s err=%s",
                        target, exc,
                    )
                    continue
        return False


__all__ = ["URLClassifier", "ClassifyResult"]
