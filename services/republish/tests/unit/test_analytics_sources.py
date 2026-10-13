"""유입 경로 · 옛 글 수집 (마케팅 B1·B2, 2026-10-14).

순서도: docs/flowcharts/analytics_sources.md
"""
import asyncio
from datetime import date

import pytest


class TestClassifyChannel:
    """sessionSource/medium → 네이버/구글/직접/기타."""

    @pytest.mark.parametrize("source,medium,expected", [
        ("naver", "organic", "naver"),
        ("search.naver.com", "referral", "naver"),
        ("m.blog.naver.com", "referral", "naver"),
        ("google", "organic", "google"),
        ("(direct)", "(none)", "direct"),
        ("daum", "organic", "other"),
        ("chatgpt.com", "referral", "other"),
        ("", "(none)", "direct"),
    ])
    def test_channels(self, source, medium, expected):
        from app.services.analytics.page_metrics import classify_channel
        assert classify_channel(source, medium) == expected


class TestAggregatePages:
    """(경로, 날짜) 칸으로 합치기."""

    def _rows(self):
        return [
            {"date": "2026-10-01", "path": "/555/", "source": "naver",
             "medium": "organic", "sessions": 3, "engaged_sessions": 2,
             "avg_duration": 100.0},
            {"date": "2026-10-01", "path": "/555", "source": "(direct)",
             "medium": "(none)", "sessions": 1, "engaged_sessions": 0,
             "avg_duration": 20.0},
            {"date": "2026-10-01", "path": "/", "source": "google",
             "medium": "organic", "sessions": 2, "engaged_sessions": 1,
             "avg_duration": 0.0},
            {"date": "bad", "path": "/x", "source": "naver",
             "medium": "organic", "sessions": 9, "engaged_sessions": 9,
             "avg_duration": 9.0},
        ]

    def test_trailing_slash_merged_and_channels_split(self):
        from app.services.analytics.page_metrics import aggregate_pages
        out = aggregate_pages(self._rows())
        slot = out[("/555", date(2026, 10, 1))]
        assert slot["sessions"] == 4
        assert slot["naver_sessions"] == 3
        assert slot["direct_sessions"] == 1
        assert slot["google_sessions"] == 0
        assert slot["engaged_sessions"] == 2

    def test_avg_duration_is_session_weighted(self):
        from app.services.analytics.page_metrics import aggregate_pages
        slot = aggregate_pages(self._rows())[("/555", date(2026, 10, 1))]
        assert slot["avg_duration"] == pytest.approx((300 + 20) / 4, 0.01)

    def test_channel_sum_equals_sessions(self):
        from app.services.analytics.page_metrics import (
            CHANNELS, aggregate_pages)
        for slot in aggregate_pages(self._rows()).values():
            assert sum(slot[f"{c}_sessions"] for c in CHANNELS) == slot["sessions"]

    def test_broken_date_dropped(self):
        from app.services.analytics.page_metrics import aggregate_pages
        assert all(k[0] != "/x" for k in aggregate_pages(self._rows()))


class TestFetchLandingSources:
    """GA4 행을 1만 행씩 끝까지 이어 받는다."""

    def test_paginates_until_row_count(self, monkeypatch):
        from app.services.analytics import ga4_client

        def row(i):
            return {"dimensionValues": [{"value": "20261001"},
                                        {"value": f"/p{i}"},
                                        {"value": "naver"},
                                        {"value": "organic"}],
                    "metricValues": [{"value": "1"}, {"value": "1"},
                                     {"value": "10.5"}]}

        offsets = []

        class FakeResponse:
            status_code = 200

            def __init__(self, offset):
                self._offset = offset

            def json(self):
                size = 2 if self._offset == 0 else 1
                return {"rowCount": 3,
                        "rows": [row(self._offset + i) for i in range(size)]}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                offsets.append(json["offset"])
                return FakeResponse(json["offset"])

        monkeypatch.setattr(ga4_client, "SOURCE_PAGE_SIZE", 2)
        monkeypatch.setattr(ga4_client.httpx, "AsyncClient", FakeClient)
        rows = asyncio.run(ga4_client.fetch_landing_sources("t", "1", 28))
        assert offsets == [0, 2]
        assert len(rows) == 3
        assert rows[0]["source"] == "naver" and rows[0]["medium"] == "organic"
        assert rows[0]["date"] == "2026-10-01"
        assert "_dims" not in rows[0]

    def test_old_parser_has_no_dims(self):
        from app.services.analytics import ga4_client
        out = ga4_client._parse_rows([{
            "dimensionValues": [{"value": "20261001"}, {"value": "/a"}],
            "metricValues": [{"value": "1"}, {"value": "0"}, {"value": "1"}]}])
        assert "_dims" not in out[0]
