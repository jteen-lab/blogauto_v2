"""형제 블로그 판정 — 제목 중복 조건부 차단용 (계획서 N2).

같은 제목의 글을 여러 블로그에 뿌리는 것 자체를 금지하지는 않는다. 노출 총량을
늘리는 기존 전략이 있기 때문이다. 다만 아래 두 경우는 총량을 늘리지도 못하면서
(서로 경쟁) 중복 콘텐츠 위험만 키우므로 차단한다.

1. **같은 등록 도메인**을 공유하는 블로그 — 같은 사이트 안의 중복이 된다
   (예: doooit082.com / info.doooit082.com / fund.doooit082.com)
2. **같은 모듈에 연결된 블로그** — 공용 니치 모듈이 같은 좁은 제목 풀에서 뽑는다

주의: `*.blogspot.com` 처럼 호스팅 공용 도메인은 등록 도메인을 그 아래 한 단계까지
본다. 그러지 않으면 모든 블로거 블로그가 서로 형제가 되어 버린다.

계획서: docs/plans/niche_title_aeo_plan.md N2
"""
from typing import Any, Iterable, List, Optional, Set
from urllib.parse import urlparse

# 이 접미사 아래는 각자 다른 사이트다(공용 호스팅·2단계 국가 TLD).
# 한 단계 더 내려가야 등록 도메인이 된다.
_MULTI_LABEL_SUFFIXES = {
    # 블로그·정적 호스팅
    "blogspot.com", "blogspot.kr", "tistory.com", "wordpress.com",
    "github.io", "netlify.app", "vercel.app", "wixsite.com", "weebly.com",
    "cafe24.com", "gitbook.io", "pages.dev",
    # 2단계 국가 TLD
    "co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "pe.kr", "kr.com",
    "co.uk", "co.jp", "com.au", "com.br", "co.in",
}


def extract_host(url: Optional[str]) -> str:
    """URL에서 호스트만 뽑는다(스킴·www·포트·경로 제거, 소문자)."""
    if not url:
        return ""
    raw = url.strip()
    if "://" not in raw:
        raw = "http://" + raw
    host = (urlparse(raw).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def registrable_domain(url: Optional[str]) -> str:
    """등록 도메인(같은 사이트로 볼 단위)을 반환한다.

    >>> registrable_domain("https://info.doooit082.com/")
    'doooit082.com'
    >>> registrable_domain("https://guntamoney.blogspot.com/")
    'guntamoney.blogspot.com'   # 공용 호스팅이라 한 단계 더 내려감
    >>> registrable_domain("https://in4note.co.kr/")
    'in4note.co.kr'
    """
    host = extract_host(url)
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) < 2:
        return host

    # 뒤에서부터 2~3레이블을 후보 접미사로 보고 공용 접미사인지 확인
    for take in (3, 2):
        if len(parts) >= take:
            suffix = ".".join(parts[-take:])
            if suffix in _MULTI_LABEL_SUFFIXES and len(parts) > take:
                return ".".join(parts[-(take + 1):])

    return ".".join(parts[-2:])


def same_site_blog_ids(blog: Any, all_blogs: Iterable[Any]) -> Set[int]:
    """이 블로그와 **같은 등록 도메인**을 쓰는 다른 블로그 ID들."""
    domain = registrable_domain(getattr(blog, "url", None))
    if not domain:
        return set()
    me = getattr(blog, "id", None)
    return {
        b.id for b in all_blogs
        if getattr(b, "id", None) != me
        and registrable_domain(getattr(b, "url", None)) == domain
    }


def module_linked_blog_ids(module: Any, blog: Any) -> Set[int]:
    """같은 모듈에 연결된 **다른** 블로그 ID들(공용 니치 모듈의 형제)."""
    from ..flow.module_blog_scope import resolve_module_blog_ids

    ids = resolve_module_blog_ids(module)
    me = getattr(blog, "id", None)
    return {i for i in ids if i != me}


def resolve_sibling_blog_ids(
    blog: Any,
    all_blogs: Iterable[Any],
    module: Any = None,
) -> List[int]:
    """제목 후보에서 제외할 형제 블로그 ID 목록(정렬)."""
    siblings = same_site_blog_ids(blog, all_blogs)
    if module is not None:
        siblings |= module_linked_blog_ids(module, blog)
    return sorted(siblings)
