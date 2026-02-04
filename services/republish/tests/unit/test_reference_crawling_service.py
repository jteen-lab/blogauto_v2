"""
참조자료 크롤링 서비스 단위 테스트

ReferenceCrawlingService의 웹 문서 크롤링 기능을 테스트합니다.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import httpx
import sys
import os

# app 경로 추가
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

from tests.fixtures.reference_collection_fixtures import (
    create_mock_db_session,
    create_html_response,
    create_blocked_html_response
)


class TestReferenceCrawlingServiceInit:
    """ReferenceCrawlingService 초기화 테스트"""

    def test_init_with_db_session(self):
        """DB 세션으로 초기화"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        assert service.db == mock_db
        assert service.TARGET_COUNT == 10
        assert service.MIN_COUNT == 5


class TestCrawlDocuments:
    """crawl_documents 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_crawl_empty_urls(self):
        """빈 URL 목록"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        result = await service.crawl_documents([], reference_id=1)

        assert result.total_attempted == 0
        assert result.total_success == 0
        assert result.documents == []

    @pytest.mark.asyncio
    async def test_crawl_single_url_success(self):
        """단일 URL 성공적 크롤링"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html_content = create_html_response(
            title="테스트 페이지",
            content="충분히 긴 본문 내용입니다. " * 20
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.crawl_documents(
                ["https://example.com/post/1"],
                reference_id=1
            )

            assert result.total_success == 1
            assert len(result.documents) == 1
            assert result.documents[0].title == "테스트 페이지"

    @pytest.mark.asyncio
    async def test_crawl_stops_at_target_count(self):
        """TARGET_COUNT 도달 시 중단"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        # 15개 URL 준비
        urls = [f"https://example{i}.com/post" for i in range(15)]

        html_content = create_html_response(content="충분한 내용 " * 30)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.crawl_documents(urls, reference_id=1)

            # TARGET_COUNT(10)에서 중단
            assert result.total_success == 10
            assert len(result.documents) == 10

    @pytest.mark.asyncio
    async def test_same_domain_limit(self):
        """같은 도메인 제한 (최대 2개)"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        # 같은 도메인 URL 5개
        urls = [f"https://example.com/post/{i}" for i in range(5)]

        html_content = create_html_response(content="충분한 내용 " * 30)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.crawl_documents(urls, reference_id=1)

            # MAX_SAME_DOMAIN(2)개만 크롤링
            assert result.total_success == 2


class TestCrawlSingle:
    """_crawl_single 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_successful_crawl(self):
        """성공적인 단일 크롤링"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html_content = create_html_response(
            title="성공 페이지",
            content="본문 내용입니다. " * 30
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            doc, status, error = await service._crawl_single(
                "https://example.com/post",
                "example.com"
            )

            assert doc is not None
            assert status == "success"
            assert error is None
            assert doc.title == "성공 페이지"

    @pytest.mark.asyncio
    async def test_blocked_response(self):
        """403 차단 응답"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            doc, status, error = await service._crawl_single(
                "https://blocked.com/post",
                "blocked.com"
            )

            assert doc is None
            assert status == "blocked"
            assert "403" in error

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """타임아웃 에러"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            doc, status, error = await service._crawl_single(
                "https://slow.com/post",
                "slow.com"
            )

            assert doc is None
            assert status == "timeout"
            assert "타임아웃" in error

    @pytest.mark.asyncio
    async def test_content_too_short(self):
        """본문이 너무 짧은 경우"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        # 너무 짧은 본문
        html_content = create_html_response(content="짧음")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            doc, status, error = await service._crawl_single(
                "https://short.com/post",
                "short.com"
            )

            assert doc is None
            assert status == "failed"
            assert "길이 부족" in error


class TestExtractContent:
    """_extract_content 메서드 테스트"""

    def test_extract_from_article(self):
        """article 태그에서 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <body>
            <header>헤더</header>
            <article>이것은 본문입니다. 충분히 긴 내용을 포함하고 있습니다. """ + "추가 내용 " * 20 + """</article>
            <footer>푸터</footer>
        </body>
        </html>
        """

        content = service._extract_content(html)

        assert content is not None
        assert "본문" in content
        assert "헤더" not in content
        assert "푸터" not in content

    def test_extract_from_main(self):
        """main 태그에서 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <body>
            <nav>네비게이션</nav>
            <main>메인 콘텐츠입니다. """ + "충분한 내용 " * 20 + """</main>
        </body>
        </html>
        """

        content = service._extract_content(html)

        assert content is not None
        assert "메인" in content

    def test_extract_removes_script_and_style(self):
        """script, style 태그 제거"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <head>
            <style>body { color: red; }</style>
        </head>
        <body>
            <script>alert('hello');</script>
            <article>본문 내용입니다. """ + "추가 " * 30 + """</article>
            <script>console.log('test');</script>
        </body>
        </html>
        """

        content = service._extract_content(html)

        assert "alert" not in content
        assert "color: red" not in content
        assert "console.log" not in content

    def test_extract_from_body_fallback(self):
        """본문 영역 없으면 body에서 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <body>
            <div>일반 div 내용입니다. """ + "충분한 내용 " * 30 + """</div>
        </body>
        </html>
        """

        content = service._extract_content(html)

        assert content is not None
        assert "일반 div" in content


class TestExtractTitle:
    """_extract_title 메서드 테스트"""

    def test_extract_og_title(self):
        """og:title 메타 태그에서 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <head>
            <title>일반 제목</title>
            <meta property="og:title" content="OG 제목" />
        </head>
        <body></body>
        </html>
        """

        title = service._extract_title(html)

        # og:title 우선
        assert title == "OG 제목"

    def test_extract_title_tag(self):
        """title 태그에서 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <head>
            <title>페이지 제목</title>
        </head>
        <body></body>
        </html>
        """

        title = service._extract_title(html)

        assert title == "페이지 제목"

    def test_extract_no_title(self):
        """제목이 없는 경우"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        html = """
        <html>
        <head></head>
        <body></body>
        </html>
        """

        title = service._extract_title(html)

        assert title is None


class TestValidateContent:
    """_validate_content 메서드 테스트"""

    def test_valid_content(self):
        """유효한 콘텐츠"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        content = "충분히 긴 콘텐츠입니다. " * 20

        assert service._validate_content(content) is True

    def test_empty_content(self):
        """빈 콘텐츠"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        assert service._validate_content("") is False
        assert service._validate_content(None) is False

    def test_short_content(self):
        """짧은 콘텐츠 (MIN_CONTENT_LENGTH 미만)"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        short_content = "짧은 내용"

        assert service._validate_content(short_content) is False


class TestExtractDomain:
    """_extract_domain 메서드 테스트"""

    def test_extract_simple_domain(self):
        """단순 도메인 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        domain = service._extract_domain("https://example.com/post/123")

        assert domain == "example.com"

    def test_extract_subdomain(self):
        """서브도메인 포함 추출"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        domain = service._extract_domain("https://blog.example.com/post")

        assert domain == "blog.example.com"

    def test_extract_invalid_url(self):
        """잘못된 URL"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        domain = service._extract_domain("not a url")

        assert domain == ""


class TestCleanText:
    """_clean_text 메서드 테스트"""

    def test_normalize_whitespace(self):
        """공백 정규화"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        text = "여러    공백이\n\n있는   텍스트"
        result = service._clean_text(text)

        assert result == "여러 공백이 있는 텍스트"

    def test_strip_text(self):
        """앞뒤 공백 제거"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        text = "   텍스트   "
        result = service._clean_text(text)

        assert result == "텍스트"


class TestLogCrawl:
    """_log_crawl 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_log_success(self):
        """성공 로그 저장"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        await service._log_crawl(
            reference_id=1,
            url="https://example.com",
            domain="example.com",
            status="success",
            content_length=1000,
            duration_ms=500
        )

        # db.add 호출 확인
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_failure(self):
        """실패 로그 저장"""
        from app.services.reference_crawling_service import ReferenceCrawlingService

        mock_db = create_mock_db_session()
        service = ReferenceCrawlingService(mock_db)

        await service._log_crawl(
            reference_id=1,
            url="https://failed.com",
            domain="failed.com",
            status="failed",
            error_message="HTTP 500",
            duration_ms=200
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
