"""건강형 주제 '공식 출처 우선' — 도메인·가산·판정·인용 지시문."""
import asyncio
from types import SimpleNamespace

from app.services.reference import health_sources as hs
from app.services.generation.reference_collector import (
    ReferenceCollectionResult)
from app.schemas.reference_collection import DocumentSummary


def _r(link):
    return SimpleNamespace(link=link, title="t", description="")


class TestDomainWhitelist:
    def test_subdomain_and_www(self):
        assert hs.is_official("https://health.kdca.go.kr/x")
        assert hs.is_official("https://www.mfds.go.kr/a")
        assert hs.official_org("https://nedrug.mfds.go.kr/p").startswith(
            "의약품안전나라")

    def test_lookalike_rejected(self):
        assert not hs.is_official("https://blog.naver.com/kdca.go.kr")
        assert not hs.is_official("https://evilkdca.go.kr/")
        assert not hs.is_official("https://cafe.naver.com/x")
        assert not hs.is_official("")


class TestBoost:
    def test_official_first_stable(self):
        items = [_r("https://blog.naver.com/a"), _r("https://www.nhis.or.kr/b"),
                 _r("https://tistory.com/c"), _r("https://kdca.go.kr/d")]
        out = [i.link for i in hs.boost_official(items)]
        assert out == ["https://www.nhis.or.kr/b", "https://kdca.go.kr/d",
                       "https://blog.naver.com/a", "https://tistory.com/c"]

    def test_augment_adds_official_only_for_health(self):
        class S:
            calls = 0

            async def search_webdoc(self, q, count=10):
                S.calls += 1
                return [_r("https://health.kdca.go.kr/1"),
                        _r("https://blog.naver.com/x")]

        base = [_r("https://blog.naver.com/y")]
        out = asyncio.run(hs.augment(S(), "비타민D", base, True))
        links = [r.link for r in out]
        assert links[0] == "https://health.kdca.go.kr/1"
        assert "https://blog.naver.com/x" not in links
        assert links.count("https://health.kdca.go.kr/1") == 1
        S.calls = 0
        assert asyncio.run(hs.augment(S(), "q", base, False)) == base
        assert S.calls == 0


class TestHealthTopic:
    def test_topic_names(self):
        assert hs.is_health_topic(["건강/의학", "비만/다이어트"])
        assert hs.is_health_topic(["음식/레시피", "음식 효능"])
        assert hs.is_health_topic(["생활", "육아팁"])
        assert not hs.is_health_topic(["금융", "대출"])

    def test_title_fallback(self):
        assert hs.is_health_topic([], "마늘 효능 총정리")
        assert not hs.is_health_topic([], "청년 전세대출 조건")


class TestPrompt:
    def _res(self, citation):
        return ReferenceCollectionResult(
            count=1, citation=citation,
            summaries=[DocumentSummary(url="http://a", title="a",
                                       summary="요약", original_length=10, summary_length=2,
                                       is_ai_summary=True)])

    def test_health_prompt_has_citation_rule(self):
        refs = hs.official_refs([SimpleNamespace(
            url="https://health.kdca.go.kr/p", title="비만"),
            SimpleNamespace(url="https://blog.naver.com/b", title="블로그")])
        assert len(refs) == 1 and refs[0]["is_official"]
        text = self._res(hs.citation_block(refs, True)).to_prompt_injection()
        assert "참고 자료" in text and "국가건강정보포털" in text
        assert "blog.naver.com" not in text.split("[인용 가능한 공식 출처]")[1]
        assert "진단·치료를 대신하지 않습니다" in text
        assert "공식 출처에 있는 것만" in text
        assert "출처 URL 은 본문에 쓰지 마세요" not in text

    def test_non_health_without_official_unchanged(self):
        assert hs.citation_block([], False) == ""
        text = self._res("").to_prompt_injection()
        assert "진단" not in text
        assert "출처 URL 은 본문에 쓰지 마세요" not in text
