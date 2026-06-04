"""
autorun_message_builder 단위 테스트

수집/대량수집 동작 로그 메시지/통계 생성기를 검증한다.
사용자 보고("동작 로그에 '수집'이라는 단어만 표시")의 재발 방지가 목적.
"""

from __future__ import annotations

import pytest

from app.services.autorun_message_builder import (
    CollectLogStats,
    build_collect_log_stats,
)


class TestCollectAction:
    """``action="collect"`` 케이스."""

    def test_success_with_title_and_keyword_sources(self) -> None:
        """제목 + 키워드/URL 소스 동시 성공 시 통계가 올바르게 합산된다."""
        result = {
            "success": True,
            "results": {
                "naver_news": {"success": True, "saved": 152},
                "google_trends": {"success": True, "saved": 20},
                "naver_ads": {"success": True, "saved": 15},
            },
        }
        stats = build_collect_log_stats(result, "collect")
        assert isinstance(stats, CollectLogStats)
        # 제목 152개 + 키워드/URL 35개 = 187 처리
        assert "제목 152개" in stats.message
        assert "키워드/URL 35개" in stats.message
        assert "수집" in stats.message
        assert "소스 3개" in stats.message
        assert stats.posts_processed == 187
        assert stats.posts_success == 187
        assert stats.posts_failed == 0

    def test_success_with_failed_source(self) -> None:
        """소스 일부 실패 시 실패 카운트가 메시지에 포함된다."""
        result = {
            "success": True,
            "results": {
                "naver_news": {"success": True, "saved": 100},
                "google_trends": {
                    "success": False,
                    "error": "API timeout",
                },
            },
        }
        stats = build_collect_log_stats(result, "collect")
        assert "제목 100개" in stats.message
        assert "실패 1개" in stats.message
        assert stats.posts_processed == 100

    def test_success_empty(self) -> None:
        """소스는 있는데 저장 0개인 경우도 깔끔하게 처리."""
        result = {
            "success": True,
            "results": {
                "naver_news": {"success": True, "saved": 0},
            },
        }
        stats = build_collect_log_stats(result, "collect")
        assert "수집 완료" in stats.message or "0개" in stats.message
        assert stats.posts_processed == 0
        assert stats.posts_failed == 0

    def test_with_extraction(self) -> None:
        """키워드 추출 결과 포함 시 메시지에 표시."""
        result = {
            "success": True,
            "results": {
                "naver_news": {"success": True, "saved": 50},
            },
            "extraction_result": {"keywords_saved": 30},
        }
        stats = build_collect_log_stats(result, "collect")
        assert "제목 50개" in stats.message
        assert "키워드추출 30개" in stats.message
        assert stats.posts_processed == 80

    def test_failed(self) -> None:
        """전체 실패 케이스."""
        result = {
            "success": False,
            "message": "수집 소스가 설정되지 않았습니다 (타입: both)",
        }
        stats = build_collect_log_stats(result, "collect")
        assert stats.message.startswith("수집 실패:")
        assert "수집 소스가 설정되지" in stats.message
        assert stats.posts_processed == 0
        assert stats.posts_failed == 1


class TestBulkCollectAction:
    """``action="bulk_collect"`` 케이스."""

    def test_success_large_numbers(self) -> None:
        """대량 수집 성공 시 처리/실패/소요 시간이 표시된다."""
        result = {
            "success": True,
            "processed": 80,
            "failed": 5,
            "duration_sec": 45,
            "chunk_size": 100,
            "ingest_summary": None,
        }
        stats = build_collect_log_stats(result, "bulk_collect")
        assert "제목 80개" in stats.message
        assert "실패 5개" in stats.message
        assert "소요 45초" in stats.message
        assert stats.posts_processed == 85
        assert stats.posts_success == 80
        assert stats.posts_failed == 5

    def test_success_with_ingest_summary(self) -> None:
        """첫 사이클 ingest 시 posts_ingested 우선 사용."""
        result = {
            "success": True,
            "processed": 5,
            "failed": 0,
            "duration_sec": 10,
            "ingest_summary": {
                "posts_ingested": 200,
                "blogs_processed": 3,
            },
        }
        stats = build_collect_log_stats(result, "bulk_collect")
        # posts_ingested 가 우선 표시
        assert "제목 200개" in stats.message

    def test_failed(self) -> None:
        """대량 수집 실패."""
        result = {
            "success": False,
            "message": "모듈을 찾을 수 없습니다 id=42",
        }
        stats = build_collect_log_stats(result, "bulk_collect")
        assert stats.message.startswith("대량 수집 실패:")
        assert stats.posts_failed == 1


class TestEdgeCases:
    """방어 코드 검증."""

    def test_unknown_action_returns_none(self) -> None:
        """publish/republish 등은 None 반환 → 호출자 기존 로직 유지."""
        result = {"success": True, "message": "발행 완료"}
        assert build_collect_log_stats(result, "publish") is None
        assert build_collect_log_stats(result, "republish") is None

    def test_malformed_result(self) -> None:
        """results 키가 list 등 잘못된 타입이어도 예외 없이 fallback."""
        result = {"success": True, "results": "not-a-dict"}
        stats = build_collect_log_stats(result, "collect")
        # 예외 없이 None 또는 stats 반환 (둘 다 허용)
        assert stats is None or isinstance(stats, CollectLogStats)


class TestJitterNormalization:
    """jitter.normalize_jitter_config 및 resolve_module_jitter 검증."""

    def test_new_object_format(self) -> None:
        from app.scheduler.jitter import normalize_jitter_config
        result = normalize_jitter_config(
            {"enabled": True, "min_percent": -20, "max_percent": 30}
        )
        assert result == {
            "enabled": True, "min_percent": -20, "max_percent": 30,
        }

    def test_legacy_flat_format_conversion(self) -> None:
        """레거시 양수 형식 (80~120) → ±% (-20~+20) 변환."""
        from app.scheduler.jitter import normalize_jitter_config
        result = normalize_jitter_config({
            "jitter_enabled": True,
            "jitter_min_percent": 80,
            "jitter_max_percent": 120,
        })
        assert result["enabled"] is True
        assert result["min_percent"] == -20
        assert result["max_percent"] == 20

    def test_none_returns_default_disabled(self) -> None:
        from app.scheduler.jitter import normalize_jitter_config
        result = normalize_jitter_config(None)
        assert result["enabled"] is False

    def test_resolve_module_jitter_new_format(self) -> None:
        """settings.schedule.jitter (객체) 우선."""
        from app.scheduler.jitter import resolve_module_jitter
        settings = {
            "schedule": {
                "jitter": {
                    "enabled": True,
                    "min_percent": -30,
                    "max_percent": 50,
                },
            },
        }
        result = resolve_module_jitter(settings)
        assert result == {
            "enabled": True, "min_percent": -30, "max_percent": 50,
        }

    def test_resolve_module_jitter_legacy_flat(self) -> None:
        """settings.schedule.jitter_enabled 평탄 형식 폴백."""
        from app.scheduler.jitter import resolve_module_jitter
        settings = {
            "schedule": {
                "jitter_enabled": True,
                "jitter_min_percent": 90,
                "jitter_max_percent": 110,
            },
        }
        result = resolve_module_jitter(settings)
        assert result["enabled"] is True
        assert result["min_percent"] == -10
        assert result["max_percent"] == 10

    def test_resolve_module_jitter_empty(self) -> None:
        """settings 비었으면 disabled 기본값."""
        from app.scheduler.jitter import resolve_module_jitter
        assert resolve_module_jitter({})["enabled"] is False
        assert resolve_module_jitter(None)["enabled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
