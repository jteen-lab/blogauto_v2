"""검색광고가 검색량을 '< 10' 으로 가려 줄 때 클릭÷클릭률로 어림 (2026-10-23)."""
from app.services.naver_ads_service import NaverAdsService


def test_masked_count_estimated_from_clicks():
    svc = NaverAdsService(None)
    assert svc._count_or_estimate("< 10", 244.5, 1.52) == 16086
    assert svc._count_or_estimate("< 10", 0, 0) == 9
    assert svc._count_or_estimate(1200, 10, 1.0) == 1200      # 가려지지 않으면 그대로
    assert svc._count_or_estimate("< 10", 0.1, 10.0) == 9     # 어림이 더 작으면 9


def test_parse_response_uses_estimate():
    svc = NaverAdsService(None)
    data = {"keywordList": [{"relKeyword": "석류효능", "monthlyPcQcCnt": "< 10",
                             "monthlyMobileQcCnt": "< 10", "compIdx": "높음",
                             "monthlyAvePcClkCnt": 1.1, "monthlyAvePcCtr": 0.27,
                             "monthlyAveMobileClkCnt": 175.0, "monthlyAveMobileCtr": 2.37}]}
    kw = svc._parse_keyword_response(data, False)["keywords"][0]
    assert kw["total_search_volume"] == 7384 + 407 and kw["competition"] == "높음"
