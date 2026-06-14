"""
발행(Publishing) 모듈 통합 테스트

대상: PublishResult, ImageUploadResult, HtmlInjector, ImageUploader,
WordPressPublisher, BloggerPublisher, PublisherPipeline
모든 외부 API 호출은 mock 처리됩니다.
"""
import sys
from unittest.mock import MagicMock as _MagicMock

# PIL(Pillow) 미설치 환경 대응
if "PIL" not in sys.modules:
    _pil_mock = _MagicMock()
    sys.modules["PIL"] = _pil_mock
    sys.modules["PIL.Image"] = _pil_mock.Image

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.publishing.publish_result import (
    PublishResult, ImageUploadResult,
)
from app.services.publishing.html_injector import HtmlInjector
from app.services.publishing.wordpress_publisher import WordPressPublisher
from app.services.publishing.blogger_publisher import BloggerPublisher
from app.services.publishing.publisher_pipeline import PublisherPipeline
from tests.fixtures.reference_collection_fixtures import create_mock_db_session

SAMPLE_HTML = "<h2>서론</h2><p>테스트 내용입니다.</p>"


# Mock 팩토리 -------------------------------------------------------

def create_mock_blog_for_publish(
    blog_id: int = 1, name: str = "테스트블로그",
    url: str = "https://test.wordpress.com", platform: str = "wordpress",
    api_key_encrypted: str = "enc_user", api_secret_encrypted: str = "enc_pass",
    placeholders: dict = None, editor_type: str = "classic",
) -> MagicMock:
    """발행 테스트용 Mock Blog"""
    from app.models.blog import BlogPlatform
    blog = MagicMock()
    blog.id = blog_id
    blog.name = name
    blog.url = url
    blog.platform = BlogPlatform(platform)
    blog.api_key_encrypted = api_key_encrypted
    blog.api_secret_encrypted = api_secret_encrypted
    blog.placeholders = placeholders or {}
    blog.editor_type = editor_type
    return blog


def create_mock_crawled_post(
    post_id: int = 1, title: str = "테스트 포스트 제목",
    content_html: str = "<h2>서론</h2><p>내용</p>", image_url: str = None,
) -> MagicMock:
    """발행 테스트용 Mock CrawledPost"""
    post = MagicMock()
    post.id = post_id
    post.blog_id = 1
    post.title = title
    post.content_html = content_html
    post.image_url = image_url
    post.source = "generated"
    return post


def create_mock_credential(access_token: str = "mock_token") -> MagicMock:
    """Google OAuth Mock"""
    cred = MagicMock()
    cred.get_access_token = MagicMock(return_value=access_token)
    return cred


def create_mock_httpx_response(
    status_code: int = 200, json_data: dict = None, text: str = "",
) -> MagicMock:
    """httpx.Response Mock"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json = MagicMock(return_value=json_data or {})
    return resp


# Fixtures -----------------------------------------------------------

@pytest.fixture
def mock_db():
    return create_mock_db_session()

@pytest.fixture
def wp_blog() -> MagicMock:
    return create_mock_blog_for_publish(platform="wordpress")

@pytest.fixture
def blogger_blog() -> MagicMock:
    return create_mock_blog_for_publish(
        blog_id=2, name="블로거블로그", url="https://test.blogspot.com",
        platform="blogger", placeholders={"blogger_id": "123456789"},
    )

@pytest.fixture
def sample_post() -> MagicMock:
    return create_mock_crawled_post()

@pytest.fixture
def sample_post_with_image() -> MagicMock:
    return create_mock_crawled_post(
        image_url="/static/generated/images/test.webp",
    )


# 1. 데이터클래스 ---------------------------------------------------

class TestPublishResultDataclasses:
    """PublishResult / ImageUploadResult 기본 생성 테스트"""

    def test_image_upload_result_defaults(self):
        """ImageUploadResult: success=True, Optional 필드는 None"""
        r = ImageUploadResult(success=True, platform_url="https://img.com/1.webp")
        assert r.success is True
        assert r.platform_url == "https://img.com/1.webp"
        assert r.media_id is None
        assert r.error is None

    def test_publish_result_defaults(self):
        """PublishResult: errors 빈 리스트, retry_count=0"""
        r = PublishResult(success=False, platform="wordpress")
        assert r.success is False
        assert r.errors == []
        assert r.retry_count == 0
        assert r.image_uploaded is False


# 2. HtmlInjector ---------------------------------------------------

class TestHtmlInjector:
    """에디터 타입별 이미지 주입 테스트"""

    def setup_method(self):
        self.inj = HtmlInjector()
        self.img = "https://cdn.example.com/img.webp"

    def test_classic_image_injection(self):
        """Classic: featured-image div 삽입"""
        result = self.inj.inject_featured_image(
            html=SAMPLE_HTML, image_url=self.img,
            title="테스트", editor_type="classic",
        )
        assert 'class="featured-image"' in result
        assert self.img in result
        assert result.endswith(SAMPLE_HTML)

    def test_gutenberg_image_injection(self):
        """Gutenberg: wp:image 블록 + media_id 클래스"""
        result = self.inj.inject_featured_image(
            html=SAMPLE_HTML, image_url=self.img,
            title="테스트", editor_type="gutenberg", media_id=42,
        )
        assert "<!-- wp:image" in result
        assert "wp-image-42" in result

    def test_blogger_image_injection(self):
        """Blogger: separator div + border=0"""
        result = self.inj.inject_featured_image(
            html=SAMPLE_HTML, image_url=self.img,
            title="테스트", platform="blogger",
        )
        assert 'class="separator"' in result
        assert 'border="0"' in result

    def test_no_image_returns_original(self):
        """image_url 빈 문자열이면 원본 HTML 그대로 반환"""
        result = self.inj.inject_featured_image(
            html=SAMPLE_HTML, image_url="", title="테스트",
        )
        assert result == SAMPLE_HTML

    def test_html_escape_in_title(self):
        """XSS 방지: HTML 특수문자 이스케이프"""
        result = self.inj.inject_featured_image(
            html=SAMPLE_HTML, image_url=self.img,
            title='<script>alert("xss")</script>',
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


# 3. WordPressPublisher ---------------------------------------------

class TestWordPressPublisher:
    """WordPress REST API 발행 테스트"""

    def setup_method(self):
        self.pub = WordPressPublisher()

    @pytest.mark.asyncio
    async def test_publish_success(self, wp_blog, sample_post):
        """201 응답 시 성공: published_url, platform_post_id 설정"""
        resp = create_mock_httpx_response(
            status_code=201,
            json_data={"id": 999, "link": "https://test.wordpress.com/post/999"},
        )
        self.pub._send_request = AsyncMock(return_value=resp)
        with patch(
            "app.services.publishing.wordpress_publisher.decrypt_api_key",
            return_value="decrypted",
        ):
            result = await self.pub.publish(wp_blog, sample_post, SAMPLE_HTML)
        assert result.success is True
        assert result.published_url == "https://test.wordpress.com/post/999"
        assert result.platform_post_id == "999"

    @pytest.mark.asyncio
    async def test_publish_retry_then_success(self, wp_blog, sample_post):
        """429 -> 재시도 -> 201 성공"""
        self.pub._send_request = AsyncMock(side_effect=[
            create_mock_httpx_response(status_code=429),
            create_mock_httpx_response(
                status_code=201, json_data={"id": 100, "link": "https://t.com/100"},
            ),
        ])
        with patch(
            "app.services.publishing.wordpress_publisher.decrypt_api_key",
            return_value="d",
        ), patch(
            "app.services.publishing.wordpress_publisher.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await self.pub.publish(wp_blog, sample_post, SAMPLE_HTML)
        assert result.success is True
        assert self.pub._send_request.call_count == 2

    @pytest.mark.asyncio
    async def test_publish_auth_failure(self, wp_blog, sample_post):
        """인증 복호화 실패 -> error에 '복호화' 포함"""
        with patch(
            "app.services.publishing.wordpress_publisher.decrypt_api_key",
            side_effect=Exception("복호화 실패"),
        ):
            result = await self.pub.publish(wp_blog, sample_post, SAMPLE_HTML)
        assert result.success is False
        assert "복호화" in result.error

    @pytest.mark.asyncio
    async def test_publish_non_retryable_error(self, wp_blog, sample_post):
        """403 -> 재시도 없이 즉시 실패"""
        self.pub._send_request = AsyncMock(
            return_value=create_mock_httpx_response(
                status_code=403, json_data={"message": "Forbidden"},
            ),
        )
        with patch(
            "app.services.publishing.wordpress_publisher.decrypt_api_key",
            return_value="d",
        ):
            result = await self.pub.publish(wp_blog, sample_post, SAMPLE_HTML)
        assert result.success is False
        assert "403" in result.error
        assert self.pub._send_request.call_count == 1


# 4. BloggerPublisher -----------------------------------------------

class TestBloggerPublisher:
    """Blogger API v3 발행 테스트"""

    def setup_method(self):
        self.pub = BloggerPublisher()

    @pytest.mark.asyncio
    async def test_publish_success(self, blogger_blog, sample_post):
        """201 응답 시 성공"""
        resp = create_mock_httpx_response(
            status_code=201,
            json_data={"id": "abc", "url": "https://test.blogspot.com/p.html"},
        )
        self.pub._send_request = AsyncMock(return_value=resp)
        result = await self.pub.publish(
            blogger_blog, sample_post, SAMPLE_HTML,
            credential=create_mock_credential(),
        )
        assert result.success is True
        assert result.platform == "blogger"
        assert "blogspot.com" in result.published_url

    @pytest.mark.asyncio
    async def test_publish_token_expired(self, blogger_blog, sample_post):
        """401 -> 토큰 만료 에러"""
        self.pub._send_request = AsyncMock(
            return_value=create_mock_httpx_response(status_code=401),
        )
        result = await self.pub.publish(
            blogger_blog, sample_post, SAMPLE_HTML,
            credential=create_mock_credential(),
        )
        assert result.success is False
        assert "토큰" in result.error

    @pytest.mark.asyncio
    async def test_publish_no_credential(self, blogger_blog, sample_post):
        """credential=None -> 인증 에러"""
        result = await self.pub.publish(
            blogger_blog, sample_post, SAMPLE_HTML, credential=None,
        )
        assert result.success is False
        assert "인증" in result.error

    def test_extract_blog_id_from_placeholders(self, blogger_blog):
        """placeholders.blogger_id에서 ID 추출"""
        assert self.pub._extract_blog_id(blogger_blog) == "123456789"

    def test_extract_blog_id_missing(self):
        """blogger_id 없으면 None"""
        blog = create_mock_blog_for_publish(
            platform="blogger", placeholders={}, api_key_encrypted=None,
        )
        assert self.pub._extract_blog_id(blog) is None


# 5. ImageUploader --------------------------------------------------

class TestImageUploader:
    """WordPress/imgbb 이미지 업로드 테스트"""

    @pytest.mark.asyncio
    async def test_wordpress_upload_success(self, wp_blog):
        """WordPress 미디어 업로드 201 -> media_id, platform_url 확인"""
        from app.services.publishing.image_uploader import ImageUploader
        up = ImageUploader()
        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(up, "_optimize_image", return_value=b"data"), \
             patch("app.services.publishing.image_uploader.decrypt_api_key",
                   return_value="d"), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=create_mock_httpx_response(
                       status_code=201,
                       json_data={"id": 55,
                                  "source_url": "https://t.com/img.webp",
                                  "media_details": {"width": 800, "height": 600}},
                   )):
            result = await up.upload_image(wp_blog, "/tmp/t.webp", title="t")
        assert result.success is True
        assert result.media_id == 55

    @pytest.mark.asyncio
    async def test_imgbb_upload_success(self, blogger_blog):
        """imgbb 200 -> platform_url에 ibb.co 포함"""
        from app.services.publishing.image_uploader import ImageUploader
        blogger_blog.placeholders = {
            "image_hosting": {"imgbb_api_key": "key"},
        }
        up = ImageUploader()
        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(up, "_optimize_image", return_value=b"data"), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=create_mock_httpx_response(
                       status_code=200,
                       json_data={"success": True, "data": {
                           "url": "https://i.ibb.co/abc/img.webp",
                           "width": "1200", "height": "800"}},
                   )):
            result = await up.upload_image(blogger_blog, "/tmp/t.webp", title="t")
        assert result.success is True
        assert "ibb.co" in result.platform_url


# 6. PublisherPipeline ----------------------------------------------

class TestPublisherPipeline:
    """전체 파이프라인 오케스트레이터 테스트"""

    def _build(self, mock_db, *, publish_ok: bool = True,
               image_result: ImageUploadResult = None) -> PublisherPipeline:
        """서브서비스를 mock으로 교체한 파이프라인 생성"""
        p = PublisherPipeline(mock_db)
        p.image_uploader.upload_image = AsyncMock(return_value=image_result)
        url = "https://test.com/p/1" if publish_ok else None
        err = None if publish_ok else "발행 실패"
        p.wp_publisher.publish = AsyncMock(return_value=PublishResult(
            success=publish_ok, platform="wordpress",
            published_url=url, platform_post_id="999" if publish_ok else None,
            error=err,
        ))
        p.blogger_publisher.publish = AsyncMock(return_value=PublishResult(
            success=publish_ok, platform="blogger",
            published_url=url, platform_post_id="abc" if publish_ok else None,
            error=err,
        ))
        p.inventory_manager.mark_as_published = AsyncMock()
        return p

    @pytest.mark.asyncio
    async def test_full_pipeline_wordpress_success(
        self, mock_db, wp_blog, sample_post,
    ):
        """WordPress 전체 성공: mark_as_published 호출 확인"""
        p = self._build(mock_db)
        result = await p.publish_post(wp_blog, sample_post)
        assert result.success is True
        assert result.image_uploaded is False
        p.inventory_manager.mark_as_published.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_image_upload_failure_aborts(
        self, mock_db, wp_blog, sample_post_with_image,
    ):
        """대표이미지 업로드 실패 시 발행 중단(이미지 없는 발행 금지)

        - 플랫폼 발행/상태 갱신 미호출
        - 실패 기록 호출, success=False 반환
        """
        p = self._build(mock_db, image_result=ImageUploadResult(
            success=False,
            error="imgbb API 키가 설정되지 않았습니다",
        ))
        with patch.object(PublisherPipeline, "_resolve_image_path",
                          return_value="/tmp/t.webp"):
            result = await p.publish_post(
                wp_blog, sample_post_with_image,
            )
        assert result.success is False
        assert "대표이미지 업로드 실패" in (result.error or "")
        p.wp_publisher.publish.assert_not_called()
        p.inventory_manager.mark_as_published.assert_not_called()
        sample_post_with_image.record_publish_failure \
            .assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_publish_failure(
        self, mock_db, wp_blog, sample_post,
    ):
        """발행 실패 시 에러 반환, mark_as_published 미호출"""
        p = self._build(mock_db, publish_ok=False)
        result = await p.publish_post(wp_blog, sample_post)
        assert result.success is False
        assert result.error is not None
        p.inventory_manager.mark_as_published.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_status_update_error_still_success(
        self, mock_db, wp_blog, sample_post,
    ):
        """상태 갱신 실패해도 발행 성공 유지, errors에 기록"""
        p = self._build(mock_db)
        p.inventory_manager.mark_as_published = AsyncMock(
            side_effect=Exception("DB 오류"),
        )
        result = await p.publish_post(wp_blog, sample_post)
        assert result.success is True
        assert len(result.errors) >= 1
        assert "상태 갱신" in result.errors[0]
