"""발행 주소가 아직 살아 있는지 — 지운 글(404)을 노출 점검에서 빼기 위해.

수작남(2026-10-19 마케팅 진단): '네이버 노출확인 86' 중 79개가 9/29 에 지운 글이었다.
한 번 found 가 되면 다시 안 봐서, 지운 글이 계속 노출로 세어졌다.
기록은 지우지 않고 상태만 'gone' 으로 바꾼다(순서도 search_visibility.md S6-N).
"""
from __future__ import annotations

from typing import Optional

import httpx

from ...core.logger import get_logger

logger = get_logger("url_liveness", "app.log")

TIMEOUT = 15.0
GONE_STATUS = (404, 410)
# 블로거는 Yeti 에도 같은 응답을 준다 — 평범한 브라우저로 본다.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BlogAutoLiveness/1.0)"}


async def status_of(url: str, client: Optional[httpx.AsyncClient] = None) -> Optional[int]:
    """주소의 HTTP 상태 코드. 네트워크 오류면 None(판정 보류)."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                         headers=HEADERS)
    try:
        resp = await client.get(url)
        return resp.status_code
    except Exception as exc:  # noqa: BLE001 — 확인 실패는 '살아 있음'으로 둔다
        logger.warning("[LIVENESS] 확인 실패 | %s | %s", url[:80], exc)
        return None
    finally:
        if own:
            await client.aclose()


def is_gone(status: Optional[int]) -> bool:
    """404·410 만 지운 글로 본다. 5xx·네트워크 오류는 일시 장애일 수 있다."""
    return status in GONE_STATUS
