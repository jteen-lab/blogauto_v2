"""
참조자료 검색 서비스 단위 테스트

ReferenceSearchService의 네이버 웹문서 검색 기능을 테스트합니다.
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

# fixtures 경로 추가
fixtures_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../fixtures'))
if fixtures_path not in sys.path:
    sys.path.insert(0, fixtures_path)

from tests.fixtures.reference_collection_fixtures import (
    create_mock_user_settings,
    create_mock_user_settings_no_api,
    create_naver_api_response
)


class TestReferenceSearchServiceInit:
    """ReferenceSearchService 초기화 테스트"""

    def test_init_with_valid_settings(self):
        """유효한 설정으로 초기화"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        assert service.client_id == "test_client_id"
        assert service.client_secret == "test_client_secret"
        assert service.is_configured() is True

    def test_init_without_api_keys(self):
        """API 키 없이 초기화"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings_no_api()
        service = ReferenceSearchService(settings)

        assert service.is_configured() is False


class TestIsConfigured:
    """is_configured 메서드 테스트"""

    def test_configured_with_both_keys(self):
        """양쪽 키가 모두 있으면 True"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        assert service.is_configured() is True

    def test_not_configured_with_missing_id(self):
        """client_id 없으면 False"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings(naver_client_id=None)
        service = ReferenceSearchService(settings)

        assert service.is_configured() is False

    def test_not_configured_with_missing_secret(self):
        """client_secret 없으면 False"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings(naver_client_secret=None)
        service = ReferenceSearchService(settings)

        assert service.is_configured() is False


class TestSearchWebdoc:
    """search_webdoc 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_configured(self):
        """API 키 미설정 시 빈 리스트 반환"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings_no_api()
        service = ReferenceSearchService(settings)

        result = await service.search_webdoc("테스트 검색어")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_short_query(self):
        """검색어가 너무 짧으면 빈 리스트 반환"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        result = await service.search_webdoc("a")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_query(self):
        """빈 검색어면 빈 리스트 반환"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        result = await service.search_webdoc("")

        assert result == []

    @pytest.mark.asyncio
    async def test_successful_search(self):
        """성공적인 검색"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        mock_response = create_naver_api_response(3)

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = await service.search_webdoc("테스트 검색어", count=3)

            assert len(result) == 3
            assert result[0].title == "테스트 블로그 글 1"
            assert "blog1.example.com" in result[0].link

    @pytest.mark.asyncio
    async def test_search_respects_count_limit(self):
        """count 파라미터 제한 확인"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        mock_response = create_naver_api_response(5)

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = await service.search_webdoc("테스트", count=5)

            # _call_api 호출 시 display 파라미터 확인
            call_args = mock_api.call_args
            assert call_args[0][1]["display"] == 5


class TestCallApi:
    """_call_api 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_successful_api_call(self):
        """성공적인 API 호출"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        mock_response_data = create_naver_api_response(3)

        # httpx.AsyncClient Mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service._call_api(
                "https://openapi.naver.com/v1/search/webkr.json",
                {"query": "테스트", "display": 3}
            )

            assert result is not None
            assert "items" in result

    @pytest.mark.asyncio
    async def test_api_timeout_with_retry(self):
        """타임아웃 발생 시 재시도"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service._call_api(
                "https://openapi.naver.com/v1/search/webkr.json",
                {"query": "테스트"}
            )

            # 타임아웃 후 None 반환
            assert result is None
            # 재시도 포함 2회 호출
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_api_error_response(self):
        """API 오류 응답 처리"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service._call_api(
                "https://openapi.naver.com/v1/search/webkr.json",
                {"query": "테스트"}
            )

            assert result is None


class TestParseResponse:
    """_parse_response 메서드 테스트"""

    def test_parse_valid_response(self):
        """유효한 응답 파싱"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        response = create_naver_api_response(3)
        results = service._parse_response(response)

        assert len(results) == 3
        # HTML 태그 제거 확인
        assert "<b>" not in results[0].title
        assert "테스트 블로그 글 1" in results[0].title

    def test_parse_empty_response(self):
        """빈 응답 파싱"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        response = {"items": []}
        results = service._parse_response(response)

        assert results == []

    def test_parse_response_with_invalid_item(self):
        """잘못된 아이템이 포함된 응답"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        response = {
            "items": [
                {"title": "정상 제목", "link": "https://example.com", "description": "설명"},
                None,  # 잘못된 아이템
                {"title": "또 다른 제목", "link": "https://example2.com", "description": "설명2"}
            ]
        }

        # None 아이템은 예외 발생시켜 스킵됨
        results = service._parse_response(response)
        assert len(results) >= 1


class TestCleanHtml:
    """_clean_html 메서드 테스트"""

    def test_remove_html_tags(self):
        """HTML 태그 제거"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        text = "<b>볼드</b> 텍스트 <i>이탤릭</i>"
        result = service._clean_html(text)

        assert result == "볼드 텍스트 이탤릭"

    def test_decode_html_entities(self):
        """HTML 엔티티 디코딩"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        text = "Tom &amp; Jerry &quot;friends&quot;"
        result = service._clean_html(text)

        assert result == 'Tom & Jerry "friends"'

    def test_normalize_whitespace(self):
        """공백 정규화"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        text = "여러    공백이   있는   텍스트"
        result = service._clean_html(text)

        assert result == "여러 공백이 있는 텍스트"

    def test_empty_input(self):
        """빈 입력 처리"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        assert service._clean_html("") == ""
        assert service._clean_html(None) == ""


class TestTestConnection:
    """test_connection 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_connection_not_configured(self):
        """설정되지 않은 경우"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings_no_api()
        service = ReferenceSearchService(settings)

        result = await service.test_connection()

        assert result["success"] is False
        assert "설정되지 않" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_success(self):
        """연결 성공"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        mock_response = create_naver_api_response(1)

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response

            result = await service.test_connection()

            assert result["success"] is True
            assert "성공" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_no_results(self):
        """검색 결과 없음"""
        from app.services.reference_search_service import ReferenceSearchService

        settings = create_mock_user_settings()
        service = ReferenceSearchService(settings)

        with patch.object(service, '_call_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {"items": []}

            result = await service.test_connection()

            assert result["success"] is False
            assert "결과가 없" in result["error"]
