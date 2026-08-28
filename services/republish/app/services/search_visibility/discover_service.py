"""X5 — 구글 디스커버 준비도 점검.

디스커버 카드는 큰 이미지가 화면 절반 이상을 차지한다. 그래서 구글은 가로
1,200px 이상과 `max-image-preview:large` 허락을 함께 요구한다. 둘 중 하나라도
없으면 카드가 만들어지지 않는다.

원칙
    - 진단은 항상 가능, 강제는 옵트인(`discover_enabled`).
    - 항목마다 **누가 고칠 수 있는지**(앱/사용자)를 함께 돌려준다.
      코드로 못 하는 것을 할 수 있는 척하지 않는다.
    - 작은 이미지를 확대하지 않는다. 화질만 나빠진다.

설계: docs/flowcharts/discover_readiness.md
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ...core.logger import get_logger
from .config import load_config

logger = get_logger("discover", "app.log")

TIMEOUT = 25.0
HEAD_BYTES = 120000

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I,
)
MAX_PREVIEW_RE = re.compile(r"max-image-preview\s*:\s*large", re.I)
AUTHOR_SCHEMA_RE = re.compile(r'"@type"\s*:\s*"Person"', re.I)

# 조치 주체
BY_APP = "app"
BY_USER = "user"


@dataclass
class CheckItem:
    """점검 항목 1건."""

    key: str
    label: str
    passed: Optional[bool]
    owner: str
    detail: str = ""


@dataclass
class DiscoverReadiness:
    """블로그 1개의 디스커버 준비도."""

    enabled: bool
    min_width: int
    items: List[CheckItem] = field(default_factory=list)
    checked_url: Optional[str] = None
    error: Optional[str] = None

    @property
    def ready(self) -> bool:
        return bool(self.items) and all(i.passed for i in self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "min_width": self.min_width,
            "ready": self.ready,
            "checked_url": self.checked_url,
            "error": self.error,
            "items": [
                {
                    "key": i.key, "label": i.label, "passed": i.passed,
                    "owner": i.owner, "detail": i.detail,
                }
                for i in self.items
            ],
        }


def _image_size(raw: bytes) -> Optional[tuple[int, int]]:
    """이미지 바이트에서 (가로, 세로)를 읽는다. 실패하면 None."""
    try:
        from PIL import Image

        return Image.open(io.BytesIO(raw)).size
    except Exception:  # noqa: BLE001 — 포맷 미지원 등
        return None


def template_path(blog: Any) -> Optional[Path]:
    """블로그의 템플릿 이미지 경로. 설정이 없거나 파일이 없으면 None.

    경로 해석은 실제 생성에 쓰는 TemplateImageService 의 것을 그대로 재사용한다.
    여기서 따로 추측하면 생성 결과와 점검 결과가 어긋난다.
    """
    overlay = getattr(blog, "overlay_config", None) or {}
    raw = (overlay.get("template_image") or "").strip()
    if not raw:
        return None

    from ..generation.template_image_service import TemplateImageService

    resolved = TemplateImageService()._resolve_media_path(raw)
    return Path(resolved) if resolved else None


def check_template(blog: Any, min_width: int) -> CheckItem:
    """템플릿 원본 가로 폭을 검사한다(로컬 파일)."""
    mode = str(getattr(blog, "image_mode", "") or "")
    if mode != "template":
        return CheckItem(
            "template", "템플릿 원본 크기", None, BY_APP,
            f"이미지 모드가 '{mode or '미설정'}' 이라 템플릿 검사 대상이 아닙니다",
        )

    path = template_path(blog)
    if not path:
        return CheckItem(
            "template", "템플릿 원본 크기", False, BY_USER,
            "템플릿 이미지가 설정되어 있지 않습니다",
        )

    try:
        size = _image_size(path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        return CheckItem(
            "template", "템플릿 원본 크기", None, BY_USER, f"읽기 실패: {exc}",
        )

    if not size:
        return CheckItem(
            "template", "템플릿 원본 크기", None, BY_USER, "이미지 형식을 읽지 못했습니다",
        )

    width, height = size
    passed = width >= min_width
    detail = f"{width}×{height}"
    if not passed:
        detail += f" — 가로 {min_width}px 이상 필요 (권장 1600×900)"
    return CheckItem("template", "템플릿 원본 크기", passed, BY_USER, detail)


async def check_published(
    blog: Any, url: str, min_width: int,
) -> List[CheckItem]:
    """발행된 실물 페이지에서 디스커버 신호를 잰다."""
    platform = str(getattr(getattr(blog, "platform", None), "value", "") or "")
    items: List[CheckItem] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        page = await client.get(url)
        html = page.text[:HEAD_BYTES]

        # max-image-preview
        preview_owner = BY_USER if platform == "blogger" else BY_APP
        preview_detail = (
            "블로거는 테마 HTML의 <head>에 직접 넣어야 합니다"
            if platform == "blogger"
            else "SEO 플러그인이 처리합니다"
        )
        items.append(CheckItem(
            "max_preview", "이미지 크게 쓰기 허락(max-image-preview:large)",
            bool(MAX_PREVIEW_RE.search(html)), preview_owner, preview_detail,
        ))

        # og:image
        match = OG_IMAGE_RE.search(html)
        if not match:
            items.append(CheckItem(
                "og_image", "대표 이미지(og:image)", False, BY_USER,
                "페이지에 og:image 가 없습니다"
                + (" — 블로거 테마 설정을 확인하세요" if platform == "blogger" else ""),
            ))
        else:
            try:
                raw = (await client.get(match.group(1))).content
                size = _image_size(raw)
            except Exception as exc:  # noqa: BLE001
                size = None
                logger.debug("[DISCOVER] og:image 조회 실패 | %s", exc)

            if not size:
                items.append(CheckItem(
                    "og_image", "대표 이미지(og:image)", None, BY_USER,
                    "이미지를 읽지 못했습니다",
                ))
            else:
                width, height = size
                passed = width >= min_width
                detail = f"{width}×{height}"
                if not passed:
                    detail += f" — 가로 {min_width}px 이상 필요"
                items.append(CheckItem(
                    "og_image", "대표 이미지 크기", passed, BY_USER, detail,
                ))

        # 저자 신호
        profile = getattr(blog, "author_profile", None) or {}
        has_name = bool((profile.get("name") or "").strip())
        items.append(CheckItem(
            "author", "저자 정보",
            has_name or bool(AUTHOR_SCHEMA_RE.search(html)),
            BY_APP,
            "블로그 설정의 저자 프로필에 이름을 넣으면 본문에 자동 삽입됩니다"
            if not has_name else (profile.get("name") or ""),
        ))

    return items


async def check_blog(blog: Any, published_url: Optional[str]) -> DiscoverReadiness:
    """블로그 1개의 디스커버 준비도를 점검한다."""
    config = load_config(blog)
    min_width = int(config.get("discover_min_image_width") or 1200)
    result = DiscoverReadiness(
        enabled=bool(config.get("discover_enabled")), min_width=min_width,
    )
    result.items.append(check_template(blog, min_width))

    if not published_url:
        result.error = "발행된 글이 없어 실물 점검을 건너뜁니다"
        return result

    result.checked_url = published_url
    try:
        result.items.extend(await check_published(blog, published_url, min_width))
    except Exception as exc:  # noqa: BLE001
        result.error = f"발행 페이지 점검 실패: {exc}"
    return result
