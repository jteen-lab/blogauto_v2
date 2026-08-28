"""X5 디스커버 준비도 테스트.

원칙 검증:
    - 옵트인 기본값은 꺼짐(켜지 않으면 동작이 바뀌지 않는다)
    - 항목마다 조치 주체(앱/사용자)를 구분해 돌려준다
    - 작은 이미지를 통과시키지 않는다
"""
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.search_visibility import discover_service as ds
from app.services.search_visibility.config import merge_config


def _blog(**kw):
    base = dict(
        id=1, name="테스트", url="https://example.com",
        platform=SimpleNamespace(value="wordpress"),
        image_mode="template", overlay_config={}, author_profile={},
        search_index_config=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


# ---------- 옵트인 기본값 ----------

def test_discover_is_off_by_default():
    """켜지 않으면 어떤 동작도 바뀌지 않아야 한다."""
    config = merge_config(None)
    assert config["discover_enabled"] is False
    assert config["discover_block_on_fail"] is False
    assert config["discover_min_image_width"] == 1200


# ---------- 이미지 크기 ----------

def test_image_size_reads_png():
    assert ds._image_size(_png(1600, 900)) == (1600, 900)


def test_image_size_returns_none_for_garbage():
    assert ds._image_size(b"not an image") is None


# ---------- 템플릿 검사 ----------

def test_template_missing_is_user_action(tmp_path):
    item = ds.check_template(_blog(overlay_config={}), 1200)
    assert item.passed is False
    assert item.owner == ds.BY_USER


def test_template_too_small_fails_with_guidance(tmp_path, monkeypatch):
    path = tmp_path / "t.png"
    path.write_bytes(_png(500, 500))
    monkeypatch.setattr(ds, "template_path", lambda blog: path)

    item = ds.check_template(_blog(overlay_config={"template_image": "t.png"}), 1200)
    assert item.passed is False
    assert item.owner == ds.BY_USER
    assert "500×500" in item.detail
    assert "1600×900" in item.detail  # 권장 규격을 알려준다


def test_template_large_enough_passes(tmp_path, monkeypatch):
    path = tmp_path / "t.png"
    path.write_bytes(_png(1600, 900))
    monkeypatch.setattr(ds, "template_path", lambda blog: path)

    item = ds.check_template(_blog(overlay_config={"template_image": "t.png"}), 1200)
    assert item.passed is True


def test_non_template_mode_is_not_applicable():
    """AI 모드는 16:9 기본값이 이미 요건을 만족하므로 검사 대상이 아니다."""
    item = ds.check_template(_blog(image_mode="ai"), 1200)
    assert item.passed is None
    assert "검사 대상이 아닙니다" in item.detail


# ---------- 준비도 종합 ----------

@pytest.mark.asyncio
async def test_no_published_url_reports_reason():
    result = await ds.check_blog(_blog(), None)
    assert result.error is not None
    assert result.ready is False


def test_readiness_requires_all_items():
    r = ds.DiscoverReadiness(enabled=True, min_width=1200)
    r.items = [
        ds.CheckItem("a", "A", True, ds.BY_APP),
        ds.CheckItem("b", "B", False, ds.BY_USER),
    ]
    assert r.ready is False
    r.items[1].passed = True
    assert r.ready is True


def test_readiness_is_false_when_no_items():
    assert ds.DiscoverReadiness(enabled=True, min_width=1200).ready is False


def test_to_dict_exposes_owner_per_item():
    """코드로 못 고치는 항목을 사용자가 구분할 수 있어야 한다."""
    r = ds.DiscoverReadiness(enabled=False, min_width=1200)
    r.items = [ds.CheckItem("template", "템플릿", False, ds.BY_USER, "500×500")]
    body = r.to_dict()
    assert body["items"][0]["owner"] == "user"
    assert body["enabled"] is False
