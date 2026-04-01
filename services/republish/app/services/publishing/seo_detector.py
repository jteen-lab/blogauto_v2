"""
SEO 플러그인 자동 감지 서비스

WordPress REST API 루트(/wp-json/)의 namespaces를 확인하여
설치된 SEO 플러그인을 감지합니다.
인증 불필요 (공개 엔드포인트).
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

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

