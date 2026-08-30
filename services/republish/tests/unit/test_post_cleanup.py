"""발행글 정리 — 분류·하한·모드 (2026-08-30).

라이프인포 146개를 일회성 스크립트로 비공개했는데 같은 일이 12개 블로그에서
반복된다. 앱 기능으로 만들면서 가장 중요한 건 안전장치다 — 애드센스 승인
사이트에서 콘텐츠가 부족해지면 광고 게재가 중단될 수 있다.

순서도: docs/flowcharts/post_cleanup.md
"""
from types import SimpleNamespace

import pytest

from app.routers.post_cleanup import _min_remaining
from app.services.publishing.post_cleanup_service import (
    CATEGORIES,
    DEFAULT_MIN_REMAINING,
    MODE_DELETE,
    MODE_PRIVATE,
    PostItem,
    build_plan,
    classify,
    plain_len,
)


def _item(i: int, title: str, body_len: int = 3000) -> PostItem:
    code, label = classify(title)
    return PostItem(post_id=str(i), title=title, url=f"https://x.com/{i}/",
                    status="publish", body_len=body_len,
                    category=code, category_label=label)


# ── 분류 ────────────────────────────────────────────────
@pytest.mark.parametrize("title,expected", [
    ("롯데카드 고객센터 전화번호 확인하기", "contact"),
    ("쏘카 고객센터 번호는 어디서 찾을까", "contact"),
    ("금강제화 상품권 현금화 저렴한 곳은", "voucher"),
    ("부산 온누리상품권 사용처 안내", "voucher"),
    ("대한주택관리사협회 채용정보 안내", "job"),
    ("안산교차로 구인구직 사이트", "job"),
    ("창원시청 주차요금과 무료시간 안내", "facility"),
    ("목동 CGV 상영시간표와 좌석 팁", "facility"),
])
def test_known_low_value_types_detected(title, expected):
    """라이프인포에서 걷어낸 유형이 그대로 잡혀야 한다."""
    assert classify(title)[0] == expected


@pytest.mark.parametrize("title", [
    "소고기 미역국 황금 레시피",
    "윈도우 11 설치 순서 정리",
    "제주도 3박 4일 여행 코스",
])
def test_normal_posts_not_targeted(title):
    assert classify(title)[0] is None


def test_plain_len_strips_tags():
    assert plain_len("<p>안녕하세요</p><div>반갑습니다</div>") == 10


# ── 대상 선정 ────────────────────────────────────────────
def test_plan_selects_only_matching_types():
    posts = [_item(1, "고객센터 전화번호"), _item(2, "소고기 미역국 레시피"),
             _item(3, "상품권 현금화")]
    plan = build_plan(posts, min_remaining=0)
    assert len(plan.targets) == 2
    assert {t.post_id for t in plan.targets} == {"1", "3"}


def test_plan_can_limit_categories():
    """유형을 골라서 지울 수 있어야 한다."""
    posts = [_item(1, "고객센터 전화번호"), _item(2, "상품권 현금화")]
    plan = build_plan(posts, categories=["contact"], min_remaining=0)
    assert [t.post_id for t in plan.targets] == ["1"]


def test_short_body_included_when_requested():
    posts = [_item(1, "정상 제목", body_len=800),
             _item(2, "정상 제목", body_len=3000)]
    plan = build_plan(posts, min_body_len=1800, min_remaining=0)
    assert [t.post_id for t in plan.targets] == ["1"]
    assert "본문 800자" in plan.targets[0].reason


def test_reason_recorded_for_every_target():
    """왜 지워지는지 없으면 사용자가 판단할 수 없다."""
    posts = [_item(i, "고객센터 전화번호") for i in range(3)]
    plan = build_plan(posts, min_remaining=0)
    assert all(t.reason for t in plan.targets)


def test_by_category_summary():
    posts = [_item(1, "고객센터 전화번호"), _item(2, "고객센터 번호"),
             _item(3, "상품권 현금화")]
    plan = build_plan(posts, min_remaining=0)
    assert plan.by_category["고객센터·연락처"] == 2
    assert plan.by_category["상품권·현금화"] == 1


# ── 안전장치 ────────────────────────────────────────────
def test_floor_blocks_over_deletion():
    """승인 사이트를 비우면 광고 게재가 중단될 수 있다."""
    posts = ([_item(i, "고객센터 전화번호") for i in range(30)]
             + [_item(100 + i, "정상 제목") for i in range(90)])
    plan = build_plan(posts, min_remaining=100)
    assert plan.allowed is False
    assert "90개만 남습니다" in plan.block_reason
    assert "최대 20개" in plan.block_reason


def test_floor_allows_when_enough_remains():
    posts = ([_item(i, "고객센터 전화번호") for i in range(10)]
             + [_item(100 + i, "정상 제목") for i in range(150)])
    plan = build_plan(posts, min_remaining=100)
    assert plan.allowed is True and plan.remaining == 150


def test_zero_floor_allows_full_wipe():
    """미신청 블로그는 전체 삭제가 가능해야 한다."""
    posts = [_item(i, "고객센터 전화번호") for i in range(50)]
    plan = build_plan(posts, min_remaining=0)
    assert plan.allowed is True and plan.remaining == 0


# ── 하한 결정 ────────────────────────────────────────────
def _blog(status):
    return SimpleNamespace(adsense_status=status)


def test_approved_blog_gets_floor_by_default():
    assert _min_remaining(_blog("approved"), None) == DEFAULT_MIN_REMAINING


def test_unapproved_blog_has_no_floor():
    for s in ("none", "preparing", "applied"):
        assert _min_remaining(_blog(s), None) == 0


def test_approved_floor_cannot_be_lowered():
    """사용자가 낮춰 달라고 해도 승인 사이트는 기본값 아래로 못 내린다."""
    assert _min_remaining(_blog("approved"), 0) == DEFAULT_MIN_REMAINING
    assert _min_remaining(_blog("approved"), 10) == DEFAULT_MIN_REMAINING


def test_approved_floor_can_be_raised():
    assert _min_remaining(_blog("approved"), 300) == 300


def test_unapproved_floor_respected():
    assert _min_remaining(_blog("none"), 50) == 50


# ── 모드 ────────────────────────────────────────────────
def test_delete_mode_uses_force_for_410():
    """force=true 라야 휴지통이 아니라 410 Gone 이 된다.

    구글은 404 보다 410 에서 재크롤을 훨씬 빨리 멈춘다.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/services/publishing/post_cleanup_service.py").read_text(
        encoding="utf-8")
    assert '"force": "true"' in src
    assert MODE_PRIVATE == "private" and MODE_DELETE == "delete"


def test_blogger_uses_revert_for_private():
    """블로거에는 private 이 없어 초안으로 되돌린다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/services/publishing/post_cleanup_service.py").read_text(
        encoding="utf-8")
    assert "/revert" in src


def test_apply_endpoint_rechecks_floor():
    """미리보기를 건너뛰고 API 를 직접 부르는 것도 막아야 한다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/routers/post_cleanup.py").read_text(encoding="utf-8")
    assert "하한 재검사" in src
    assert "remaining < floor" in src


def test_categories_exposed_for_ui():
    """화면이 유형 목록을 하드코딩하지 않도록 API 가 내려준다."""
    assert len(CATEGORIES) == 4
    assert all(len(c) == 3 for c in CATEGORIES)


# ── 화면에서 고른 글 삭제 (2026-08-30) ────────────────────
# 데이터 관리 > 정식제목 탭에서 발행완료 목록을 보고 직접 골라 지운다.
# 대상 선정을 사람이 하므로 유형 분류는 쓰지 않지만 하한은 지킨다.

@pytest.mark.parametrize("url,expected", [
    ("https://doooit082.com/1998/", "1998"),
    ("https://doooit082.com/1998", "1998"),
    ("https://info.doooit082.com/253/", "253"),
    ("https://x.com/hello-world/", None),
    ("", None),
])
def test_wordpress_post_id_from_url(url, expected):
    """doooit082 계열은 글 번호를 URL 로 쓴다. 슬러그형이면 검색으로 찾는다."""
    from app.services.publishing.post_cleanup_service import (
        wordpress_post_id_from_url,
    )

    assert wordpress_post_id_from_url(url) == expected


def test_by_titles_endpoint_keeps_floor():
    """화면 경로도 승인 사이트 하한을 지켜야 한다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/routers/post_cleanup.py").read_text(encoding="utf-8")
    assert "by-titles" in src
    assert "최소" in src and "유지해야" in src


def test_by_titles_cleans_local_record():
    """블로그에서 지웠으면 우리 기록도 지워야 한다.

    남겨 두면 다음 크롤링까지 발행완료로 보이고, 내부링크가 사라진 글을
    가리킨다.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/routers/post_cleanup.py").read_text(encoding="utf-8")
    assert "db.delete(r)" in src
    # 실패한 것은 지우지 않는다
    assert "failed_urls" in src


def test_blogger_deletion_resolves_post_id_by_path():
    """블로거는 URL 로 바로 못 지운다 — path 로 postId 를 찾는다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "app/services/publishing/post_cleanup_service.py").read_text(
        encoding="utf-8")
    assert "posts/bypath" in src


def test_delete_button_only_in_published_view():
    """발행완료 목록에서만 뜨게 한다 — 다른 상태에는 지울 글이 없다."""
    from pathlib import Path

    html = (Path(__file__).resolve().parents[2]
            / "app/templates/collection/_titles_main.html").read_text(
        encoding="utf-8")
    assert "블로그에서 삭제" in html
    assert "stateFilter === 'published' && selectedBlogId" in html


def test_cleanup_flags_shown_in_list():
    """정리 권장 표시가 목록에 붙는지."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    html = (root / "app/templates/collection/_titles_main.html").read_text(
        encoding="utf-8")
    assert "cleanupFlags[row.id]" in html

    js = (root / "app/templates/collection/index.html").read_text(
        encoding="utf-8")
    assert "loadCleanupFlags" in js
    assert "cleanup/flags" in js


def test_delete_confirms_irreversible():
    """되돌릴 수 없다는 것을 눌리기 전에 알려야 한다."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[2]
          / "app/templates/collection/index.html").read_text(encoding="utf-8")
    assert "deleteFromBlog" in js
    assert "되돌릴 수 없습니다" in js
