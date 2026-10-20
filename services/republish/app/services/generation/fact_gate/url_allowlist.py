"""F1. 본문 주소 허용 목록 — 목록 밖 주소는 주소만 지우고 기관 이름은 남긴다.

슈마즈 클로드 시험(2026-10-20)에서 세 모델 모두 "참고 자료에 있는 주소만"
지시를 어겼다. haiku 는 www.dic.go.kr(진짜 kdic.or.kr)·all-pension.or.kr
같은 없는 주소를 지어냈다. 말로는 안 지켜져서 저장 직전에 코드로 거른다.

남기는 주소: 이 글의 참고 자료에 실제로 있던 주소 + 허용 목록 도메인
(하위 도메인 포함). 남긴 주소도 실제로 열리는지 한 번 확인한다.

순서도: docs/flowcharts/shoemaz_fact_gate.md (F1)
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from ....core.logger import get_logger

logger = get_logger("fact_gate", "app.log")

DEFAULT_DOMAINS: Tuple[str, ...] = (
    "kdic.or.kr", "fss.or.kr", "fsc.go.kr", "nts.go.kr", "hometax.go.kr",
    "cu.co.kr", "kfcc.co.kr", "epost.go.kr", "nps.or.kr", "kofia.or.kr",
    "krx.co.kr", "bok.or.kr", "law.go.kr",
)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_MD_LINK = re.compile(r"(?<!!)\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_HTML_LINK = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                        re.I | re.S)
_BARE = re.compile(
    r"(?:https?://|www\.)[^\s<>()\[\]\"'，、]+"
    r"|\b(?:[a-z0-9-]+\.)+(?:go\.kr|or\.kr|co\.kr|ac\.kr|re\.kr|kr|com|net|org)"
    r"\b(?:/[^\s<>()\[\]\"'，、]*)?", re.I)
_TRAIL = ".,;:!?。"
_EMPTY_PAREN = re.compile(
    r"[ \t]*\(\s*(?:[가-힣A-Za-z ]{0,10}[:：]\s*)?\)|[ \t]*（\s*）")
_PH = "\u0000L{}\u0000"


def _norm(url: str) -> str:
    """비교용 주소: 스킴·www·끝 슬래시 없이 소문자."""
    u = url.strip()
    if not re.match(r"^[a-z]+://", u, re.I):
        u = "https://" + u
    try:
        p = urlparse(u)
    except ValueError:
        return ""
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = (p.path or "").rstrip("/")
    return host + path + (("?" + p.query) if p.query else "")


def host_of(url: str) -> str:
    """주소의 호스트(www 제외)."""
    return _norm(url).split("/", 1)[0].split("?", 1)[0]


def domain_allowed(url: str, domains: Iterable[str]) -> bool:
    """허용 도메인과 같거나 그 하위 도메인인가."""
    host = host_of(url)
    if not host:
        return False
    for d in domains:
        d = str(d).lower().strip().lstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def allowed(url: str, ref_urls: Iterable[str], domains: Iterable[str]) -> bool:
    """참고 자료에 있던 주소이거나 허용 도메인이면 True."""
    key = _norm(url)
    return bool(key) and (key in {_norm(r) for r in ref_urls if r}
                          or domain_allowed(url, domains))


async def _alive(url: str, cache: Dict[str, bool]) -> bool:
    """HTTP 200·300대면 True. 한 번 본 주소는 다시 묻지 않는다."""
    full = url if re.match(r"^[a-z]+://", url, re.I) else "https://" + url
    if full in cache:
        return cache[full]
    ok = False
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.get(full)
            ok = r.status_code < 400
    except Exception as e:  # noqa: BLE001 — 안 열리면 지운다
        logger.info("[FACT_GATE:F1] 열기 실패 | %s | %s", full, e)
    cache[full] = ok
    return ok


async def _keep(url: str, ref_urls: List[str], domains: List[str],
                check_alive: bool, cache: Dict[str, bool]) -> Tuple[bool, str]:
    """(남길지, 지운 이유)."""
    if not allowed(url, ref_urls, domains):
        return False, "허용 목록 밖"
    if check_alive and not await _alive(url, cache):
        return False, "열리지 않음"
    return True, ""


def _tidy(text: str) -> str:
    """주소를 뺀 뒤 남은 빈 괄호·줄 끝 쌍점을 정리한다."""
    text = _EMPTY_PAREN.sub("", text)
    text = re.sub(r"[ \t]*[:：][ \t]*$", "", text, flags=re.M)
    return re.sub(r"[ \t]{2,}", " ", text)


async def scrub(markdown: str, ref_urls: Iterable[str],
                domains: Optional[Iterable[str]] = None,
                check_alive: bool = True) -> Tuple[str, List[dict]]:
    """본문에서 허용 안 되는 주소를 지운다.

    Returns:
        (고친 본문, 지운 주소 목록 [{"url","why"}])
    """
    refs = [u for u in (ref_urls or []) if u]
    doms = list(domains or DEFAULT_DOMAINS)
    cache: Dict[str, bool] = {}
    removed: List[dict] = []
    kept: List[str] = []

    async def link(m: re.Match, text: str, url: str) -> str:
        ok, why = await _keep(url, refs, doms, check_alive, cache)
        if ok:
            kept.append(m.group(0))
            return _PH.format(len(kept) - 1)
        removed.append({"url": url, "why": why})
        return text

    out = await _asub(_MD_LINK, markdown, lambda m: link(m, m.group(1), m.group(2)))
    out = await _asub(_HTML_LINK, out, lambda m: link(m, m.group(2), m.group(1)))

    async def bare(m: re.Match) -> str:
        raw = m.group(0)
        url = raw.rstrip(_TRAIL)
        tail = raw[len(url):]
        if "@" in out[max(0, m.start() - 1):m.start()]:
            return raw  # 메일 주소 뒷부분
        ok, why = await _keep(url, refs, doms, check_alive, cache)
        if ok:
            return raw
        removed.append({"url": url, "why": why})
        return tail

    out = await _asub(_BARE, out, bare)
    if removed:
        out = _tidy(out)
    for i, original in enumerate(kept):
        out = out.replace(_PH.format(i), original)
    for r in removed:
        logger.warning("[FACT_GATE:F1] 주소 삭제 | %s | %s", r["url"], r["why"])
    return out, removed


async def _asub(pattern: re.Pattern, text: str, repl) -> str:
    """re.sub 의 비동기판(치환 함수가 coroutine)."""
    parts, last = [], 0
    for m in pattern.finditer(text):
        if "\u0000" in m.group(0):
            continue
        parts.append(text[last:m.start()])
        parts.append(await repl(m))
        last = m.end()
    parts.append(text[last:])
    return "".join(parts)
