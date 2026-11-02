"""D 방식 제목 거르기 — 규칙·AI 답 읽기·판정·사이트 점수·채우기 차례(2026-11-02)."""
from datetime import date

from app.services.title_screen import extract, filler, judge, rules, sites
from app.services.title_screen.inventory import BlogStock


def test_rules_drop_examples() -> None:
    """마케팅 표의 실제 예는 버린다."""
    cases = {
        "○○ 주가 전망": "stock",
        "[천안 맛집] 미미제면소 만두": "restaurant",
        "MiSTer FPGA 사용자용 Cave 게임 모음집": "game",
        "[실시간 e뉴스] 문틈으로 철사가 '쑥'…": "news",
        "본사직영 파인라인 스트레치 쉘 PAMAP745038": "model_list",
        "우리은행 희망플러스 신용대출 금리 한도": "loan_product",
        "2024년 11월 이번달 월간별자리운세": "past_year",
        "신평면 금천리 이삿짐센터 추천": "town_list",
        "그램프로16키스킨 구매 예정이신가요?": "product_list",
        "수원 장례식화환 당일 제작 배송": "town_list",
        "서울 강동구 근조화환 빈소 직접 전달": "town_list",
    }
    for title, why in cases.items():
        assert rules.junk_reason(title, date(2026, 11, 2)) == why, title


def test_rules_lon_narrow() -> None:
    """'론' 은 대출 상품만 — 메론·금융론·이론·토론은 통과."""
    for ok in ("메론 효능", "부동산금융론 강의 정리", "행동경제학 이론 쉽게", "토론 잘하는 법",
               "윈도우11 KB5031455 업데이트 오류", "국민연금 수령나이 출생연도별 기준"):
        assert rules.junk_reason(ok, date(2026, 11, 2)) is None, ok
    for bad in ("햇살론 신청 조건", "사잇돌론 한도", "비상금론 금리", "새희망론 금리 비교"):
        assert rules.junk_reason(bad) == "loan_product", bad


def test_fingerprint_and_site_key() -> None:
    """지문은 공백 무시, 네이버 블로그는 아이디까지."""
    assert rules.fingerprint("국민연금 수령 나이") == rules.fingerprint("국민연금수령나이")
    assert rules.site_key("https://m.blog.naver.com/PostView.naver?blogId=chlwjr&logNo=1") == \
        "blog.naver.com/chlwjr"
    assert rules.site_key("https://blog.naver.com/bluebeat/2233") == "blog.naver.com/bluebeat"
    assert rules.site_key("https://www.recelo.tistory.com/12") == "recelo.tistory.com"


def test_keyword_junk() -> None:
    """검색어 버릴 말."""
    assert rules.keyword_junk("동학사맛집") == "junk_word"
    assert rules.keyword_junk("오늘 좋아하게 되었습니다") == "broken_spacing"
    assert rules.keyword_junk("DTSWISS") == "not_korean"
    assert rules.keyword_junk("국민연금수령나이") is None


def test_parse_titles() -> None:
    """AI 답 읽기 — 칸 번호가 목록 밖이면 칸 없음."""
    text = "답: {\"1\": [[\"국민연금 수령시기\", \"국민연금 수령나이\"], 105], \"2\": [[\"코사무이\"], 999]}"
    out = extract.parse_titles(text, 2, [105])
    assert out[0].candidates == ["국민연금 수령시기", "국민연금 수령나이"]
    assert out[0].subtopic_id == 105
    assert out[1].subtopic_id is None
    assert extract.parse_keywords("1|105\n2|0", 2, [105]) == {0: 105, 1: None}


def test_judge_biggest_and_rules() -> None:
    """가장 큰 말 채택, 500 기준, 칸 없음·사이트 이름·못 잼."""
    p = extract.Picked(["국민연금 수령시기", "국민연금 수령나이"], 105)
    v = judge.judge(p, {"국민연금수령시기": 10, "국민연금수령나이": 56260})
    assert (v.result, v.keyword, v.volume) == (judge.PASS, "국민연금 수령나이", 56260)
    assert judge.judge(extract.Picked(["시댁선물"], 44), {"시댁선물": 240}).reason == "low_volume"
    assert judge.judge(extract.Picked(["코사무이"], None), {"코사무이": 10630}).reason == \
        "off_niche"
    assert judge.judge(extract.Picked(["알바천국"], 63), {"알바천국": 1041000}).result == \
        judge.HOLD
    assert judge.judge(None, {}).result == judge.SKIP
    assert judge.judge(extract.Picked(["없는말"], 63), {}).result == judge.SKIP


def test_site_judge() -> None:
    """20개+ & 10% 미만 차단, 30%+ 우선."""
    assert sites.judge(25, 1) == "blocked"
    assert sites.judge(19, 0) == "normal"
    assert sites.judge(12, 4) == "priority"
    assert sites.judge(40, 8) == "normal"


def _stock(bid: int, days: float) -> BlogStock:
    return BlogStock(bid, f"b{bid}", 1, days, 100.0, [bid])


def test_filler_order_and_stall(tmp_path, monkeypatch) -> None:
    """가장 적은 블로그부터, 45일 치면 다음, 3회차 안 늘면 멈춤."""
    monkeypatch.setattr(filler, "STALL_LOG", tmp_path / "stall.jsonl")
    state: dict = {}
    cur = filler._advance(state, [_stock(1, 5), _stock(2, 12), _stock(3, 80)])
    assert cur.blog_id == 1
    for _ in range(3):
        cur = filler._advance(state, [_stock(1, 5), _stock(2, 12), _stock(3, 80)])
    assert cur.blog_id == 2 and "1" in state["stalled"]
    assert (tmp_path / "stall.jsonl").exists()
    cur = filler._advance(state, [_stock(1, 5), _stock(2, 50), _stock(3, 80)])
    assert cur is None


def test_pick_conditions_skip_screened() -> None:
    """거름·보류는 스위치와 상관없이 고를 때 빠진다."""
    from app.services.generation import title_pick_order as pick

    sql = str(pick.conditions(pick.NONE)[0])
    assert "screen_result" in sql
    assert len(pick.order(pick.NONE)) == 3
