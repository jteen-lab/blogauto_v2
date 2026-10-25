"""P3 돈 되는 정보 · 리뉴얼 성과 고르기·이미지만 바꾸기 (2026-10-25)."""
from datetime import datetime, timedelta, timezone

from app.services.generation import money_pick as mp
from app.services.renewal import renewal_ga as ga
from app.services.renewal import renewal_images as ri
from app.services.renewal import renewal_pick as rp
from app.services.renewal import renewal_record as rr


def test_money_titles():
    assert mp.is_money("삼성카드 연회비 면제 조건 정리")
    assert mp.is_money("실손보험 청구 서류와 기간")
    assert mp.is_money("연말정산 의료비 공제 받는 법")
    assert not mp.is_money("셀프염색 하는 방법")
    assert mp.wanted({"money_info_daily": 1}) == 1 and mp.wanted({}) == 0


def test_window_and_classify():
    assert ga.window_for(40) == 20 and ga.window_for(100) == 28 and ga.window_for(6) == 7
    assert ga.classify(None, False, False)[0] == "legacy"
    assert ga.classify(None, True, False)[0] == "rewrite"
    assert ga.classify(None, True, True)[0] == "augment"          # 보호 글은 재작성 금지
    down = ga.GaStat(naver_cur=10, naver_prev=30, sessions_cur=10, sessions_prev=30)
    assert ga.classify(down, True, False)[0] == "augment"
    keep = ga.GaStat(naver_cur=30, naver_prev=30, sessions_cur=30, sessions_prev=30)
    assert ga.classify(keep, True, False)[0] == "keep"


def _row(i, src, days_old, title="생활 꿀팁"):
    t = datetime.now(timezone.utc) - timedelta(days=days_old)
    return rp.Row(i, src, title, f"https://x.com/{i}/", t, None)


def test_pick_order_prefers_decline_then_zero_old_then_legacy():
    view = ga.GaView(40, 20, None, {1: ga.GaStat(5, 20, 5, 20), 2: ga.GaStat(9, 9, 9, 9)}, set())
    rows = [_row(1, "crawled", 900), _row(2, "crawled", 800), _row(3, "crawled", 700),
            _row(4, "crawled", 1000), _row(5, "generated", 400)]
    assert rp.pick_order(rows, view, 6)[:2] == (rows[0], "1-augment")
    view.stats.pop(1)
    r, stage, _ = rp.pick_order(rows, view, 6)
    assert stage == "3-rewrite" and r.id == 4            # GA 0 옛 글 중 가장 오래된 것
    view.coverage_days = 5                                # 수집 부족이면 0 으로 읽지 않음
    assert rp.pick_order(rows, view, 6)[1] == "4-legacy"


def test_blocked_titles_and_switch():
    assert rp.blocked_title("SBI저축은행 소액대출 한도")
    assert not rp.blocked_title("셀프염색 하는 방법")
    assert rp.enabled({"pick": "performance"}) and not rp.enabled({"enabled": True})


def test_strip_images_keeps_text():
    html = ('<p>앞</p><!-- wp:image {"id":1} --><figure class="wp-block-image"><img src="'
            'https://a.com/wp-content/uploads/2022/03/a.png"></figure><!-- /wp:image -->'
            '<p><img src="b.png"></p><p>뒤</p>')
    out = ri.strip_images(html)
    assert "<img" not in out and "앞" in out and "뒤" in out


def test_old_images_detected():
    h = '<img src="https://d.com/wp-content/uploads/2023/06/x.png"><img src="https://d.com/wp-content/uploads/2026/10/blogauto_1.webp">'
    assert rr.old_images(h) == ["https://d.com/wp-content/uploads/2023/06/x.png"]


def test_text_len_and_shrink_rule():
    assert rr.text_len("<p>가 나</p><!-- x --><img src='a'>") == 2
    assert rr.MIN_KEEP == 0.9


def test_new_image_is_injected_into_body():
    """템플릿 모드는 그림 파일만 준다 — 리뉴얼이 본문에 직접 넣어야 한다(10/25 미리보기 그림 0개)."""
    from pathlib import Path
    src = Path("app/services/renewal/renewal_generator.py").read_text()
    assert "if img.image_url not in html:" in src and "inject_featured(" in src
    src2 = Path("app/services/renewal/renewal_images.py").read_text()
    assert "inject_featured(" in src2
