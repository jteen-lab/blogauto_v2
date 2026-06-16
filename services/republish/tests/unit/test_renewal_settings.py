"""재발행 리뉴얼 설정 정규화 테스트 (P1)."""
import pytest

from app.routers.blog_settings_renewal import (
    RenewalSettingsRequest,
    _normalize_config,
)


def test_defaults():
    cfg = _normalize_config(RenewalSettingsRequest())
    assert cfg == {
        "default_period_months": 6,
        "title_mode": "keep",
        "delete_grace_days": 7,
        "category_periods": {},
    }


def test_category_periods_clamp_and_drop():
    """0 이하는 제외, 120 초과는 클램프, 정상은 유지."""
    req = RenewalSettingsRequest(
        default_period_months=12,
        title_mode="recombine",
        delete_grace_days=0,
        category_periods={"5": 3, "7": 0, "9": 200},
    )
    cfg = _normalize_config(req)
    assert cfg["category_periods"] == {"5": 3, "9": 120}
    assert cfg["title_mode"] == "recombine"
    assert cfg["default_period_months"] == 12


def test_invalid_title_mode_rejected_by_schema():
    """제목 모드는 keep|recombine만 허용(스키마 검증)."""
    with pytest.raises(Exception):
        RenewalSettingsRequest(title_mode="other")


def test_period_range_enforced_by_schema():
    """기본 주기 1~120개월 범위 강제."""
    with pytest.raises(Exception):
        RenewalSettingsRequest(default_period_months=0)
    with pytest.raises(Exception):
        RenewalSettingsRequest(default_period_months=200)
