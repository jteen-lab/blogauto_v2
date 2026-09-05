"""URL 맞추기 — 세 곳이 서로 다른 모양으로 같은 글을 가리킨다.

    우리 DB   https://carin4note.blogspot.com/2026/09/foo.html
    GSC       https://carin4note.blogspot.com/2026/09/foo.html
    GA4       /2026/09/foo.html            ← 경로만 온다

**여기서 틀리면 조용히 0건이 된다.** 그러면 멀쩡한 글이 "유입 없음" 으로
분류돼 재발행이 통째로 갈아엎는다. 그래서 정규화 규칙을 한 곳에만 둔다.

계획서: docs/plans/analytics_integration_plan.md §4
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional
from urllib.parse import urlsplit, unquote

# GA4·GSC 가 붙여 오는 추적 파라미터. 같은 글이 여러 행으로 갈라진다.
_DROP_PARAMS = ("utm_", "fbclid", "gclid", "m=1", "m=0")


def path_of(url: str) -> Optional[str]:
    """비교에 쓸 경로만 남긴다.

    호스트를 버리는 이유: GA4 는 경로만 주고, 블로그 하나가 곧 속성 하나다.
    호스트를 맞추려면 www 유무·프로토콜·커스텀 도메인까지 다 다뤄야 하는데,
    속성이 블로그별로 나뉜 구성에서는 그럴 이유가 없다.
    """
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None

    # GA4 는 이미 경로만 준다. urlsplit 은 이것도 그대로 통과시킨다.
    parts = urlsplit(raw if "//" in raw else f"//{raw}"
                     if raw.startswith("www.") else raw)
    path = parts.path or "/"

    try:
        path = unquote(path)
    except Exception:  # noqa: BLE001 — 깨진 인코딩은 원본 그대로 비교한다
        pass

    # 트레일링 슬래시는 있으나 없으나 같은 글이다(루트는 예외)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path.lower() or "/"


def index_by_path(urls: Iterable) -> Dict[str, object]:
    """URL 객체들을 경로로 색인한다.

    같은 경로가 둘이면 **먼저 온 것**을 남긴다. 재발행으로 URL 이 바뀌면
    옛 행이 남아 있을 수 있는데, 목록은 최신순으로 들어오므로 앞이 최신이다.

    Args:
        urls: `.url` 속성을 가진 객체들(SearchVisibilityUrl 등)

    Returns:
        {경로: 객체}
    """
    out: Dict[str, object] = {}
    for row in urls:
        key = path_of(getattr(row, "url", "") or "")
        if key and key not in out:
            out[key] = row
    return out


def strip_tracking(url: str) -> str:
    """추적 파라미터를 뗀다. 붙은 채로는 같은 글이 여러 행으로 갈라진다."""
    if not url or "?" not in url:
        return url
    base, _, query = url.partition("?")
    keep = [
        part for part in query.split("&")
        if part and not any(part.startswith(bad) or part == bad
                            for bad in _DROP_PARAMS)
    ]
    return f"{base}?{'&'.join(keep)}" if keep else base


class MatchReport:
    """맞춘 결과. 실패를 세어 두지 않으면 정규화가 틀려도 알 수 없다."""

    def __init__(self) -> None:
        self.matched = 0
        self.missed = 0
        self.samples: list = []

    def hit(self) -> None:
        self.matched += 1

    def miss(self, path: str) -> None:
        self.missed += 1
        if len(self.samples) < 5:
            self.samples.append(path)

    @property
    def rate(self) -> float:
        total = self.matched + self.missed
        return round(self.matched / total, 3) if total else 0.0

    def to_dict(self) -> dict:
        return {"matched": self.matched, "missed": self.missed,
                "rate": self.rate, "missed_samples": self.samples}
