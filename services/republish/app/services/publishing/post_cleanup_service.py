"""발행글 정리 — 저품질 글을 비공개하거나 완전 삭제한다.

라이프인포 146개를 일회성 스크립트로 처리했는데, 같은 일이 12개 블로그에서
반복된다. 앱 기능으로 만든다.

안전장치가 핵심이다. 애드센스 승인 사이트에서 콘텐츠가 부족해지면 광고 게재가
중단될 수 있어, 잔존 글 수 하한 아래로는 지우지 않는다.

순서도: docs/flowcharts/post_cleanup.md
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ...core.logger import get_logger
from ...core.security import decrypt_data
from ...models.blog import Blog, BlogPlatform

logger = get_logger("post_cleanup", "app.log")

TIMEOUT = 30.0
PAGE_SIZE = 100

# 승인 사이트가 콘텐츠 부족으로 광고 중단되는 것을 막는 기본 하한
DEFAULT_MIN_REMAINING = 100

MODE_PRIVATE = "private"   # 되돌릴 수 있다
MODE_DELETE = "delete"     # 410 Gone — 되돌릴 수 없다

# 확인 가능한 사실이 글의 핵심인데 그 값을 AI 가 지어내는 유형.
# 「대한주택관리사협회 채용정보」의 연봉표가 창작이었다.
CATEGORIES: List[tuple] = [
    ("contact", "고객센터·연락처",
     r"고객센터|전화번호|상담(전화|번호)|콜센터|A/?S\s*센터|문의처"),
    ("voucher", "상품권·현금화",
     r"상품권|현금화|기프트카드|온누리|지역화폐|바우처|포인트\s*전환"),
    ("job", "구인구직·채용",
     r"구인|구직|채용|일자리|알바|아르바이트|교차로|취업\s*정보"),
    ("facility", "시설 운영정보",
     r"시간표|영업시간|운영시간|주차\s*(요금|비용|무료)|배차|입장료"),
]


@dataclass
class PostItem:
    """정리 대상 후보 글 하나."""

    post_id: str
    title: str
    url: str
    status: str
    body_len: int
    category: Optional[str] = None
    category_label: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id, "title": self.title, "url": self.url,
            "status": self.status, "body_len": self.body_len,
            "category": self.category, "category_label": self.category_label,
            "reason": self.reason,
        }


@dataclass
class CleanupPlan:
    """무엇을 왜 지울지. 실행 전에 사용자에게 보여준다."""

    total_posts: int = 0
    targets: List[PostItem] = field(default_factory=list)
    remaining: int = 0
    min_remaining: int = DEFAULT_MIN_REMAINING
    allowed: bool = True
    block_reason: str = ""
    by_category: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_posts": self.total_posts,
            "target_count": len(self.targets),
            "remaining": self.remaining,
            "min_remaining": self.min_remaining,
            "allowed": self.allowed,
            "block_reason": self.block_reason,
            "by_category": self.by_category,
            "targets": [t.to_dict() for t in self.targets],
        }


def classify(title: str) -> tuple:
    """제목으로 유형을 가른다. 해당 없으면 (None, None)."""
    for code, label, pattern in CATEGORIES:
        if re.search(pattern, title or ""):
            return code, label
    return None, None


def plain_len(html: str) -> int:
    """태그를 뺀 본문 길이."""
    import html as html_mod

    text = re.sub(r"<[^>]+>", "", html or "")
    return len(html_mod.unescape(text).strip())


def build_plan(
    posts: List[PostItem],
    *,
    categories: Optional[List[str]] = None,
    min_body_len: int = 0,
    min_remaining: int = DEFAULT_MIN_REMAINING,
) -> CleanupPlan:
    """대상을 고르고 하한을 검사한다(네트워크 없이 테스트 가능하도록 분리)."""
    plan = CleanupPlan(total_posts=len(posts), min_remaining=min_remaining)
    wanted = set(categories or [c[0] for c in CATEGORIES])

    for p in posts:
        reasons = []
        if p.category and p.category in wanted:
            reasons.append(p.category_label or p.category)
        if min_body_len and p.body_len < min_body_len:
            reasons.append(f"본문 {p.body_len}자")
        if reasons:
            p.reason = " · ".join(reasons)
            plan.targets.append(p)
            key = p.category_label or "본문 짧음"
            plan.by_category[key] = plan.by_category.get(key, 0) + 1

    plan.remaining = plan.total_posts - len(plan.targets)
    if plan.remaining < min_remaining:
        plan.allowed = False
        can = max(0, plan.total_posts - min_remaining)
        plan.block_reason = (
            f"{len(plan.targets)}개를 지우면 {plan.remaining}개만 남습니다. "
            f"하한 {min_remaining}개를 지키려면 최대 {can}개까지만 "
            f"정리할 수 있습니다"
        )
    return plan


class PostCleanupService:
    """플랫폼별 글 목록 수집과 정리 실행."""

    def __init__(self, blog: Blog):
        self.blog = blog

    # ── 인증 ──────────────────────────────────────────────
    def _wp_auth(self) -> Optional[str]:
        try:
            user = decrypt_data(self.blog.api_key_encrypted)
            pw = decrypt_data(self.blog.api_secret_encrypted)
            return base64.b64encode(f"{user}:{pw}".encode()).decode()
        except Exception as e:  # noqa: BLE001
            logger.error("[CLEANUP] 워드프레스 인증 실패 | %s", e)
            return None

    # ── 목록 수집 ──────────────────────────────────────────
    async def fetch_posts(self, limit: int = 2000) -> List[PostItem]:
        if self.blog.platform == BlogPlatform.WORDPRESS:
            return await self._fetch_wordpress(limit)
        return await self._fetch_blogger(limit)

    async def _fetch_wordpress(self, limit: int) -> List[PostItem]:
        base = self.blog.url.rstrip("/") + "/wp-json/wp/v2/posts"
        out: List[PostItem] = []
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for page in range(1, limit // PAGE_SIZE + 2):
                r = await client.get(base, params={
                    "per_page": PAGE_SIZE, "page": page, "status": "publish",
                    "_fields": "id,title,link,status,content",
                })
                if r.status_code != 200:
                    break
                rows = r.json()
                if not rows:
                    break
                for p in rows:
                    title = (p.get("title") or {}).get("rendered", "")
                    code, label = classify(title)
                    out.append(PostItem(
                        post_id=str(p["id"]), title=title,
                        url=p.get("link", ""), status=p.get("status", ""),
                        body_len=plain_len(
                            (p.get("content") or {}).get("rendered", "")),
                        category=code, category_label=label,
                    ))
                if len(out) >= limit:
                    break
        return out

    async def _fetch_blogger(self, limit: int) -> List[PostItem]:
        from .blogger_publisher import BloggerPublisher

        pub = BloggerPublisher()
        token = await pub._get_access_token(self.blog, None)
        if not token:
            logger.error("[CLEANUP] 블로거 인증 실패 | blog=%s", self.blog.name)
            return []
        blog_id = await pub._extract_blog_id(self.blog, token)
        if not blog_id:
            return []

        out: List[PostItem] = []
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts"
        params = {"maxResults": PAGE_SIZE, "fetchBodies": True}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            while len(out) < limit:
                r = await client.get(
                    url, params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if r.status_code != 200:
                    break
                data = r.json()
                for p in data.get("items", []):
                    title = p.get("title", "")
                    code, label = classify(title)
                    out.append(PostItem(
                        post_id=p["id"], title=title, url=p.get("url", ""),
                        status="live", body_len=plain_len(p.get("content", "")),
                        category=code, category_label=label,
                    ))
                token_next = data.get("nextPageToken")
                if not token_next:
                    break
                params["pageToken"] = token_next
        return out

    # ── 실행 ──────────────────────────────────────────────
    async def apply(
        self, targets: List[PostItem], mode: str = MODE_PRIVATE,
    ) -> Dict[str, Any]:
        """비공개 또는 완전삭제. 실패한 건은 따로 모아 돌려준다."""
        done, failed = 0, []
        if self.blog.platform == BlogPlatform.WORDPRESS:
            auth = self._wp_auth()
            if not auth:
                return {"done": 0, "failed": [], "error": "인증 실패"}
            base = self.blog.url.rstrip("/") + "/wp-json/wp/v2/posts"
            headers = {"Authorization": f"Basic {auth}",
                       "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                for t in targets:
                    try:
                        if mode == MODE_DELETE:
                            # force=true 라야 휴지통이 아니라 완전 삭제되고
                            # 410 Gone 이 된다. 404 보다 재크롤이 빨리 멈춘다.
                            r = await client.delete(
                                f"{base}/{t.post_id}",
                                params={"force": "true"}, headers=headers)
                        else:
                            r = await client.post(
                                f"{base}/{t.post_id}", headers=headers,
                                json={"status": "private"})
                        if r.status_code in (200, 201):
                            done += 1
                        else:
                            failed.append((t.post_id, r.status_code))
                    except Exception as e:  # noqa: BLE001
                        failed.append((t.post_id, str(e)[:60]))
        else:
            from .blogger_publisher import BloggerPublisher

            pub = BloggerPublisher()
            token = await pub._get_access_token(self.blog, None)
            blog_id = await pub._extract_blog_id(self.blog, token) if token else None
            if not blog_id:
                return {"done": 0, "failed": [], "error": "인증 실패"}
            base = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts"
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                for t in targets:
                    try:
                        if mode == MODE_DELETE:
                            r = await client.delete(
                                f"{base}/{t.post_id}", headers=headers)
                        else:
                            # 블로거는 private 이 없다. 초안으로 되돌린다.
                            r = await client.post(
                                f"{base}/{t.post_id}/revert", headers=headers)
                        if r.status_code in (200, 204, 404):
                            done += 1
                        else:
                            failed.append((t.post_id, r.status_code))
                    except Exception as e:  # noqa: BLE001
                        failed.append((t.post_id, str(e)[:60]))

        logger.info(
            "[CLEANUP] %s | mode=%s | 처리 %d건 / 실패 %d건",
            self.blog.name, mode, done, len(failed),
        )
        return {"done": done, "failed": failed}


def wordpress_post_id_from_url(url: str) -> Optional[str]:
    """워드프레스 글 URL 에서 숫자 ID 를 뽑는다.

    doooit082 계열은 /1998/ 처럼 글 번호를 URL 로 쓴다. 슬러그형 URL 이면
    None 을 돌려주고 호출자가 REST 검색으로 찾는다.
    """
    m = re.search(r"/(\d+)/?$", (url or "").rstrip("/") + "/")
    return m.group(1) if m else None


def slug_of(url: Optional[str]) -> str:
    """URL 마지막 조각(슬러그). 워드프레스 슬러그 조회에 쓴다."""
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


class PostDeleter:
    """정식제목에 매칭된 발행글을 URL 로 찾아 지운다.

    정리 서비스(PostCleanupService)는 플랫폼 전체를 훑어 대상을 고르지만,
    여기서는 사용자가 화면에서 고른 글만 지운다. 대상 선정은 사람이 한다.
    """

    def __init__(self, blog: Blog):
        self.blog = blog
        self._svc = PostCleanupService(blog)

    async def delete_by_urls(
        self, urls: List[str], mode: str = MODE_DELETE,
    ) -> Dict[str, Any]:
        """URL 목록으로 삭제한다. 실패한 것은 이유와 함께 돌려준다."""
        if self.blog.platform == BlogPlatform.WORDPRESS:
            return await self._delete_wordpress(urls, mode)
        return await self._delete_blogger(urls, mode)

    async def _delete_wordpress(self, urls, mode) -> Dict[str, Any]:
        """워드프레스 삭제.

        **이미 없는 글은 실패가 아니다.** 원하는 상태(글이 블로그에 없음)가
        이미 이루어진 것이므로 done 으로 센다. 실패로 두면 우리 기록만 영영
        남아 내부링크가 사라진 글을 가리킨다.
        """
        auth = self._svc._wp_auth()
        if not auth:
            return {"done": 0, "failed": [{"url": u, "error": "인증 실패"}
                                          for u in urls], "already_gone": 0}
        base = self.blog.url.rstrip("/") + "/wp-json/wp/v2/posts"
        headers = {"Authorization": f"Basic {auth}",
                   "Content-Type": "application/json"}
        done, failed, gone = 0, [], 0
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for url in urls:
                pid = wordpress_post_id_from_url(url)
                if not pid:
                    # 슬러그형 URL — 슬러그로 찾는다.
                    # 조회 자체가 실패한 것과, 조회는 됐는데 글이 없는 것을
                    # 구분한다. 뭉뚱그리면 이미 지운 글이 영영 안 지워진다.
                    try:
                        r = await client.get(base, params={
                            "slug": slug_of(url), "_fields": "id"},
                            headers=headers)
                    except Exception as e:  # noqa: BLE001
                        failed.append({"url": url, "error": str(e)[:60]})
                        continue
                    if r.status_code != 200:
                        failed.append({"url": url,
                                       "error": f"조회 실패 {r.status_code}"})
                        continue
                    rows = r.json() or []
                    if not rows:
                        gone += 1          # 이미 없다
                        continue
                    pid = str(rows[0]["id"])
                try:
                    if mode == MODE_DELETE:
                        r = await client.delete(
                            f"{base}/{pid}", params={"force": "true"},
                            headers=headers)
                    else:
                        r = await client.post(
                            f"{base}/{pid}", headers=headers,
                            json={"status": "private"})
                    if r.status_code in (200, 201):
                        done += 1
                    elif r.status_code in (404, 410):
                        gone += 1          # 이미 없다
                    else:
                        failed.append({"url": url,
                                       "error": f"HTTP {r.status_code}"})
                except Exception as e:  # noqa: BLE001
                    failed.append({"url": url, "error": str(e)[:60]})
        return {"done": done + gone, "failed": failed, "already_gone": gone}

    async def _delete_blogger(self, urls, mode) -> Dict[str, Any]:
        """블로거 삭제.

        블로거는 URL 로 바로 지울 수 없어 path 로 postId 를 먼저 찾는다.
        **이미 지운 글은 이 조회가 404 라 삭제 단계에 닿지도 못한다.**
        그것을 실패로 두면 우리 기록만 남아 다음 크롤링까지 발행완료로
        보이고, 내부링크가 사라진 글을 가리킨다.
        """
        from .blogger_publisher import BloggerPublisher

        pub = BloggerPublisher()
        token = await pub._get_access_token(self.blog, None)
        blog_id = await pub._extract_blog_id(self.blog, token) if token else None
        if not blog_id:
            return {"done": 0, "failed": [{"url": u, "error": "인증 실패"}
                                          for u in urls], "already_gone": 0}

        api = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}"
        headers = {"Authorization": f"Bearer {token}"}
        done, failed, gone = 0, [], 0
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for url in urls:
                path = re.sub(r"^https?://[^/]+", "", url or "")
                try:
                    r = await client.get(
                        f"{api}/posts/bypath", params={"path": path},
                        headers=headers)
                except Exception as e:  # noqa: BLE001
                    failed.append({"url": url, "error": str(e)[:60]})
                    continue
                if r.status_code == 404:
                    gone += 1              # 이미 없다
                    continue
                if r.status_code != 200:
                    failed.append({"url": url,
                                   "error": f"조회 실패 {r.status_code}"})
                    continue
                pid = (r.json() or {}).get("id")
                if not pid:
                    gone += 1
                    continue

                try:
                    if mode == MODE_DELETE:
                        r = await client.delete(
                            f"{api}/posts/{pid}", headers=headers)
                    else:
                        r = await client.post(
                            f"{api}/posts/{pid}/revert", headers=headers)
                    if r.status_code in (200, 204):
                        done += 1
                    elif r.status_code == 404:
                        gone += 1
                    else:
                        failed.append({"url": url,
                                       "error": f"HTTP {r.status_code}"})
                except Exception as e:  # noqa: BLE001
                    failed.append({"url": url, "error": str(e)[:60]})
        return {"done": done + gone, "failed": failed, "already_gone": gone}
