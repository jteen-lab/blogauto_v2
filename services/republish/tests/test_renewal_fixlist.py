"""고칠 글 목록 — 내용 문제만 담고, 고치면 빠지는지 시험."""
from app.services.renewal import renewal_fixlist as fx


def test_내용_문제만_고칠_글이다():
    assert fx.fact_reason("사실 관문 통과 못 함 — 사실 관문 보류: 금액 — 고친 뒤에도 틀린 문장 5개")
    assert fx.fact_reason("사실 관문 통과 못 함 — 사실 관문 보류: 사실 검사 호출 실패") is None
    assert fx.fact_reason("사실 관문 통과 못 함 — 법령 — 재검사 실패") is None
    assert fx.fact_reason("본문이 줄거나 짧아 갱신 안 함") is None
    assert fx.fact_reason(None) is None


def test_닫은_글은_빠지고_다시_막히면_돌아온다():
    a = {"post": 1, "reason": "첫째"}
    b = {"post": 2, "reason": "둘째"}
    assert {r["post"] for r in fx.open_items([a, b, {"post": 1, "closed": True}])} == {2}
    again = {"post": 1, "reason": "또"}
    got = fx.open_items([a, {"post": 1, "closed": True}, again])
    assert got == [again]


def test_같은_글은_마지막_줄만():
    got = fx.open_items([{"post": 1, "reason": "옛"}, {"post": 1, "reason": "새"}])
    assert [r["reason"] for r in got] == ["새"]
