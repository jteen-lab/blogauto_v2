"""
이미지 업로드 서비스

플랫폼별 이미지 업로드를 처리합니다.
- WordPress: wp/v2/media REST API
- Blogger: imgbb 외부 호스팅

설계 문서: publish_module_implementation_plan.md - Phase 1
"""
import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from ...models.blog import Blog, BlogPlatform
from ...core.encryption import decrypt_api_key
from ...core.logger import get_logger
from .publish_result import ImageUploadResult

logger = get_logger("image_uploader", "app.log")

# 이미지 최적화 설정
MAX_IMAGE_WIDTH = 1200
WEBP_QUALITY = 85
UPLOAD_TIMEOUT = 30.0


class ImageUploader:
    """
    플랫폼별 이미지 업로드 라우터

    WordPress: 미디어 라이브러리 직접 업로드 (wp/v2/media)
    Blogger: imgbb 외부 호스팅 후 URL 참조
    """

    async def upload_image(
        self,
        blog: Blog,
        image_path: str,
        title: str = "",
    ) -> ImageUploadResult:
        """
        블로그 플랫폼에 따라 이미지를 업로드합니다.

        Args:
            blog: 대상 블로그
            image_path: 로컬 이미지 파일 경로
            title: 이미지 alt 텍스트

        Returns:
            ImageUploadResult
        """
        path = Path(image_path)
        if not path.exists():
            logger.warning(
                "[IMG_UPLOAD] 이미지 파일 없음: %s", image_path
            )
            return ImageUploadResult(
                success=False, error=f"파일 없음: {image_path}"
            )

        try:
            optimized = self._optimize_image(path)
        except Exception as e:
            logger.error("[IMG_UPLOAD] 이미지 최적화 실패: %s", e)
            return ImageUploadResult(
                success=False, error=f"이미지 최적화 실패: {e}"
            )

        if blog.platform == BlogPlatform.WORDPRESS:
            return await self._upload_wordpress(
                blog, optimized, title
            )
        elif blog.platform == BlogPlatform.BLOGGER:
            return await self._upload_imgbb(
                blog, optimized, title
            )
        else:
            return ImageUploadResult(
                success=False,
                error=f"지원하지 않는 플랫폼: {blog.platform}",
            )

    @staticmethod
    def _safe_filename(title: str) -> str:
        """
        ASCII 안전 파일명 생성

        한글 등 비ASCII 문자가 Content-Disposition 헤더에 포함되면
        인코딩 오류가 발생하므로, ASCII 문자만 사용합니다.

        Args:
            title: 원본 제목

        Returns:
            ASCII 안전 파일명 (예: blogauto_a1b2c3d4.webp)
        """
        # 영문/숫자만 추출
        ascii_part = re.sub(r'[^a-zA-Z0-9]', '', title)[:20]
        # 제목 해시로 고유성 보장
        title_hash = hashlib.md5(title.encode()).hexdigest()[:8]

        if ascii_part:
            return f"blogauto_{ascii_part}_{title_hash}.webp"
        return f"blogauto_{title_hash}.webp"

    def _optimize_image(self, path: Path) -> bytes:
        """
        이미지 최적화: WebP 변환 + 리사이징 + EXIF 제거

        Args:
            path: 원본 이미지 경로

        Returns:
            최적화된 이미지 바이트
        """
        with Image.open(path) as img:
            # EXIF 제거 (RGB 변환)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # 리사이징 (너비 기준)
            if img.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / img.width
                new_height = int(img.height * ratio)
                img = img.resize(
                    (MAX_IMAGE_WIDTH, new_height),
                    Image.LANCZOS,
                )

            buf = BytesIO()
            img.save(buf, format="WEBP", quality=WEBP_QUALITY)
            return buf.getvalue()

    async def _upload_wordpress(
        self,
        blog: Blog,
        image_data: bytes,
        title: str,
    ) -> ImageUploadResult:
        """
        WordPress REST API로 이미지 업로드

        API: POST {blog_url}/wp-json/wp/v2/media
        Auth: Basic (username:app_password)
        """
        api_url = f"{blog.url.rstrip('/')}/wp-json/wp/v2/media"

        try:
            username = decrypt_api_key(blog.api_key_encrypted)
            app_password = decrypt_api_key(blog.api_secret_encrypted)
        except Exception as e:
            return ImageUploadResult(
                success=False,
                error=f"API 인증 정보 복호화 실패: {e}",
                retryable=False,
            )

        auth_str = base64.b64encode(
            f"{username}:{app_password}".encode()
        ).decode()

        filename = self._safe_filename(title)

        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
            try:
                resp = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Basic {auth_str}",
                        "Content-Disposition": (
                            f'attachment; filename="{filename}"'
                        ),
                        "Content-Type": "image/webp",
                    },
                    content=image_data,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    media_id = data.get("id", 0)
                    logger.info(
                        "[IMG_UPLOAD] WordPress 업로드 성공 | "
                        "blog=%s | media_id=%d",
                        blog.name, media_id,
                    )

                    # 메타데이터 업데이트 (title, alt_text, caption, description)
                    if media_id and title:
                        await self._update_wordpress_meta(
                            client, blog.url, auth_str,
                            media_id, title,
                        )

                    return ImageUploadResult(
                        success=True,
                        platform_url=data.get("source_url", ""),
                        media_id=media_id,
                        width=data.get("media_details", {})
                        .get("width"),
                        height=data.get("media_details", {})
                        .get("height"),
                    )
                else:
                    error_msg = resp.text[:200]
                    logger.error(
                        "[IMG_UPLOAD] WordPress 업로드 실패 | "
                        "status=%d | error=%s",
                        resp.status_code, error_msg,
                    )
                    return ImageUploadResult(
                        success=False,
                        error=f"HTTP {resp.status_code}: {error_msg}",
                    )

            except httpx.TimeoutException:
                return ImageUploadResult(
                    success=False, error="WordPress 업로드 타임아웃"
                )
            except Exception as e:
                return ImageUploadResult(
                    success=False, error=f"WordPress 업로드 오류: {e}"
                )

    @staticmethod
    async def _update_wordpress_meta(
        client: httpx.AsyncClient,
        blog_url: str,
        auth_str: str,
        media_id: int,
        title: str,
    ) -> None:
        """
        WordPress 미디어 메타데이터를 포스트 제목으로 업데이트합니다.

        업데이트 실패해도 이미지 업로드 자체는 성공으로 처리됩니다.

        Args:
            client: httpx 비동기 클라이언트
            blog_url: 블로그 URL
            auth_str: Base64 인코딩된 인증 문자열
            media_id: 업로드된 미디어 ID
            title: 포스트 제목 (메타데이터 값으로 사용)
        """
        meta_url = (
            f"{blog_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
        )
        try:
            meta_resp = await client.post(
                meta_url,
                headers={
                    "Authorization": f"Basic {auth_str}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": title,
                    "alt_text": title,
                    "caption": title,
                    "description": title,
                },
            )
            if meta_resp.status_code in (200, 201):
                logger.info(
                    "[IMG_UPLOAD] 메타데이터 업데이트 성공 | "
                    "media_id=%d", media_id,
                )
            else:
                logger.warning(
                    "[IMG_UPLOAD] 메타데이터 업데이트 실패 | "
                    "media_id=%d | status=%d | error=%s",
                    media_id, meta_resp.status_code,
                    meta_resp.text[:200],
                )
        except Exception as e:
            logger.warning(
                "[IMG_UPLOAD] 메타데이터 업데이트 오류 | "
                "media_id=%d | error=%s",
                media_id, e,
            )

    async def _upload_imgbb(
        self,
        blog: Blog,
        image_data: bytes,
        title: str,
    ) -> ImageUploadResult:
        """
        imgbb API로 이미지 업로드 (Blogger용 외부 호스팅)

        API: POST https://api.imgbb.com/1/upload
        Auth: API Key (query parameter)
        """
        # Blog.placeholders에서 imgbb API 키 조회
        placeholders = blog.placeholders or {}
        imgbb_config = placeholders.get("image_hosting", {})
        api_key = imgbb_config.get("imgbb_api_key", "")

        if not api_key:
            return ImageUploadResult(
                success=False,
                error="imgbb API 키가 설정되지 않았습니다. "
                "블로그 설정 > 치환자 > image_hosting.imgbb_api_key",
                retryable=False,
            )

        image_b64 = base64.b64encode(image_data).decode()

        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
            try:
                resp = await client.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        "key": api_key,
                        "image": image_b64,
                        "name": title[:50] if title else "blogauto",
                    },
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        img_data = data["data"]
                        logger.info(
                            "[IMG_UPLOAD] imgbb 업로드 성공 | "
                            "blog=%s | url=%s",
                            blog.name,
                            img_data.get("url", "")[:60],
                        )
                        return ImageUploadResult(
                            success=True,
                            platform_url=img_data.get("url", ""),
                            width=int(img_data.get("width", 0))
                            or None,
                            height=int(img_data.get("height", 0))
                            or None,
                        )

                error_msg = resp.text[:200]
                logger.error(
                    "[IMG_UPLOAD] imgbb 업로드 실패 | "
                    "status=%d | error=%s",
                    resp.status_code, error_msg,
                )
                return ImageUploadResult(
                    success=False,
                    error=f"imgbb HTTP {resp.status_code}: {error_msg}",
                )

            except httpx.TimeoutException:
                return ImageUploadResult(
                    success=False, error="imgbb 업로드 타임아웃"
                )
            except Exception as e:
                return ImageUploadResult(
                    success=False, error=f"imgbb 업로드 오류: {e}"
                )
