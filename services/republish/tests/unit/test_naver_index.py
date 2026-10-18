"""S6-N 네이버 색인(노출) 점검 테스트.

네이버에는 GSC 같은 색인 조회 API 가 없어 웹문서 검색으로 대신한다.
따라서 '없음'이 미색인의 증거가 아니며, 상태 이름도 found/not_found 다.
"""
import pytest

from app.services.search_visibility import naver_index_service as nis


# ---------- URL 정규화 ----------

@pytest.mark.parametrize("a,b", [
    ("https://doooit082.com/5107/", "http://doooit082.com/5107"),
    ("https://www.doooit082.com/5107", "https://doooit082.com/5107/"),
    ("https://DOOOIT082.com/5107/", "https://doooit082.com/5107"),
])
def test_normalize_treats_variants_as_same(a, b):
    """스킴·www·대소문자·끝슬래시 차이로 놓치면 안 된다."""
    assert nis.normalize(a) == nis.normalize(b)


def test_normalize_distinguishes_different_paths():
    assert nis.normalize("https://x.com/1") != nis.normalize("https://x.com/2")


def test_normalize_empty():
    assert nis.normalize("") == ""


# ---------- 제목 정리 ----------

def test_clean_title_strips_tags_and_brackets():
    assert nis.clean_title("<b>[속보]</b> 월세 환급 (2026)") == "속보 월세 환급 2026"


def test_clean_title_collapses_whitespace():
    assert nis.clean_title("  월세   환급  ") == "월세 환급"


def test_clean_title_empty():
    assert nis.clean_title("") == ""


# ---------- 순위 탐색 ----------

def test_find_rank_returns_position():
    items = [
        {"link": "https://other.com/a"},
        {"link": "https://doooit082.com/5107/"},
    ]
    assert nis.find_rank(items, "https://doooit082.com/5107") == 2


def test_find_rank_none_when_absent():
    assert nis.find_rank([{"link": "https://other.com/a"}], "https://x.com/1") is None


def test_find_rank_handles_empty_items():
    assert nis.find_rank([], "https://x.com/1") is None


# ---------- 검색 호출 ----------

class _FakeService:
    def __init__(self, response):
        self.response = response
        self.queries = []

    def is_configured(self):
        return True

    async def search_webdoc(self, query, display=100, start=1):
        self.queries.append(query)
        return self.response


@pytest.mark.asyncio
async def test_check_url_found():
    svc = _FakeService({"items": [{"link": "https://x.com/1/"}]})
    result = await nis.check_url(svc, "https://x.com/1", "테스트 제목")
    assert result.found is True
    assert result.rank == 1
    assert svc.queries == ["테스트 제목"]


@pytest.mark.asyncio
async def test_check_url_not_found():
    svc = _FakeService({"items": [{"link": "https://other.com/9"}]})
    result = await nis.check_url(svc, "https://x.com/1", "테스트 제목")
    assert result.found is False
    assert result.rank is None
    assert result.result_count == 1


@pytest.mark.asyncio
async def test_check_url_reports_api_error():
    svc = _FakeService({"success": False, "error": "Rate Limit 초과", "items": []})
    result = await nis.check_url(svc, "https://x.com/1", "제목")
    assert result.error == "Rate Limit 초과"
    assert result.found is False


@pytest.mark.asyncio
async def test_check_url_without_title():
    svc = _FakeService({"items": []})
    result = await nis.check_url(svc, "https://x.com/1", "   ")
    assert result.found is False
    assert "제목" in result.error
    assert svc.queries == []  # 빈 질의로 API 를 낭비하지 않는다


@pytest.mark.asyncio
async def test_check_url_survives_exception():
    class Boom:
        def is_configured(self):
            return True

        async def search_webdoc(self, *a, **kw):
            raise RuntimeError("네트워크 끊김")

    result = await nis.check_url(Boom(), "https://x.com/1", "제목")
    assert result.found is False
    assert "네트워크 끊김" in result.error


def test_detail_payload_shape():
    result = nis.NaverIndexResult(found=True, rank=3, query="q", result_count=30)
    assert result.to_detail() == {
        "query": "q", "rank": 3, "result_count": 30, "error": None,
    }


# ---------- 짧은 검색어 (10/19 마케팅: 제목 전체 검색 = 색인 확인일 뿐) ----------

def test_short_query_takes_front_words():
    assert nis.short_query("관악우체국 근무시간 전화번호 정리") == "관악우체국 근무시간"


def test_short_query_adds_word_when_front_is_short():
    assert nis.short_query("옷 땀 냄새 쉽게 제거하는 방법") == "옷 땀 냄새"


def test_short_query_empty_when_same_as_title():
    """제목이 이미 짧으면 따로 볼 필요가 없다(같은 질의로 두 번 부르지 않는다)."""
    assert nis.short_query("마운자로 부작용") == ""


@pytest.mark.asyncio
async def test_check_short_records_rank():
    svc = _FakeService({"items": [{"link": "https://o.com/1"}, {"link": "https://x.com/1"}]})
    out = await nis.check_short(svc, "https://x.com/1", "마운자로 손바닥 간지러움 원인 정리")
    assert out == {"short_query": "마운자로 손바닥 간지러움", "short_rank": 2}
