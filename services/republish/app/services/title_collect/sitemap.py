"""사이트맵 파서 — 도메인의 URL 목록과 각 URL 의 제목.

`bulk_collect` 에서 옮겨 왔다. 그 모듈은 폐기됐지만 사이트맵 읽기는
② 도메인 추출의 핵심이라 여기 남긴다. 새 코드가 폐기된 패키지에
의존하지 않게 하는 것이 이동의 목적이다.

계획서: docs/plans/title_tab_workplan.md §2-2
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# <loc> 태그 추출 정규식 (사이트맵·인덱스 공용)
_LOC_PATTERN = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)

# lastmod 태그 추출 정규식 (urlset 안의 <url>...<lastmod>...</lastmod>...)
_LASTMOD_PATTERN = re.compile(r"<lastmod>([^<]+)</lastmod>", re.IGNORECASE)

# 포스트 URL 형태 정규식 (느슨한 휴리스틱)
_POST_URL_HINT = re.compile(
    r"(/\d+(?:\.html)?/?$)"  # 끝이 숫자 또는 숫자.html
    r"|(/entry/)"
    r"|(/post/)"
    r"|(/p/[A-Za-z0-9_\-]+/?$)",
    re.IGNORECASE,
)

# <title> 태그 추출
_TITLE_TAG_PATTERN = re.compile(
    r"<title[^>]*>([^<]+)</title>", re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """HTML/엔티티/CDATA 제거 후 공백 정리.

    Args:
        title: 원본 문자열.

    Returns:
        정리된 제목 문자열.
    """
    if not title:
        return ""
    text = re.sub(r"<[^>]+>", "", title)
    text = (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&apos;", "'")
        .replace("&#39;", "'")
        .replace("<![CDATA[", "")
        .replace("]]>", "")
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class SitemapParser:
    """사이트맵 XML 파서 (인덱스 + urlset 지원).

    Attributes:
        timeout: HTTP 타임아웃 (초).
    """

    def __init__(self, timeout: float = 15.0) -> None:
        """
        Args:
            timeout: 사이트맵 GET 시 타임아웃.
        """
        self.timeout: float = timeout

    async def fetch_urls(
        self,
        blog_domain: str,
        max_urls: Optional[int] = None,
    ) -> List[str]:
        """블로그 도메인의 sitemap.xml 에서 포스트 URL 목록을 추출.

        Args:
            blog_domain: 호스트 (예: "example.com").
            max_urls: 최대 URL 수 (None=무제한).

        Returns:
            추출된 포스트 URL 리스트 (휴리스틱 필터 통과한 것만).
        """
        sitemap_url = f"https://{blog_domain}/sitemap.xml"
        urls: List[str] = []

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True,
            ) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code != 200:
                    logger.debug(
                        "사이트맵 응답 비정상 url=%s status=%d",
                        sitemap_url, resp.status_code,
                    )
                    return []

                content = resp.text
                if "<sitemapindex" in content:
                    urls = await self._parse_index(client, content, max_urls)
                else:
                    urls = self._parse_urlset(content, max_urls)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "사이트맵 파싱 실패 url=%s err=%s", sitemap_url, exc,
            )

        return urls

    async def _parse_index(
        self,
        client: httpx.AsyncClient,
        content: str,
        max_urls: Optional[int],
    ) -> List[str]:
        """sitemapindex 처리 — 하위 사이트맵을 순회하며 URL 수집."""
        urls: List[str] = []
        sub_sitemaps = _LOC_PATTERN.findall(content)

        # post 관련 사이트맵 우선
        post_first = [s for s in sub_sitemaps if "post" in s.lower()]
        ordered = post_first or sub_sitemaps

        for sub_loc in ordered:
            if max_urls and len(urls) >= max_urls:
                break
            try:
                sub_resp = await client.get(sub_loc)
                if sub_resp.status_code == 200:
                    remaining = (
                        None if not max_urls else max_urls - len(urls)
                    )
                    urls.extend(
                        self._parse_urlset(sub_resp.text, remaining)
                    )
                await asyncio.sleep(0.05)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "하위 사이트맵 조회 실패 url=%s err=%s", sub_loc, exc,
                )
                continue

        if max_urls:
            return urls[:max_urls]
        return urls

    def _parse_urlset(
        self,
        content: str,
        max_urls: Optional[int],
    ) -> List[str]:
        """urlset XML 에서 포스트로 보이는 <loc> 만 골라 반환."""
        urls: List[str] = []
        for url in _LOC_PATTERN.findall(content):
            if _POST_URL_HINT.search(url):
                urls.append(url)
                if max_urls and len(urls) >= max_urls:
                    break
        return urls

    async def fetch_url_lastmod_pairs(
        self,
        blog_domain: str,
        max_pairs: Optional[int] = None,
    ) -> List[Tuple[str, Optional[str]]]:
        """포스트 URL 과 lastmod 문자열(있으면) 쌍을 함께 반환.

        고급 모드(증분 수집)에서 lastmod 비교를 위해 사용.

        Args:
            blog_domain: 호스트.
            max_pairs: 최대 쌍 수.

        Returns:
            [(url, lastmod_or_none), ...]. lastmod 형식은 사이트맵 원문 그대로
            (보통 ISO-8601). 호출자가 datetime 파싱 책임.
        """
        sitemap_url = f"https://{blog_domain}/sitemap.xml"
        pairs: List[Tuple[str, Optional[str]]] = []

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True,
            ) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code != 200:
                    return []
                content = resp.text
                if "<sitemapindex" in content:
                    # 인덱스 → URL만 가져오고 lastmod는 None
                    urls = await self._parse_index(
                        client, content, max_pairs,
                    )
                    pairs = [(u, None) for u in urls]
                else:
                    pairs = self._parse_urlset_with_lastmod(
                        content, max_pairs,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "사이트맵 lastmod 페어 파싱 실패 url=%s err=%s",
                sitemap_url, exc,
            )
        return pairs

    @staticmethod
    def _parse_urlset_with_lastmod(
        content: str,
        max_pairs: Optional[int],
    ) -> List[Tuple[str, Optional[str]]]:
        """`<url><loc>...</loc><lastmod>...</lastmod></url>` 블록 파싱."""
        # 블록 단위 분할: 정규식이 무겁지 않도록 단순 분리
        result: List[Tuple[str, Optional[str]]] = []
        # <url> ... </url> 블록 매칭
        url_block_pattern = re.compile(
            r"<url\b[^>]*>(.*?)</url>", re.IGNORECASE | re.DOTALL,
        )
        for block in url_block_pattern.findall(content):
            loc_match = _LOC_PATTERN.search(block)
            if not loc_match:
                continue
            url = loc_match.group(1).strip()
            if not _POST_URL_HINT.search(url):
                continue
            lm_match = _LASTMOD_PATTERN.search(block)
            lastmod = lm_match.group(1).strip() if lm_match else None
            result.append((url, lastmod))
            if max_pairs and len(result) >= max_pairs:
                break
        return result


async def fetch_title_from_url(
    url: str,
    *,
    timeout: float = 10.0,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[str]:
    """단일 URL에서 `<title>` 추출.

    Args:
        url: 포스트 URL.
        timeout: 타임아웃 (client 미사용 시 적용).
        client: 재사용할 httpx 클라이언트 (선택).

    Returns:
        추출된 제목 문자열 (실패 시 None).
    """
    owns_client = client is None
    try:
        if owns_client:
            client = httpx.AsyncClient(
                timeout=timeout, follow_redirects=True,
            )
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        match = _TITLE_TAG_PATTERN.search(resp.text)
        if not match:
            return None
        title = clean_title(match.group(1))
        # 사이트 이름 꼬리 제거 (" - 블로그명")
        title = re.sub(r"\s*[-|]\s*[^-|]+$", "", title)
        return title.strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_title_from_url 실패 url=%s err=%s", url, exc)
        return None
    finally:
        if owns_client and client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


__all__ = ["SitemapParser", "clean_title", "fetch_title_from_url"]
