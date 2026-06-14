"""
WordPress 발행 서비스 (REST API + XML-RPC)

2단계 발행: draft 생성 → SEO/ping 설정 → publish 전환
내부링크 핑백 차단: 자기 도메인 링크를 상대경로로 변환
"""
import asyncio
import base64
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from .publish_result import PublishResult
from .seo_meta_builder import SEOMetaBuilder

logger = get_logger("wordpress_publisher", "app.log")

# 재시도 설정
MAX_RETRIES = 3
BACKOFF_BASE = 2
PUBLISH_TIMEOUT = 30.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _strip_self_links(html: str, blog_url: str) -> str:
    """내부링크를 상대경로로 변환 (핑백 원천 차단)

    WordPress는 콘텐츠의 절대 URL에 대해 핑백을 전송합니다.
    자기 도메인 링크를 상대경로로 변환하면 핑백이 발생하지 않으며,
    브라우저는 상대경로를 자동으로 절대경로로 해석하므로
    링크 기능에는 영향이 없습니다.
    """
    if not html or not blog_url:
        return html
    parsed = urlparse(blog_url.rstrip('/'))
    # https://domain.com 와 http://domain.com 모두 처리
    patterns = [
        f"https://{parsed.netloc}",
        f"http://{parsed.netloc}",
    ]
    for prefix in patterns:
        html = html.replace(
            f'href="{prefix}/', 'href="/'
        )
        html = html.replace(
            f"href='{prefix}/", "href='/"
        )
    return html


def _build_xmlrpc_members(
    custom_fields: list, slug: str = "",
) -> str:
    """XML-RPC struct 멤버 생성"""
    parts = []
    if custom_fields:
        cf = "".join(
            "<value><struct>"
            f"<member><name>key</name>"
            f"<value><string>{f['key']}</string>"
            "</value></member>"
            f"<member><name>value</name>"
            f"<value><string>{f['value']}</string>"
            "</value></member></struct></value>"
            for f in custom_fields
        )
        parts.append(
            "<member><name>custom_fields</name>"
            f"<value><array><data>{cf}"
            "</data></array></value></member>"
        )
    if slug:
        parts.append(
            "<member><name>post_name</name>"
            f"<value><string>{slug}"
            "</string></value></member>"
        )
    parts.append(
        "<member><name>comment_status</name>"
        "<value><string>closed</string>"
        "</value></member>"
    )
    parts.append(
        "<member><name>ping_status</name>"
        "<value><string>closed</string>"
        "</value></member>"
    )
    return "".join(parts)


class WordPressPublisher:
    """WordPress REST API + XML-RPC 발행 (2단계: draft→publish)"""

    async def publish(
        self, blog: Blog, post: CrawledPost,
        final_html: str,
        seo_meta: dict | None = None,
        seo_plugin: str | None = None,
    ) -> PublishResult:
        """WordPress에 글을 발행합니다."""
        result = PublishResult(
            success=False, platform="wordpress"
        )

        try:
            username = decrypt_api_key(blog.api_key_encrypted)
            app_password = decrypt_api_key(
                blog.api_secret_encrypted
            )
        except Exception as e:
            result.error = f"API 인증 정보 복호화 실패: {e}"
            result.retryable = False
            logger.error(
                "[WP_PUBLISH] %s | blog=%s",
                result.error, blog.name,
            )
            return result

        auth_str = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()

        api_url = (
            f"{blog.url.rstrip('/')}/wp-json/wp/v2/posts"
        )

        payload = self._build_payload(
            post, final_html, blog, seo_meta, seo_plugin,
        )

        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._send_request(
                    api_url, auth_str, payload
                )

                if resp.status_code in (200, 201):
                    return await self._handle_success(
                        resp, result, blog,
                        username, app_password,
                        seo_meta, seo_plugin,
                    )

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    wait = BACKOFF_BASE ** attempt
                    result.retry_count = attempt + 1
                    logger.warning(
                        "[WP_PUBLISH] 재시도 | attempt=%d"
                        " | wait=%ds | status=%d",
                        attempt + 1, wait,
                        resp.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                result.error = (
                    f"HTTP {resp.status_code}: "
                    f"{self._parse_error(resp)}"
                )
                result.retryable = False
                logger.error(
                    "[WP_PUBLISH] 발행 실패 | blog=%s"
                    " | %s", blog.name, result.error,
                )
                return result

            except httpx.TimeoutException:
                result.error = "WordPress API 타임아웃"
                result.retry_count = attempt + 1
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(
                        BACKOFF_BASE ** attempt
                    )
                    continue
            except Exception as e:
                result.error = f"WordPress API 오류: {e}"
                logger.error(
                    "[WP_PUBLISH] 예외 | blog=%s | %s",
                    blog.name, e,
                )
                return result

        return result

    def _build_payload(
        self, post: CrawledPost, final_html: str,
        blog: Blog, seo_meta: dict | None,
        seo_plugin: str | None,
    ) -> dict:
        """WordPress REST API POST payload 구성

        1단계로 draft 생성 후 2단계에서 publish 전환.
        draft 상태에서 ping_status를 closed로 설정하면
        publish 전환 시 핑백이 발생하지 않습니다.
        """
        # 내부링크를 상대경로로 변환 (핑백 원천 차단)
        content = _strip_self_links(
            final_html, blog.url,
        )
        payload = {
            "title": post.title,
            "content": content,
            "status": "draft",
            "format": "standard",
            "comment_status": "closed",
            "ping_status": "closed",
        }
        if seo_meta:
            if seo_meta.get("slug"):
                payload["slug"] = seo_meta["slug"]
            if seo_plugin and seo_plugin != "aioseo":
                pm = SEOMetaBuilder.build_plugin_meta(
                    seo_plugin, seo_meta,
                )
                if pm:
                    payload["meta"] = pm
            logger.info(
                "[WP_PUBLISH] SEO payload | plugin=%s"
                " | slug='%s' | meta_keys=%s",
                seo_plugin,
                seo_meta.get("slug", "")[:40],
                list(payload.get("meta", {}).keys()),
            )
        categories = self._get_categories(blog)
        if categories:
            payload["categories"] = categories
        return payload

    async def _handle_success(
        self, resp: httpx.Response,
        result: PublishResult, blog: Blog,
        username: str, app_password: str,
        seo_meta: dict | None,
        seo_plugin: str | None,
    ) -> PublishResult:
        """draft 생성 후 SEO 설정 → publish 전환"""
        data = resp.json()
        post_id = str(data.get("id", ""))
        result.platform_post_id = post_id

        # SEO custom_fields 업데이트
        # XML-RPC 우선 시도 → 실패 시 REST API meta 업데이트로 fallback
        # (lifein4.com 등 보안 플러그인이 XML-RPC 차단한 사이트 호환)
        if seo_meta and seo_plugin and post_id:
            if seo_plugin == "aioseo":
                await self._post_aioseo_meta(
                    blog.url, username,
                    app_password, post_id, seo_meta,
                )
            else:
                xmlrpc_ok = await self._update_seo_via_xmlrpc(
                    blog.url, username,
                    app_password, post_id,
                    seo_meta, seo_plugin,
                )
                if not xmlrpc_ok:
                    # XML-RPC 차단 사이트용 REST API fallback
                    await self._update_seo_via_rest(
                        blog.url, username,
                        app_password, post_id,
                        seo_meta, seo_plugin,
                    )

        # 2단계: draft → publish 전환
        pub_ok = await self._publish_draft(
            blog.url, username, app_password, post_id,
        )
        if pub_ok:
            result.success = True
            result.published_url = pub_ok
        else:
            result.success = False
            result.error = "draft→publish 전환 실패"
            # draft가 이미 생성됨 → 재시도 시 중복 draft 발생하므로 영구 처리
            result.retryable = False

        logger.info(
            "[WP_PUBLISH] 발행 완료 | blog=%s | "
            "post_id=%s | seo=%s",
            blog.name, post_id,
            seo_plugin or "없음",
        )
        return result

    async def _publish_draft(
        self, blog_url: str, username: str,
        app_password: str, post_id: str,
    ) -> Optional[str]:
        """draft → publish 전환 (핑백 방지)"""
        url = (
            f"{blog_url.rstrip('/')}/wp-json/"
            f"wp/v2/posts/{post_id}"
        )
        auth = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()
        try:
            async with httpx.AsyncClient(
                timeout=PUBLISH_TIMEOUT,
            ) as client:
                resp = await client.post(
                    url, json={
                        "status": "publish",
                        "ping_status": "closed",
                        "comment_status": "closed",
                    },
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type":
                            "application/json"},
                )
            if resp.status_code in (200, 201):
                link = resp.json().get("link", "")
                logger.info(
                    "[WP_PUBLISH] draft→publish | "
                    "post_id=%s", post_id,
                )
                return link
            logger.warning(
                "[WP_PUBLISH] draft→publish 실패 | "
                "%s | %d", post_id, resp.status_code,
            )
        except Exception as e:
            logger.warning(
                "[WP_PUBLISH] draft→publish 오류 | "
                "%s | %s", post_id, e,
            )
        return None

    async def _update_seo_via_xmlrpc(
        self, blog_url: str, username: str,
        app_password: str, post_id: str,
        seo_meta: dict, seo_plugin: str,
    ) -> bool:
        """XML-RPC wp.editPost로 SEO 설정 (slug + custom_fields).

        Returns:
            True: 등록 성공, False: 실패(보안 플러그인 차단 등)
        """
        plugin_meta = SEOMetaBuilder.build_plugin_meta(
            seo_plugin, seo_meta,
        )
        custom_fields = [
            {"key": k, "value": v}
            for k, v in (plugin_meta or {}).items() if v
        ]
        slug = seo_meta.get("slug", "")
        if not custom_fields and not slug:
            return True  # 등록할 게 없으면 성공으로 간주
        xmlrpc_url = (
            f"{blog_url.rstrip('/')}/xmlrpc.php"
        )
        try:
            xml_body = self._build_xmlrpc_body(
                username, app_password,
                int(post_id), custom_fields,
                slug=slug,
            )
            ok = await self._send_xmlrpc(
                xmlrpc_url, xml_body,
            )
            keys = [f["key"] for f in custom_fields]
            if slug:
                keys.append("post_name(slug)")
            level = "info" if ok else "warning"
            msg = "성공" if ok else "실패"
            getattr(logger, level)(
                "[WP_PUBLISH] XML-RPC SEO %s | "
                "plugin=%s | post_id=%s | keys=%s",
                msg, seo_plugin, post_id, keys,
            )
            return ok
        except Exception as e:
            logger.warning(
                "[WP_PUBLISH] XML-RPC SEO 오류 | "
                "plugin=%s | post_id=%s | %s",
                seo_plugin, post_id, e,
            )
            return False

    async def _update_seo_via_rest(
        self, blog_url: str, username: str,
        app_password: str, post_id: str,
        seo_meta: dict, seo_plugin: str,
    ) -> bool:
        """REST API로 SEO meta 업데이트 (XML-RPC 차단 사이트용 fallback).

        WordPress REST API는 register_post_meta(show_in_rest=true)된
        meta 키만 받는다. Yoast/RankMath/SEOPress 메타는 보통 등록되어 있다.
        보안 플러그인이 XML-RPC를 차단해도 REST API는 통과되는 경우가 많다.

        Returns:
            True: 응답에 메타가 실제 저장됨, False: 실패 또는 무시됨
        """
        plugin_meta = SEOMetaBuilder.build_plugin_meta(
            seo_plugin, seo_meta,
        ) or {}
        slug = seo_meta.get("slug", "")
        if not plugin_meta and not slug:
            return True

        url = f"{blog_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
        auth = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()
        body: dict = {}
        if plugin_meta:
            body["meta"] = plugin_meta
        if slug:
            body["slug"] = slug

        try:
            async with httpx.AsyncClient(
                timeout=PUBLISH_TIMEOUT,
            ) as client:
                resp = await client.post(
                    url, json=body,
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code not in (200, 201):
                logger.warning(
                    "[WP_PUBLISH] REST SEO 실패 | "
                    "plugin=%s | post_id=%s | status=%d",
                    seo_plugin, post_id, resp.status_code,
                )
                return False
            # 응답에서 meta가 실제 저장되었는지 검증
            data = resp.json() if resp.content else {}
            saved_meta = data.get("meta") or {}
            registered = sum(
                1 for k, v in plugin_meta.items()
                if saved_meta.get(k) == v
            )
            ok = registered == len(plugin_meta) if plugin_meta else True
            level = "info" if ok else "warning"
            getattr(logger, level)(
                "[WP_PUBLISH] REST SEO %s | "
                "plugin=%s | post_id=%s | "
                "registered=%d/%d",
                "성공" if ok else "부분실패",
                seo_plugin, post_id,
                registered, len(plugin_meta),
            )
            return ok
        except Exception as e:
            logger.warning(
                "[WP_PUBLISH] REST SEO 오류 | "
                "plugin=%s | post_id=%s | %s",
                seo_plugin, post_id, e,
            )
            return False

    async def _send_xmlrpc(
        self, url: str, xml_body: str,
    ) -> bool:
        """httpx로 XML-RPC 요청 전송 (HTTP/2 호환)"""
        async with httpx.AsyncClient(
            timeout=PUBLISH_TIMEOUT,
        ) as client:
            resp = await client.post(
                url,
                content=xml_body.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; "
                    "charset=utf-8",
                },
            )
            body = resp.text
            if "<fault>" in body:
                logger.warning(
                    "[WP_PUBLISH] XML-RPC fault: %s",
                    body[:300],
                )
                return False
            return (
                resp.status_code == 200
                and "<boolean>1</boolean>" in body
            )

    @staticmethod
    def _build_xmlrpc_body(
        username: str, password: str,
        post_id: int, custom_fields: list,
        slug: str = "",
    ) -> str:
        """wp.editPost XML-RPC 요청 본문 생성"""
        members = _build_xmlrpc_members(
            custom_fields, slug,
        )
        return (
            '<?xml version="1.0"?>'
            "<methodCall>"
            "<methodName>wp.editPost</methodName>"
            "<params>"
            f"<param><value><int>0</int></value></param>"
            f"<param><value><string>{username}"
            "</string></value></param>"
            f"<param><value><string>{password}"
            "</string></value></param>"
            f"<param><value><int>{post_id}"
            "</int></value></param>"
            f"<param><value><struct>{members}"
            "</struct></value></param>"
            "</params></methodCall>"
        )

    async def _post_aioseo_meta(
        self, blog_url: str, username: str,
        app_password: str, post_id: str,
        seo_meta: dict,
    ) -> None:
        """AIOSEO 자체 REST API로 SEO 메타 설정"""
        url = f"{blog_url.rstrip('/')}/wp-json/aioseo/v1/posts/{post_id}"
        kp = seo_meta.get("focus_keyphrase", "")
        auth = base64.b64encode(f"{username}:{app_password}".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=PUBLISH_TIMEOUT) as client:
                resp = await client.post(
                    url, json={"title": kp, "description": seo_meta.get("meta_description", ""),
                               "keyphrases": {"focus": {"keyphrase": kp}}},
                    headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                )
            ok = resp.status_code in (200, 201)
            getattr(logger, "info" if ok else "warning")(
                "[WP_PUBLISH] AIOSEO %s | post_id=%s",
                "성공" if ok else f"실패({resp.status_code})", post_id,
            )
        except Exception as e:
            logger.warning("[WP_PUBLISH] AIOSEO 오류 | %s | %s", post_id, e)

    async def _send_request(
        self, api_url: str, auth_str: str,
        payload: dict,
    ) -> httpx.Response:
        """WordPress REST API POST 요청"""
        async with httpx.AsyncClient(
            timeout=PUBLISH_TIMEOUT,
        ) as client:
            return await client.post(
                api_url, json=payload, headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/json"},
            )

    @staticmethod
    def _get_categories(blog: Blog) -> list:
        """Blog.placeholders에서 WP 카테고리 ID 조회"""
        cats = (blog.placeholders or {}).get(
            "wp_categories", [],
        )
        return [int(c) for c in cats if str(c).isdigit()] if isinstance(cats, list) else []

    @staticmethod
    def _parse_error(resp: httpx.Response) -> str:
        """WordPress API 에러 파싱"""
        try:
            return resp.json().get("message", resp.text[:200])
        except Exception:
            return resp.text[:200]
