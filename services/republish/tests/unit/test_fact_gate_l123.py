"""L1 확인처 링크·L2 지시 문구 새어 나옴·L3 블로거 영어 주소 — 슈마즈 2026-10-22."""
import asyncio
from types import SimpleNamespace

from app.services.generation import fact_gate as fg
from app.services.generation.fact_gate import source_links as l1
from app.services.generation.fact_gate import template_leak as l2
from app.services.publishing import blogger_slug as l3

SECTION = (
    "## 어디서 확인하나\n\n"
    "- 예금보험공사: 예금자보호 한도와 보호 대상 금융회사 목록\n"
    "- 금융감독원 금융상품통합비교공시: 금융회사별 예·적금 조건 비교\n"
    "- **금융소비자 정보포털 파인(FINE)**: 건전성 공시\n"
    "- [국세청](https://www.nts.go.kr): 이미 링크\n"
    "- 가까운 은행 창구\n\n"
    "마무리 문장입니다.")


# ── L1 ──────────────────────────────────────────────
def test_l1_links_names_only_in_check_section():
    md = "## 한도\n\n- 예금보험공사: 1억 원\n\n" + SECTION
    out, n = l1.apply(md, {})
    assert "- 예금보험공사: 1억 원" in out  # 다른 소제목은 그대로
    assert "- [예금보험공사](https://www.kdic.or.kr): 예금자보호" in out
    assert "[금융감독원 금융상품통합비교공시](https://finlife.fss.or.kr)" in out
    assert "[**금융소비자 정보포털 파인(FINE)**](https://fine.fss.or.kr)" in out
    assert out.count("nts.go.kr") == 1 and "- 가까운 은행 창구" in out
    assert n == 3


def test_l1_skips_urls_outside_allowlist():
    cfg = {"links": [{"name": "가까운 은행", "url": "https://bank.example.com"}]}
    out, _ = l1.apply(SECTION, cfg, domains=["kdic.or.kr"])
    assert "example.com" not in out and "fss.or.kr" not in out
    assert "[예금보험공사](https://www.kdic.or.kr)" in out


# ── L2 ──────────────────────────────────────────────
def test_l2_removes_leaked_template_sentence():
    md = ("## 한도\n\n항목: 값으로 정리하면 다음과 같습니다.\n\n"
          "- 보호 한도: 1인당 1억 원\n"
          "앞 문장입니다. \"항목: 값\" 형태로 보면 이렇습니다. 뒤 문장입니다.")
    out, removed = l2.scrub(md)
    assert "항목: 값" not in out
    assert "- 보호 한도: 1인당 1억 원" in out
    assert "앞 문장입니다. 뒤 문장입니다." in out
    assert len(removed) == 2


def test_l2_directive_added_with_prompt_once():
    s = {"fact_gate": {"template_leak": {"enabled": True}},
         "content_generation": {"system_prompt": "기본"}}
    p = fg.with_prompt(fg.with_prompt(s))["content_generation"]["system_prompt"]
    assert p.count(l2.DIRECTIVE) == 1 and p.startswith("기본")


def test_gate_runs_l2_and_l1_when_switched_on():
    s = {"fact_gate": {"template_leak": {"enabled": True},
                       "source_links": {"enabled": True}}}
    md = "항목: 값으로 정리하면 다음과 같습니다.\n\n" + SECTION
    out = asyncio.run(fg.run(None, md, None, s, SimpleNamespace(
        id=15, ai_config={}), "제목"))
    assert "항목: 값" not in out.markdown and out.hold_reason is None
    assert out.record["l1_links"] == 3


def test_gate_off_keeps_text():
    out = asyncio.run(fg.run(None, SECTION, None, {}, None, "제목"))
    assert out.markdown == SECTION


# ── L3 ──────────────────────────────────────────────
def test_l3_enabled_only_with_switch():
    assert l3.enabled(SimpleNamespace(seo_config={"english_slug": {"enabled": True}}))
    assert not l3.enabled(SimpleNamespace(seo_config={}))
    assert not l3.enabled(SimpleNamespace(seo_config=None))


def test_l3_clean_slug():
    assert l3.clean("Deposit Insurance Limit 100-Million Won\n설명") == \
        "deposit-insurance-limit-100-million-won"
    assert l3.clean("예금자보호") == ""
    assert l3.clean("single") == ""
    assert len(l3.clean("-".join(["word"] * 30))) <= l3.MAX_LEN


def test_l3_make_returns_none_when_off():
    blog = SimpleNamespace(seo_config={}, name="x")
    assert asyncio.run(l3.make(None, blog, "제목")) is None
