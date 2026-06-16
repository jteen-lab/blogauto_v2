"""리뉴얼 계획 결정 테스트 (P2b 순수 로직)."""
from app.services.renewal.renewal_plan import decide_renewal_plan


def test_keep_blogauto_reuses_image():
    p = decide_renewal_plan("keep", True, "blogauto", "https://i.ibb.co/x.webp")
    assert p.recombine_title is False
    assert p.image_action == "reuse"
    assert p.reuse_image_url == "https://i.ibb.co/x.webp"


def test_recombine_always_new_image():
    p = decide_renewal_plan("recombine", True, "blogauto", "https://i.ibb.co/x.webp")
    assert p.recombine_title is True
    assert p.image_action == "new"


def test_legacy_post_new_image_even_if_keep():
    p = decide_renewal_plan("keep", False, "legacy", "https://x/legacy.jpg")
    assert p.recombine_title is False
    assert p.image_action == "new"


def test_blogauto_post_but_legacy_image_new():
    # blogauto 글이어도 이미지가 legacy면 현재 양식 위해 새로 생성
    p = decide_renewal_plan("keep", True, "legacy", "https://x/old.jpg")
    assert p.image_action == "new"


def test_keep_blogauto_but_no_image_new():
    p = decide_renewal_plan("keep", True, "none", "")
    assert p.image_action == "new"
