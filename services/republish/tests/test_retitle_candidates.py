"""제목 재조합 후보 — 검색어 맞추기·유입 판정 시험."""
from app.services.renewal import retitle_candidates as rc


def _row(url: str = "https://a.com/12/", clicks: int = 0) -> rc.Row:
    return rc.Row(1, "제목", url, None, "found", 0, clicks)


def test_제목에_든_검색어를_큰_순으로():
    got = rc.match_keywords("삼성카드 무이자 할부 신청방법",
                            {"삼성카드 무이자": 500, "무이자할부": 4000, "운전면허": 9000})
    assert [k["keyword"] for k in got] == ["무이자할부", "삼성카드 무이자"]
    assert got[0]["band"] == "B" and got[1]["band"] == "A"
    assert got[1]["lead"] is True and got[0]["lead"] is False


def test_낱말이_떨어져_있어도_찾고_짧은_말은_뺀다():
    got = rc.match_keywords("전기차 올해 보조금 정리", {"전기차 보조금": 300, "적금": 9000})
    assert [k["keyword"] for k in got] == ["전기차 보조금"]


def test_같은_말은_한_번만_상위_다섯까지():
    vols = {"전기차 보조금": 300, "전기차보조금": 500}
    assert [k["volume"] for k in rc.match_keywords("전기차 보조금", vols)] == [500]
    many = {f"긴검색어{i}": i + 100 for i in range(9)}
    assert len(rc.match_keywords(" ".join(many), many)) == rc.TOP_KEYWORDS


def test_유입이나_클릭이_있으면_후보가_아니다():
    assert rc.has_no_search(_row(), {}) is True
    assert rc.has_no_search(_row(), {"/12/": 3}) is False
    assert rc.has_no_search(_row(clicks=1), {}) is False
    assert rc.has_no_search(_row("https://a.com/2026/09/Abc.html"), {"/2026/09/abc.html/": 2}) is False
