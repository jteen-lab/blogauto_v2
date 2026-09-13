"""상황 추출 — 주제를 가르는 것은 니치가 아니라 조건이다."""
from app.services.keyword_lab import situation as S


class TestExtract:
    def test_수치_조건을_뽑는다(self):
        got = S.extract("15평 투룸에서 32평 아파트로 이사합니다")
        assert "15평" in got.signals
        assert "30평" in got.signals          # 32 → 5단위로 뭉갬
        assert got.has_move

    def test_층수는_그대로_남긴다(self):
        got = S.extract("2층에서 3층으로 옮기는데 엘리베이터가 없어요")
        assert "2층" in got.signals
        assert "3층" in got.signals

    def test_없음_조건을_뽑는다(self):
        got = S.extract("엘리베이터가 없는 빌라입니다")
        assert any(s.startswith("-") for s in got.signals)

    def test_금액은_구간으로_뭉갠다(self):
        a = S.extract("견적이 70만원 나왔어요")
        b = S.extract("견적이 89만원 나왔어요")
        assert a.signals == b.signals == ["50만원"]

    def test_흔한_말은_신호가_아니다(self):
        got = S.extract("이사 견적이 없어서 궁금합니다")
        assert "-이사" not in got.signals
        assert "-견적" not in got.signals

    def test_신호가_없으면_빈_상황(self):
        got = S.extract("이사 견적 어떻게 하나요")
        assert got.signals == []
        assert not got.is_concrete


class TestConcrete:
    def test_신호_둘이면_구체적이다(self):
        assert S.extract("2층에서 3층, 장롱 3짝").is_concrete

    def test_이동_하나만으로는_부족하다(self):
        got = S.extract("여기에서 저기로 갑니다")
        assert not got.is_concrete

    def test_이동에_신호_하나면_구체적이다(self):
        assert S.extract("파주에서 부산으로 1톤 이사").is_concrete


class TestFingerprint:
    def test_같은_상황은_같은_지문(self):
        a = S.extract("2층에서 3층으로, 엘리베이터 없음")
        b = S.extract("엘리베이터 없는데 3층에서 2층으로 갑니다")
        assert a.fingerprint() == b.fingerprint()

    def test_다른_상황은_다른_지문(self):
        a = S.extract("15평에서 32평으로 이사")
        b = S.extract("2층에서 3층으로 이사")
        assert a.fingerprint() != b.fingerprint()

    def test_빈_상황은_지문이_없다(self):
        assert S.extract("이사 견적").fingerprint() == ""


class TestDedupe:
    def test_이미_쓴_상황은_뺀다(self):
        first = S.extract("2층에서 3층, 장롱 3짝")
        again = S.extract("장롱 3짝인데 2층에서 3층")
        kept = S.dedupe([again], known=[first.fingerprint()])
        assert kept == []

    def test_새_상황은_남긴다(self):
        old = S.extract("2층에서 3층, 장롱 3짝")
        new = S.extract("15평에서 32평, 5톤 차량")
        kept = S.dedupe([new], known=[old.fingerprint()])
        assert len(kept) == 1

    def test_같은_배치_안에서도_중복을_제거한다(self):
        a = S.extract("2층에서 3층, 장롱 3짝")
        b = S.extract("장롱 3짝 2층에서 3층입니다")
        assert len(S.dedupe([a, b])) == 1

    def test_구체적이지_않으면_뺀다(self):
        assert S.dedupe([S.extract("이사 견적 얼마")]) == []


class TestSummarize:
    def test_신호_빈도를_센다(self):
        items = [S.extract("2층에서 3층, 장롱 3짝"),
                 S.extract("2층 빌라인데 엘리베이터 없음")]
        got = S.summarize(items)
        assert got.get("2층") == 2
