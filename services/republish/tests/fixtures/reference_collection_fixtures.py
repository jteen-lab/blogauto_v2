"""
참조자료 수집 모듈 테스트 픽스처

모든 참조자료 관련 테스트에서 사용되는 공통 픽스처 정의
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from app.schemas.reference_collection import (
    SearchResult, CrawledDocument, DocumentSummary, CrawlResult
)


# ============================================================
# Mock 데이터 팩토리
# ============================================================

def create_mock_user_settings(
    naver_client_id: str = "test_client_id",
    naver_client_secret: str = "test_client_secret",
    **kwargs
):
    """Mock UserSettings 생성"""
    settings = MagicMock()
    settings.naver_search_client_id = naver_client_id
    settings.naver_search_client_secret = naver_client_secret
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings


def create_mock_user_settings_no_api():
    """API 키 없는 Mock UserSettings"""
    return create_mock_user_settings(
        naver_client_id=None,
        naver_client_secret=None
    )


def create_mock_db_session():
    """Mock AsyncSession 생성"""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ============================================================
# 검색 결과 픽스처
# ============================================================

def create_search_result(
    title: str = "테스트 블로그 글",
    link: str = "https://blog.example.com/post/1",
    description: str = "테스트 설명입니다.",
    bloggername: str = "테스터",
    **kwargs
) -> SearchResult:
    """SearchResult 생성"""
    return SearchResult(
        title=title,
        link=link,
        description=description,
        bloggername=bloggername,
        bloggerlink=kwargs.get("bloggerlink"),
        postdate=kwargs.get("postdate", "20240101")
    )


def create_search_results(count: int = 5) -> list[SearchResult]:
    """여러 SearchResult 생성"""
    return [
        create_search_result(
            title=f"블로그 글 {i}",
            link=f"https://blog{i}.example.com/post/{i}",
            description=f"테스트 설명 {i}입니다."
        )
        for i in range(1, count + 1)
    ]


# ============================================================
# 크롤링 결과 픽스처
# ============================================================

def create_crawled_document(
    url: str = "https://blog.example.com/post/1",
    domain: str = "blog.example.com",
    title: str = "테스트 문서 제목",
    content: str = "이것은 테스트 문서의 본문입니다. " * 20,
    **kwargs
) -> CrawledDocument:
    """CrawledDocument 생성"""
    return CrawledDocument(
        url=url,
        domain=domain,
        title=title,
        content=content,
        content_length=kwargs.get("content_length", len(content)),
        crawled_at=kwargs.get("crawled_at", datetime.now())
    )


def create_crawled_documents(count: int = 5) -> list[CrawledDocument]:
    """여러 CrawledDocument 생성"""
    return [
        create_crawled_document(
            url=f"https://blog{i}.example.com/post/{i}",
            domain=f"blog{i}.example.com",
            title=f"문서 제목 {i}",
            content=f"문서 {i}의 본문 내용입니다. " * 30
        )
        for i in range(1, count + 1)
    ]


def create_crawl_result(
    total_attempted: int = 10,
    total_success: int = 5,
    total_failed: int = 5,
    documents: list[CrawledDocument] = None
) -> CrawlResult:
    """CrawlResult 생성"""
    if documents is None:
        documents = create_crawled_documents(total_success)
    return CrawlResult(
        total_attempted=total_attempted,
        total_success=total_success,
        total_failed=total_failed,
        documents=documents,
        has_minimum=total_success >= 5
    )


# ============================================================
# 요약 결과 픽스처
# ============================================================

def create_document_summary(
    url: str = "https://blog.example.com/post/1",
    title: str = "테스트 문서",
    summary: str = "이 문서는 테스트 내용을 담고 있습니다.",
    is_ai_summary: bool = True,
    **kwargs
) -> DocumentSummary:
    """DocumentSummary 생성"""
    return DocumentSummary(
        url=url,
        title=title,
        original_length=kwargs.get("original_length", 1000),
        summary=summary,
        summary_length=len(summary),
        is_ai_summary=is_ai_summary
    )


def create_document_summaries(count: int = 3) -> list[DocumentSummary]:
    """여러 DocumentSummary 생성"""
    return [
        create_document_summary(
            url=f"https://blog{i}.example.com/post/{i}",
            title=f"문서 {i}",
            summary=f"문서 {i}에 대한 요약입니다."
        )
        for i in range(1, count + 1)
    ]


# ============================================================
# HTTP 응답 픽스처
# ============================================================

def create_naver_api_response(item_count: int = 5) -> dict:
    """네이버 검색 API 응답 Mock"""
    return {
        "lastBuildDate": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900"),
        "total": item_count * 100,
        "start": 1,
        "display": item_count,
        "items": [
            {
                "title": f"<b>테스트</b> 블로그 글 {i}",
                "link": f"https://blog{i}.example.com/post/{i}",
                "description": f"테스트 &amp; 설명 {i}입니다.",
                "bloggername": f"블로거{i}",
                "bloggerlink": f"https://blog{i}.example.com",
                "postdate": "20240101"
            }
            for i in range(1, item_count + 1)
        ]
    }


def create_html_response(
    title: str = "테스트 페이지",
    content: str = "테스트 본문 내용입니다. " * 50
) -> str:
    """HTML 페이지 응답 Mock"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta property="og:title" content="{title}" />
    </head>
    <body>
        <header>헤더</header>
        <nav>네비게이션</nav>
        <article>
            <h1>{title}</h1>
            <div class="content">
                {content}
            </div>
        </article>
        <footer>푸터</footer>
    </body>
    </html>
    """


def create_blocked_html_response() -> str:
    """차단된 페이지 HTML"""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Access Denied</title></head>
    <body>
        <h1>403 Forbidden</h1>
        <p>Access to this page is denied.</p>
    </body>
    </html>
    """


# ============================================================
# CollectedReference 모델 픽스처
# ============================================================

def create_mock_collected_reference(
    id: int = 1,
    status: str = "pending",
    search_query: str = "테스트 검색어",
    **kwargs
):
    """Mock CollectedReference 생성"""
    ref = MagicMock()
    ref.id = id
    ref.title_id = kwargs.get("title_id")
    ref.search_query = search_query
    ref.status = status
    ref.total_searched = kwargs.get("total_searched", 0)
    ref.total_crawled = kwargs.get("total_crawled", 0)
    ref.total_failed = kwargs.get("total_failed", 0)
    ref.selected_references = kwargs.get("selected_references")
    ref.error_message = kwargs.get("error_message")
    ref.created_at = kwargs.get("created_at", datetime.now())
    ref.completed_at = kwargs.get("completed_at")
    return ref


# ============================================================
# AI API Mock 응답
# ============================================================

def create_mock_openai_response(content: str = "요약된 내용입니다."):
    """Mock OpenAI API 응답"""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def create_mock_anthropic_response(content: str = "요약된 내용입니다."):
    """Mock Anthropic API 응답"""
    response = MagicMock()
    response.content = [MagicMock()]
    response.content[0].text = content
    return response


def create_mock_ai_key(
    id: int = 1,
    api_key: str = "test_api_key",
    provider: str = "openai",
    is_active: bool = True
):
    """Mock AI API Key"""
    key = MagicMock()
    key.id = id
    key.api_key = api_key
    key.provider = provider
    key.is_active = is_active
    return key


# ============================================================
# pytest fixtures
# ============================================================

@pytest.fixture
def mock_db():
    """Mock 데이터베이스 세션 fixture"""
    return create_mock_db_session()


@pytest.fixture
def mock_user_settings():
    """Mock UserSettings fixture"""
    return create_mock_user_settings()


@pytest.fixture
def mock_user_settings_no_api():
    """API 키 없는 Mock UserSettings fixture"""
    return create_mock_user_settings_no_api()


@pytest.fixture
def sample_search_results():
    """샘플 검색 결과 fixture"""
    return create_search_results(5)


@pytest.fixture
def sample_crawled_documents():
    """샘플 크롤링 문서 fixture"""
    return create_crawled_documents(5)


@pytest.fixture
def sample_document_summaries():
    """샘플 요약 결과 fixture"""
    return create_document_summaries(3)


@pytest.fixture
def sample_naver_response():
    """샘플 네이버 API 응답 fixture"""
    return create_naver_api_response(5)


@pytest.fixture
def sample_html_response():
    """샘플 HTML 응답 fixture"""
    return create_html_response()


@pytest.fixture
def mock_collected_reference():
    """Mock CollectedReference fixture"""
    return create_mock_collected_reference()
