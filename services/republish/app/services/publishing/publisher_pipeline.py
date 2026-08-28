"""
발행 파이프라인 오케스트레이터

이미지 업로드 → HTML 주입 → 플랫폼 발행 → 상태 갱신
전체 발행 워크플로우를 통합 관리합니다.

설계 문서: publish_module_implementation_plan.md - Phase 4
"""
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog, BlogPlatform
from ...models.crawled_post import CrawledPost
from ...models.google_credential import GoogleCredential
from ..generation.inventory_manager import InventoryManager
from .image_uploader import ImageUploader
from .html_injector import HtmlInjector
from .wordpress_publisher import WordPressPublisher
from .blogger_publisher import BloggerPublisher
from .publish_result import PublishResult, ImageUploadResult
from .thin_content_gate import check_thin_content
from .topic_dedup_gate import check_topic_duplicate
from .image_path_utils import resolve_image_path, strip_local_image_url
from . import faq_schema

logger = get_logger("publisher_pipeline", "app.log")


class PublisherPipeline:
    """
    발행 전체 파이프라인 오케스트레이터

    단계:
    1. 이미지 업로드 (이미지 존재 시)
    2. HTML 이미지 URL 주입
    3. 플랫폼별 발행 (WordPress/Blogger)
    4. CrawledPost 상태 갱신 (InventoryManager)

    Args:
        db: SQLAlchemy 비동기 세션
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.image_uploader = ImageUploader()
        self.html_injector = HtmlInjector()
        self.wp_publisher = WordPressPublisher()
        self.blogger_publisher = BloggerPublisher()
        self.inventory_manager = InventoryManager(db)

    async def publish_post(
        self,
        blog: Blog,
        crawled_post: CrawledPost,
        credential: Optional[GoogleCredential] = None,
    ) -> PublishResult:
        """
        단일 포스트 발행 파이프라인

        Args:
            blog: 대상 블로그
            crawled_post: 발행할 CrawledPost
            credential: Google 인증 (Blogger용)

        Returns:
            PublishResult
        """
        platform = blog.platform.value if isinstance(
            blog.platform, BlogPlatform
        ) else str(blog.platform)
        result = PublishResult(success=False, platform=platform)

        logger.info(
            "[PIPELINE] 발행 시작 | blog=%s | post_id=%d | "
            "title='%s' | platform=%s",
            blog.name, crawled_post.id,
            crawled_post.title[:30], platform,
        )

        # Step 1: 대표이미지 업로드
        image_result = await self._upload_image(
            blog, crawled_post
        )

        # Step 1.5: 대표이미지 업로드 실패 시 발행 중단
        # (이미지 없는 발행 금지 — imgbb 키 미설정 등)
        if image_result is not None and not image_result.success:
            error_msg = (
                "대표이미지 업로드 실패로 발행을 중단합니다: "
                f"{image_result.error}"
            )
            return await self._reject_pre_publish(
                blog, crawled_post, result, error_msg,
                retryable=image_result.retryable,
                log_reason="이미지 실패",
            )

        # Step 2: HTML 가공
        final_html = self._prepare_html(
            blog, crawled_post, image_result
        )

        # Step 2.5: 본문 내 로컬 이미지 업로드 및 URL 치환
        final_html = await self._upload_inline_images(
            blog, final_html, post_title=crawled_post.title,
        )

        if image_result and image_result.success:
            result.image_uploaded = True
            result.image_url = image_result.platform_url

        # Step 2.7: SEO 메타 로드 (WordPress만)
        seo_meta = None
        seo_plugin = None
        if blog.platform == BlogPlatform.WORDPRESS:
            seo_config = blog.seo_config or {}
            if (
                seo_config.get("auto_seo_enabled")
                and seo_config.get("detected_plugin")
            ):
                seo_meta = crawled_post.seo_meta
                seo_plugin = seo_config["detected_plugin"]
                logger.info(
                    "[PIPELINE] SEO 로드 | blog=%s | "
                    "plugin=%s | seo_meta=%s",
                    blog.name, seo_plugin,
                    "있음" if seo_meta else "없음(NULL)",
                )
            else:
                logger.debug(
                    "[PIPELINE] SEO 비활성 | blog=%s | "
                    "enabled=%s | plugin=%s",
                    blog.name,
                    seo_config.get("auto_seo_enabled"),
                    seo_config.get("detected_plugin"),
                )

        # Step 2.8: 최소 분량 게이트 (F6, thin content 발행 차단)
        thin_content_error = check_thin_content(final_html)
        if thin_content_error is not None:
            return await self._reject_pre_publish(
                blog, crawled_post, result, thin_content_error,
                retryable=False, log_reason="분량 미달",
            )

        # Step 2.9: 발행 전 근접 중복 게이트 (F8, 주제 중복 발행 차단)
        dedup_error = await check_topic_duplicate(
            self.db, blog.id, crawled_post.title,
            exclude_post_id=crawled_post.id,
        )
        if dedup_error is not None:
            return await self._reject_pre_publish(
                blog, crawled_post, result, dedup_error,
                retryable=False, log_reason="주제 중복",
            )

        # Step 3: 플랫폼별 발행
        publish_result = await self._publish_to_platform(
            blog, crawled_post, final_html,
            image_result, credential,
            seo_meta=seo_meta,
            seo_plugin=seo_plugin,
        )

        if not publish_result.success:
            result.error = publish_result.error
            result.retry_count = publish_result.retry_count
            result.retryable = publish_result.retryable

            # 발행 실패 기록
            try:
                crawled_post.record_publish_failure(
                    publish_result.error or "Unknown error"
                )
                await self.db.commit()
            except Exception as e:
                logger.error(
                    "[PIPELINE] 발행 실패 기록 오류 | "
                    "post_id=%d | %s",
                    crawled_post.id, e,
                )

            logger.error(
                "[PIPELINE] 발행 실패 | blog=%s | post_id=%d "
                "| error=%s | attempts=%d/%d",
                blog.name, crawled_post.id, result.error,
                crawled_post.publish_attempts, 3,
            )
            return result

        # Step 4: 상태 갱신
        try:
            await self.inventory_manager.mark_as_published(
                crawled_post.id,
                published_url=publish_result.published_url,
                platform_post_id=publish_result.platform_post_id,
            )
            await self.db.commit()
        except Exception as e:
            logger.error(
                "[PIPELINE] 상태 갱신 실패 | post_id=%d | %s",
                crawled_post.id, e,
            )
            # 발행은 성공했으므로 결과는 성공으로 반환
            result.errors.append(f"상태 갱신 실패: {e}")

        result.success = True
        result.published_url = publish_result.published_url
        result.platform_post_id = (
            publish_result.platform_post_id
        )

        # 검색 노출 원장 기록 + IndexNow 제출(S1). 실패해도 발행 결과는 그대로다.
        await self._track_search_visibility(
            blog, crawled_post, result.published_url,
        )

        logger.info(
            "[PIPELINE] 발행 완료 | blog=%s | post_id=%d | "
            "url=%s | image=%s",
            blog.name, crawled_post.id,
            result.published_url,
            "업로드됨" if result.image_uploaded else "없음",
        )
        return result

    async def _track_search_visibility(
        self,
        blog: Blog,
        crawled_post: CrawledPost,
        published_url: Optional[str],
    ) -> None:
        """발행 URL을 검색 노출 원장에 남긴다(부가 작업, 실패 무시).

        Args:
            blog: 발행 대상 블로그
            crawled_post: 발행된 글
            published_url: 발행 결과 URL
        """
        if not published_url:
            return
        try:
            from .. import search_visibility as _sv  # noqa: F401  (패키지 로드)
            from ..search_visibility.tracker import track_published_url

            await track_published_url(
                self.db, blog, published_url,
                crawled_post_id=crawled_post.id,
                title=crawled_post.title,
            )
            await self.db.commit()
        except Exception as e:  # noqa: BLE001 — 발행 결과에 영향 없음
            logger.warning(
                "[PIPELINE] 검색 노출 기록 실패(무시) | post_id=%d | %s",
                crawled_post.id, e,
            )

    async def _reject_pre_publish(
        self,
        blog: Blog,
        crawled_post: CrawledPost,
        result: PublishResult,
        error_msg: str,
        retryable: bool,
        log_reason: str,
    ) -> PublishResult:
        """플랫폼 발행 시도 전 게이트에서 걸린 글을 실패로 기록하고 반환한다.

        Step 1.5(이미지 실패)·Step 2.8(분량 미달) 등 발행 전 검증
        게이트가 공통으로 사용하는 실패 처리 경로.
        """
        logger.error(
            "[PIPELINE] 발행 중단(%s) | blog=%s | post_id=%d | %s",
            log_reason, blog.name, crawled_post.id, error_msg,
        )
        try:
            crawled_post.record_publish_failure(error_msg)
            await self.db.commit()
        except Exception as e:
            logger.error(
                "[PIPELINE] 발행 실패 기록 오류 | post_id=%d | %s",
                crawled_post.id, e,
            )
        result.error = error_msg
        result.retryable = retryable
        return result

    async def publish_batch(
        self,
        blog: Blog,
        count: int = 1,
        credential: Optional[GoogleCredential] = None,
    ) -> list[PublishResult]:
        """
        배치 발행: InventoryManager에서 count만큼 선택 후 순차 발행

        Args:
            blog: 대상 블로그
            count: 발행할 글 수
            credential: Google 인증 (Blogger용)

        Returns:
            PublishResult 목록
        """
        results = []

        for i in range(count):
            post = await self.inventory_manager.get_post_for_publish(
                blog.id
            )
            if not post:
                logger.info(
                    "[PIPELINE] 발행 대상 없음 (재고 소진) | "
                    "blog=%s | published=%d/%d",
                    blog.name, i, count,
                )
                break

            result = await self.publish_post(
                blog, post, credential
            )
            results.append(result)

            if not result.success:
                logger.warning(
                    "[PIPELINE] 배치 발행 중단 | blog=%s | "
                    "published=%d/%d | error=%s",
                    blog.name, i, count, result.error,
                )
                break

        return results

    async def _upload_image(
        self,
        blog: Blog,
        post: CrawledPost,
    ) -> Optional[ImageUploadResult]:
        """대표이미지 업로드 (존재 시).

        Returns:
            - None: 발행할 대표이미지가 없는 글(image_url 미설정)
              → 정상 발행 진행
            - ImageUploadResult(success=True): 업로드 성공
            - ImageUploadResult(success=False): 업로드 실패
              → 호출 측에서 발행을 중단한다(이미지 없는 발행 금지).
        """
        if not post.image_url:
            return None

        image_path = resolve_image_path(
            post.image_url
        )
        if not image_path:
            msg = (
                "대표이미지 파일을 찾을 수 없음: "
                f"{post.image_url}"
            )
            logger.error(
                "[PIPELINE] %s | blog=%s", msg, blog.name,
            )
            return ImageUploadResult(
                success=False, error=msg, retryable=False,
            )

        result = await self.image_uploader.upload_image(
            blog, image_path, title=post.title,
        )

        if not result.success:
            logger.error(
                "[PIPELINE] 대표이미지 업로드 실패 | "
                "blog=%s | error=%s",
                blog.name, result.error,
            )

        return result

    def _prepare_html(
        self,
        blog: Blog,
        post: CrawledPost,
        image_result: Optional[ImageUploadResult],
    ) -> str:
        """HTML 가공: 이미지 주입"""
        final_html = post.content_html or ""

        if image_result and image_result.success:
            platform = blog.platform.value if isinstance(
                blog.platform, BlogPlatform
            ) else str(blog.platform)

            # 모든 플랫폼에서 HTML에 이미지 주입
            # (WordPress도 featured_media 대신 HTML 삽입 방식 사용)
            final_html = self.html_injector.inject_featured_image(
                html=final_html,
                image_url=image_result.platform_url,
                title=post.title,
                editor_type=getattr(
                    blog, "editor_type", "classic"
                ),
                media_id=image_result.media_id,
                platform=platform,
            )

        # A5: 본문에 FAQ 블록이 있으면 FAQPage JSON-LD 를 덧붙인다.
        # 가시 텍스트에서만 만들며, 없으면 아무것도 하지 않는다.
        final_html = faq_schema.inject(final_html)

        return final_html

    async def _publish_to_platform(
        self,
        blog: Blog,
        post: CrawledPost,
        final_html: str,
        image_result: Optional[ImageUploadResult],
        credential: Optional[GoogleCredential],
        seo_meta: dict | None = None,
        seo_plugin: str | None = None,
    ) -> PublishResult:
        """플랫폼별 발행"""
        if blog.platform == BlogPlatform.WORDPRESS:
            return await self.wp_publisher.publish(
                blog, post, final_html,
                seo_meta=seo_meta,
                seo_plugin=seo_plugin,
            )

        elif blog.platform == BlogPlatform.BLOGGER:
            return await self.blogger_publisher.publish(
                blog, post, final_html,
                credential=credential,
            )

        else:
            return PublishResult(
                success=False,
                platform=str(blog.platform),
                error=f"지원하지 않는 플랫폼: {blog.platform}",
            )

    async def _upload_inline_images(
        self, blog: Blog, html: str, post_title: str = "",
    ) -> str:
        """
        본문 내 로컬 이미지를 플랫폼에 업로드하고 URL 치환

        /static/generated/images/ 경로의 이미지를 찾아
        워드프레스/블로거에 업로드 후 플랫폼 URL로 치환합니다.
        업로드 실패 시 로컬 URL을 유지하여 발행을 중단하지 않습니다.

        Args:
            blog: 대상 블로그
            html: 본문 HTML
            post_title: 포스트 제목 (이미지 업로드 title용)

        Returns:
            이미지 URL이 치환된 HTML
        """
        if not html:
            return html

        pattern = (
            r'(?:src|href)=["\']'
            r'(/static/generated/images/[^"\']+)'
            r'["\']'
        )
        local_urls = set(re.findall(pattern, html))

        if not local_urls:
            return html

        logger.info(
            "[PIPELINE] 인라인 이미지 %d개 발견 | blog=%s",
            len(local_urls), blog.name,
        )

        for local_url in local_urls:
            image_path = resolve_image_path(local_url)
            if not image_path:
                html = strip_local_image_url(
                    html, local_url
                )
                logger.warning(
                    "[PIPELINE] 인라인 이미지 경로 미존재, "
                    "로컬 URL 제거: %s",
                    local_url,
                )
                continue

            try:
                result = await self.image_uploader.upload_image(
                    blog, image_path, title=post_title or "image",
                )
            except Exception as e:
                html = strip_local_image_url(
                    html, local_url
                )
                logger.error(
                    "[PIPELINE] 인라인 이미지 업로드 예외, "
                    "로컬 URL 제거: %s | %s", local_url, e,
                )
                continue

            if result.success and result.platform_url:
                html = html.replace(
                    local_url, result.platform_url
                )
                logger.info(
                    "[PIPELINE] 인라인 이미지 치환: %s → %s",
                    local_url[:40],
                    result.platform_url[:60],
                )
            else:
                html = strip_local_image_url(
                    html, local_url
                )
                logger.warning(
                    "[PIPELINE] 인라인 이미지 업로드 실패, "
                    "로컬 URL 제거: %s | error=%s",
                    local_url, result.error,
                )

        return html
