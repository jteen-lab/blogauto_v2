"""
SEO 플러그인 자동 감지 서비스

WordPress REST API 루트(/wp-json/)의 namespaces를 확인하여
설치된 SEO 플러그인을 감지합니다.
인증 불필요 (공개 엔드포인트).
"""
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# 플러그인별 SEO 메타 키 (쓰기 가능 여부 프로브에 사용)
# 이 키들이 인증 REST 응답의 meta에 노출되면 register_post_meta(show_in_rest)로
# 등록된 것 → REST 쓰기 가능(= mu-plugin 설치됨). aioseo는 자체 REST 사용.
PLUGIN_META_KEYS: Dict[str, List[str]] = {
    "yoast": ["_yoast_wpseo_focuskw", "_yoast_wpseo_metadesc"],
    "rankmath": ["rank_math_focus_keyword", "rank_math_description"],
    "seopress": ["_seopress_analysis_target_kw", "_seopress_titles_desc"],
}

WRITE_PROBE_TIMEOUT = 12.0

# 감지 우선순위 (네임스페이스 -> 플러그인명)
PLUGIN_NAMESPACES = {
    "yoast/v1": "yoast",
    "rankmath/v1": "rankmath",
    "aioseo/v1": "aioseo",
    "seopress/v1": "seopress",
}

# 플러그인 표시명
PLUGIN_DISPLAY_NAMES = {
    "yoast": "Yoast SEO",
    "rankmath": "Rank Math",
    "aioseo": "All in One SEO",
    "seopress": "SEOPress",
}

DETECT_TIMEOUT = 10.0


class SEODetector:
    """WordPress SEO 플러그인 자동 감지"""

    async def detect(self, blog_url: str) -> Dict[str, Optional[str]]:
        """
        /wp-json/ 루트를 호출하여 SEO 플러그인을 감지합니다.

        Args:
            blog_url: 블로그 URL

        Returns:
            감지 결과 딕셔너리
            - detected_plugin: 감지된 플러그인 코드명 또는 None
            - detected_at: ISO 8601 감지 시각 또는 None
            - display_name: 플러그인 표시명 또는 None
        """
        api_url = f"{blog_url.rstrip('/')}/wp-json/"

        try:
            async with httpx.AsyncClient(timeout=DETECT_TIMEOUT) as client:
                resp = await client.get(api_url)

            if resp.status_code != 200:
                logger.warning(
                    "[SEO_DETECT] wp-json 응답 실패 | url=%s | status=%d",
                    blog_url, resp.status_code,
                )
                return {"detected_plugin": None, "detected_at": None, "display_name": None}

            data = resp.json()
            namespaces = data.get("namespaces", [])

            for ns, plugin_name in PLUGIN_NAMESPACES.items():
                if ns in namespaces:
                    detected_at = datetime.now(timezone.utc).isoformat()
                    logger.info(
                        "[SEO_DETECT] 플러그인 감지 | url=%s | plugin=%s",
                        blog_url, plugin_name,
                    )
                    return {
                        "detected_plugin": plugin_name,
                        "detected_at": detected_at,
                        "display_name": PLUGIN_DISPLAY_NAMES.get(
                            plugin_name, plugin_name
                        ),
                    }

            logger.info(
                "[SEO_DETECT] SEO 플러그인 미감지 | url=%s", blog_url,
            )
            return {"detected_plugin": None, "detected_at": None, "display_name": None}

        except Exception as e:
            logger.warning(
                "[SEO_DETECT] 감지 실패 | url=%s | error=%s",
                blog_url, e,
            )
            return {
                "detected_plugin": None,
                "detected_at": None,
                "display_name": None,
            }

    async def check_write_capability(
        self, blog_url: str, username: Optional[str],
        app_password: Optional[str], plugin: Optional[str],
    ) -> Dict[str, Optional[object]]:
        """SEO 메타를 실제로 발행 시 쓸 수 있는지 프로브한다.

        플러그인 감지만으로는 자동입력 성공을 보장하지 못한다(사이트가 xmlrpc를
        차단하고 SEO 메타를 REST에 등록하지 않으면 쓰기가 조용히 무시됨).
        - aioseo: 자체 REST namespace 사용 → 감지되면 가능으로 간주.
        - yoast/rankmath/seopress: 인증 REST로 메타 노출(등록) 확인 → 'rest'.
          미등록이면 xmlrpc 가용 확인 → 'xmlrpc'. 둘 다 불가면 capable=False.

        Returns:
            {seo_write_capable: bool|None, seo_write_method: str|None,
             seo_write_checked_at: iso}
        """
        checked_at = datetime.now(timezone.utc).isoformat()
        base = {
            "seo_write_capable": None,
            "seo_write_method": None,
            "seo_write_checked_at": checked_at,
        }
        if not plugin:
            return base
        if plugin == "aioseo":
            return {**base, "seo_write_capable": True, "seo_write_method": "aioseo"}

        keys = PLUGIN_META_KEYS.get(plugin, [])
        if keys and username and app_password:
            rest_ok = await self._probe_rest_meta(
                blog_url, username, app_password, keys,
            )
            if rest_ok:
                return {**base, "seo_write_capable": True, "seo_write_method": "rest"}

        xmlrpc_ok = await self._probe_xmlrpc(blog_url)
        if xmlrpc_ok:
            return {**base, "seo_write_capable": True, "seo_write_method": "xmlrpc"}

        return {**base, "seo_write_capable": False, "seo_write_method": None}

    async def _probe_rest_meta(
        self, blog_url: str, username: str,
        app_password: str, keys: List[str],
    ) -> bool:
        """인증 REST로 최근 글의 meta에 SEO 키가 노출되는지 확인.

        show_in_rest 로 등록된 메타만 응답에 포함되므로, 키가 보이면
        REST 쓰기가 가능한 것(mu-plugin 또는 등록 스니펫 존재).
        """
        api = (
            f"{blog_url.rstrip('/')}/wp-json/wp/v2/posts"
            "?per_page=1&_fields=id,meta"
        )
        auth = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()
        try:
            async with httpx.AsyncClient(timeout=WRITE_PROBE_TIMEOUT) as c:
                r = await c.get(
                    api, headers={"Authorization": f"Basic {auth}"},
                )
            if r.status_code != 200:
                return False
            items = r.json()
            if not items:
                # 글이 없으면 판정 불가 → 스키마로 폴백(등록 여부는 알 수 없어 False)
                return False
            meta = items[0].get("meta") or {}
            return all(k in meta for k in keys)
        except Exception as e:
            logger.warning(
                "[SEO_DETECT] REST 메타 프로브 실패 | url=%s | %s",
                blog_url, e,
            )
            return False

    async def _probe_xmlrpc(self, blog_url: str) -> bool:
        """xmlrpc.php가 살아있는지 demo.sayHello로 확인(인증 불필요)."""
        url = f"{blog_url.rstrip('/')}/xmlrpc.php"
        body = (
            '<?xml version="1.0"?><methodCall>'
            "<methodName>demo.sayHello</methodName>"
            "<params></params></methodCall>"
        )
        try:
            async with httpx.AsyncClient(timeout=WRITE_PROBE_TIMEOUT) as c:
                r = await c.post(
                    url, content=body.encode(),
                    headers={"Content-Type": "text/xml"},
                )
            return r.status_code == 200 and "Hello" in r.text
        except Exception:
            return False

