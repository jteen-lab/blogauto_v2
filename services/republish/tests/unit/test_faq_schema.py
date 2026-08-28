"""A5 FAQPage 스키마 테스트.

핵심 불변식: **JSON-LD 의 문자열은 본문에 보이는 텍스트와 같아야 한다.**
마크업에만 있고 화면에 없는 FAQ 는 스팸 판정 대상이다.
"""
import json

from app.services.publishing import faq_schema

# 운영 DB에서 확인한 실제 생성 포맷
REAL_BODY = """
<h3 id="4-준비-서류">4. 준비 서류</h3>
<ul><li>신분증</li></ul>
<h3 id="5-자주-묻는-질문-FAQ">5. 자주 묻는 질문 (FAQ)</h3>
<p><strong>Q1: 월세 환급금은 얼마나 받을 수 있나요?</strong></p>
<p>A1: 환급 금액은 월세의 일정 비율로, 소득에 따라 차등 지급됩니다.</p>
<p><strong>Q2: 이미 신청했는데 결과를 어떻게 확인하나요?</strong></p>
<p>A2: 신청 후에는 관련 포털 사이트에서 진행 상황을 확인할 수 있습니다.</p>
<p><strong>Q3: 환급금은 언제 지급되나요?</strong></p>
<p>A3: 일반적으로 신청 후 1~2개월 이내에 환급이 이루어집니다.</p>
<hr/>
<p>마무리 문단입니다.</p>
<h4 id="함께-보면-좋은-글">함께 보면 좋은 글</h4>
<p><a href="https://example.com/1/">다른 글</a></p>
"""


def test_extracts_three_pairs_from_real_format():
    pairs = faq_schema.extract_pairs(REAL_BODY)
    assert len(pairs) == 3
    assert pairs[0][0] == "월세 환급금은 얼마나 받을 수 있나요?"
    assert pairs[0][1].startswith("환급 금액은 월세의 일정 비율로")


def test_labels_are_stripped():
    """Q1: / A1: 는 번호 표식이라 떼도 본문 문자열이 그대로 남는다."""
    pairs = faq_schema.extract_pairs(REAL_BODY)
    assert not any(q.startswith("Q") and q[1:2].isdigit() for q, _ in pairs)
    assert not any(a.startswith("A") and a[1:2].isdigit() for _, a in pairs)


def test_stops_at_hr_boundary():
    """FAQ 블록 뒤 마무리 문단·관련글이 답변으로 섞이면 안 된다."""
    pairs = faq_schema.extract_pairs(REAL_BODY)
    joined = " ".join(a for _, a in pairs)
    assert "마무리 문단" not in joined
    assert "다른 글" not in joined


def test_jsonld_text_matches_visible_text():
    """가장 중요한 불변식 — 스키마 문자열이 본문에 실제로 존재해야 한다."""
    result = faq_schema.inject(REAL_BODY)
    payload = json.loads(
        result.split('<script type="application/ld+json">')[1].split("</script>")[0],
    )
    for entity in payload["mainEntity"]:
        assert entity["name"] in REAL_BODY
        assert entity["acceptedAnswer"]["text"] in REAL_BODY


def test_jsonld_shape():
    payload = json.loads(faq_schema.build_jsonld(
        [("질문1", "답변1"), ("질문2", "답변2")],
    ))
    assert payload["@type"] == "FAQPage"
    assert payload["mainEntity"][0]["@type"] == "Question"
    assert payload["mainEntity"][0]["acceptedAnswer"]["@type"] == "Answer"


def test_no_faq_block_returns_original():
    body = "<h2>본문</h2><p>FAQ 없음</p>"
    assert faq_schema.inject(body) == body


def test_single_pair_is_not_enough():
    body = (
        "<h3>자주 묻는 질문</h3>"
        "<p><strong>Q1: 하나뿐인가요?</strong></p><p>A1: 네.</p>"
    )
    assert faq_schema.inject(body) == body


def test_does_not_double_inject():
    once = faq_schema.inject(REAL_BODY)
    assert faq_schema.inject(once) == once
    assert once.count("application/ld+json") == 1


def test_faq_heading_variants():
    for heading in ("자주 묻는 질문", "FAQ", "자주묻는질문", "6. FAQ (자주 묻는 질문)"):
        body = (
            f"<h2>{heading}</h2>"
            "<p><strong>질문 1: 가능한가요?</strong></p><p>답변 1: 됩니다.</p>"
            "<p><strong>질문 2: 얼마인가요?</strong></p><p>답변 2: 무료입니다.</p>"
        )
        pairs = faq_schema.extract_pairs(body)
        assert len(pairs) == 2, heading
        assert pairs[0][0] == "가능한가요?"


def test_html_entities_are_unescaped():
    body = (
        "<h3>자주 묻는 질문</h3>"
        "<p><strong>Q1: A&amp;B는 어떻게 하나요?</strong></p>"
        "<p>A1: &quot;그대로&quot; 두세요.</p>"
        "<p><strong>Q2: 두번째?</strong></p><p>A2: 네.</p>"
    )
    pairs = faq_schema.extract_pairs(body)
    assert pairs[0][0] == "A&B는 어떻게 하나요?"
    assert '"그대로"' in pairs[0][1]


def test_empty_input():
    assert faq_schema.inject("") == ""
    assert faq_schema.extract_pairs("") == []
