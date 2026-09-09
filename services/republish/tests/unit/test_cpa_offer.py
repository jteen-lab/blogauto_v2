"""CPA 오퍼 — 확인하지 않은 오퍼로 글을 만들지 않는다.

애드릭스 프로모션 페이지는 로그인해야 열려 크롤이 안 된다(2026-09-08 실측).
사람이 복사한 원문을 받는다. 원문의 애드릭스 고정 서식은 7건 모두 같은
모양이라 AI 없이 규칙으로 뽑는다.
"""
import pathlib

import pytest

from app.models.cpa_offer import (
    CpaOffer, RULE_SCOPES, RULE_TYPES, ST_ACTIVE, ST_DRAFT, default_recheck,
)
from app.services.cpa.offer_parser import (
    intake_fields, offer_name, parse, reject_reasons,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]

# 실제 오퍼 원문 일부. 형식이 이렇게 온다.
SAMPLE = """# 개인회생/파산 법률사무소
[개인회생/파산 법률사무소] CPA캠페인입니다.

7. '무료', '전문, 전담' 키워드 금지
전환 정보
미승인 DB조건 : 오류, 중복, 장기부재, 상담거절, 장난DB, 본인아님
접수 항목
＊ 이름
 
＊ 핸드폰번호
 
＊ 채무총액
 
대가성 문구 표시
ex)
이 포스팅은 애드릭스 수익이 발생합니다.

- 기존 : 첫부분 또는 끝부분에 게재 -> 변경 : 게시물의 내용 첫 부분에 대가성 문구 표시 또는 제목에 공개(제목 앞에 [광고] 표시)
"""


class TestName:
    """오퍼를 구분 못하면 규칙도 못 붙인다."""

    @pytest.mark.parametrize("line,expected", [
        ("# 부산ㅎr늘안과 라식/라섹", "부산ㅎr늘안과 라식/라섹"),
        ("[법무법인 서앤율 이혼] CPA 캠페인 입니다.", "법무법인 서앤율 이혼"),
        ("[주식매입자금대출 야호스탁론] CPA캠페인입니다.", "주식매입자금대출 야호스탁론"),
        ("[신차 비교견적 카바딜러] CPA 캠페인입니다.", "신차 비교견적 카바딜러"),
        # 대괄호가 이름의 앞머리인 경우 — 떼면 오퍼를 구분할 수 없다
        ("[자격증]산지식물자원관리사 CPA 진행합니다.", "[자격증]산지식물자원관리사"),
    ])
    def test_real_headers(self, line, expected):
        assert offer_name(line) == expected


class TestRejectReasons:
    """미승인 조건을 모르면 헛수고할 트래픽을 부른다."""

    def test_two_label_forms(self):
        """'미승인조건'과 '미승인 DB조건' 둘 다 쓰인다."""
        assert reject_reasons("미승인조건 : 오류, 중복") == ["오류", "중복"]
        assert reject_reasons("미승인 DB조건 : 오류, 중복") == ["오류", "중복"]

    def test_parentheses_are_not_split(self):
        """'나이제한(24세미만,55세이상)' 은 하나다."""
        found = reject_reasons(
            "미승인조건 : 오류, 장기부재(3회이상), 나이제한(24세미만,55세이상)")
        assert found == ["오류", "장기부재(3회이상)", "나이제한(24세미만,55세이상)"]

    def test_absent(self):
        assert reject_reasons("아무것도 없음") == []


class TestIntakeFields:
    """접수 항목이 글에서 무엇을 안내해야 하는지를 정한다."""

    def test_fullwidth_star(self):
        assert intake_fields(SAMPLE) == ["이름", "핸드폰번호", "채무총액"]

    def test_choices_are_not_fields(self):
        """'- 가정이사' 는 항목이 아니라 값이다."""
        text = ("접수 항목\n＊ 이사종류\n- 가정이사\n- 소형이사(원룸)\n"
                "＊ 도착지\n대가성 문구 표시\n")
        assert intake_fields(text) == ["이사종류", "도착지"]

    def test_stops_at_ftc_section(self):
        assert "이 포스팅은 애드릭스 수익이 발생합니다." not in intake_fields(SAMPLE)


class TestFtcNotice:
    """표시하지 않으면 위법이다. 7건 모두 같은 안내가 붙어 있다."""

    def test_extracted(self):
        assert parse(SAMPLE)["ftc_notice"] == "이 포스팅은 애드릭스 수익이 발생합니다."

    def test_position_follows_2024_revision(self):
        """끝부분 게재가 막혔다(2024-12-01 개정)."""
        assert parse(SAMPLE)["notice_position"] == "title_or_body_start"


class TestParseReport:
    def test_reports_what_it_found(self):
        """무엇이 비었는지 화면이 말해야 사람이 채운다."""
        found = parse(SAMPLE)["found"]
        assert set(found) == {"캠페인명", "미승인조건", "접수항목", "대가성문구"}

    def test_empty_offer_does_not_crash(self):
        """금지사항이 아예 없는 오퍼가 7건 중 3건이었다."""
        out = parse("[카바딜러] CPA 캠페인입니다.\n소개만 있습니다.")
        assert out["name"] == "카바딜러"
        assert out["conversion"]["fields"] == []


class TestUsability:
    """확인하지 않았거나 기한이 지난 오퍼로는 글을 만들지 않는다."""

    def _offer(self, **kw):
        base = dict(name="테스트", raw_text="x" * 30, status=ST_DRAFT,
                    recheck_due=default_recheck(30))
        base.update(kw)
        return CpaOffer(**base)

    def test_draft_is_not_usable(self):
        assert self._offer().usable is False

    def test_confirmed_is_usable(self):
        assert self._offer(status=ST_ACTIVE).usable is True

    def test_overdue_blocks_even_when_active(self):
        """조건이 바뀌어도 우리는 모른다. 기한이 유일한 방어다."""
        offer = self._offer(status=ST_ACTIVE, recheck_due=default_recheck(-1))
        assert offer.overdue is True
        assert offer.usable is False

    def test_no_due_date_never_expires(self):
        assert self._offer(status=ST_ACTIVE, recheck_due=None).usable is True


class TestCoverage:
    """규칙으로 바뀌지 않은 문장은 검사되지 않는다. 그 사실을 숨기지 않는다."""

    def test_none_when_nothing_parsed(self):
        offer = CpaOffer(name="x", raw_text="y", rules=[], unmatched=[])
        assert offer.coverage is None

    def test_ratio(self):
        offer = CpaOffer(name="x", raw_text="y",
                         rules=[{}] * 8, unmatched=["a", "b"])
        assert offer.coverage == 0.8

    def test_severity_counts(self):
        offer = CpaOffer(name="x", raw_text="y", rules=[
            {"severity": "block"}, {"severity": "block"},
            {"severity": "warn"}, {},
        ])
        counts = offer.counts()
        assert counts["block"] == 3  # 기본값이 block
        assert counts["warn"] == 1

    def test_advisories_surface(self):
        offer = CpaOffer(name="x", raw_text="y", rules=[
            {"type": "advisory"}, {"type": "must_include"},
        ])
        assert len(offer.advisories()) == 1


class TestTaxonomy:
    """실제 오퍼 7건 80건의 규칙에서 얻은 유형 집합."""

    def test_types_cover_the_seven_offers(self):
        for needed in ("must_include", "must_not_include", "required_topic",
                       "forbidden_topic", "link_policy", "conditional",
                       "channel", "asset", "conversion", "advisory"):
            assert needed in RULE_TYPES

    def test_scope_exists(self):
        """스탁론은 '금리'를 금지하면서 본문에 '월 0.4%대'를 쓴다."""
        assert "keywords" in RULE_SCOPES and "body" in RULE_SCOPES


class TestScreen:
    HTML = (ROOT / "app/templates/collection/_cpa_offers.html").read_text(encoding="utf-8")

    def test_lives_in_data_management(self):
        """별도 페이지가 아니라 데이터 관리의 한 탭이다.

        화면을 따로 두면 기존 흐름 밖에 새 로직이 생긴다(2026-09-09 정리).
        """
        base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
        assert 'href="/cpa"' not in base
        page = (ROOT / "app/templates/collection/index.html").read_text(
            encoding="utf-8")
        assert "_cpa_offers.html" in page

    def test_warns_when_no_rules(self):
        """규칙 0건이면 검사가 거의 없다는 것을 밝혀야 한다."""
        assert "지금은 검사가 거의 없습니다" in self.HTML

    def test_shows_coverage_and_unmatched(self):
        assert "커버리지" in self.HTML
        assert "미분류 문장" in self.HTML

    def test_warns_missing_ftc_notice(self):
        assert "표시하지 않으면 위법입니다" in self.HTML

    def test_paste_is_raw(self):
        assert "가공하지 말고 그대로" in self.HTML
