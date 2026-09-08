"""서브아이디 — 어느 글에서 전환됐는지.

전환 데이터는 네트워크가 가지고 있다. 우리가 알 수 있는 것은 "이 링크를
눌렀다" 까지다. 링크에 글 번호를 심어 두면 네트워크 리포트와 맞출 수 있다.

이게 없으면 최적화가 불가능하다. CPA 는 글 10편이 전부를 벌고 990편이 0원인
구조라, **어느 10편인지** 모르면 다음 글을 어떻게 쓸지 알 수 없다.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 네트워크가 파라미터 이름을 정하지 않았을 때
DEFAULT_PARAM = "subid"


def make(offer_id: int, post_id: Optional[int] = None,
         blog_id: Optional[int] = None) -> str:
    """서브아이디 값. 짧고 되짚을 수 있어야 한다.

    예: o12-p345-b7
    """
    parts = [f"o{int(offer_id)}"]
    if post_id:
        parts.append(f"p{int(post_id)}")
    if blog_id:
        parts.append(f"b{int(blog_id)}")
    return "-".join(parts)


def parse(value: str) -> dict:
    """서브아이디를 되돌린다. 네트워크 리포트를 우리 글에 붙일 때 쓴다."""
    out: dict = {}
    for token in (value or "").split("-"):
        token = token.strip()
        if len(token) < 2 or not token[1:].isdigit():
            continue
        key = {"o": "offer_id", "p": "post_id", "b": "blog_id"}.get(token[0])
        if key:
            out[key] = int(token[1:])
    return out


def apply(url: str, offer: Any, post_id: Optional[int] = None,
          blog_id: Optional[int] = None) -> str:
    """랜딩 URL 에 서브아이디를 붙인다.

    이미 붙어 있으면 덮어쓴다. 여러 번 붙어 중복 파라미터가 되면 네트워크가
    어느 값을 쓸지 알 수 없다.
    """
    if not url:
        return ""
    param = (getattr(offer, "subid_param", None) or DEFAULT_PARAM).strip()
    value = make(getattr(offer, "id", 0) or 0, post_id, blog_id)

    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k != param]
    query.append((param, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))
