"""사실 관문(F1 주소·F3 말투·F2 사실)·O1~O3 — 슈마즈 2026-10-20."""
import asyncio
from types import SimpleNamespace

from app.services.generation import fact_gate as fg
from app.services.generation import hold_retry
from app.services.generation import official_hold as oh
from app.services.generation.fact_gate import fact_check as f2
from app.services.generation.fact_gate import polite_tone as f3
from app.services.generation.fact_gate import url_allowlist as f1
from app.services.reference import official_seeds as seeds


def _scrub(md, refs=()):
    return asyncio.run(f1.scrub(md, list(refs), None, check_alive=False))


# ── F1 ──────────────────────────────────────────────
def test_f1_removes_fake_address_keeps_org_name():
    out, removed = _scrub("예금보험공사 (www.dic.go.kr)에서 확인하세요.")
    assert out == "예금보험공사에서 확인하세요."
    assert removed[0]["url"] == "www.dic.go.kr"


def test_f1_keeps_allowlisted_and_subdomains():
    md = "금감원(https://finlife.fss.or.kr/x) 과 [국세청](https://www.nts.go.kr/a)"
    out, removed = _scrub(md)
    assert out == md and removed == []


def test_f1_markdown_link_becomes_text():
    out, removed = _scrub("[통합연금포털](https://www.all-pension.or.kr) 참고")
    assert out == "통합연금포털 참고" and len(removed) == 1


def test_f1_reference_url_is_kept():
    md = "자료: https://blog.example.com/post/1"
    out, removed = _scrub(md, ["https://blog.example.com/post/1/"])
    assert out == md and not removed


def test_f1_label_colon_cleanup_and_email_untouched():
    out, _ = _scrub("- 올연금: all-pension.or.kr\n문의 help@kdic.or.kr")
    assert out == "- 올연금\n문의 help@kdic.or.kr"


def test_f1_dead_link_removed(monkeypatch):
    async def dead(url, cache):
        return False
    monkeypatch.setattr(f1, "_alive", dead)
    out, removed = asyncio.run(f1.scrub("국세청(www.nts.go.kr/x)", [], None, True))
    assert out == "국세청" and removed[0]["why"] == "열리지 않음"


# ── F3 ──────────────────────────────────────────────
def test_f3_ratio_counts_plain_da_only():
    md = "이것은 예시입니다. 한도는 1억 원이다. 확인해 보세요.\n## 제목이다.\n| 표다. |"
    r, da, total = f3.ratio(md)
    assert (da, total) == (1, 3)


def test_f3_directive_once():
    once = f3.with_directive("규칙")
    assert f3.DIRECTIVE in once and f3.with_directive(once) == once


class AI:
    """정해진 답을 차례로 돌려주는 가짜 AI."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def generate(self, **kw):
        self.calls.append(kw)
        return {"content": self.answers.pop(0)} if self.answers else None


def test_f3_rewrite_then_pass():
    bad = "한도는 1억 원이다. 지점 분산은 효과가 없다. 공식 누리집을 본다."
    good = "한도는 1억 원입니다. 지점 분산은 효과가 없습니다. 공식 누리집을 봅니다."
    md, reason, rec = asyncio.run(f3.enforce(AI(good), bad, "anthropic", "m", 100))
    assert md == good and reason is None and rec["rewritten"]


def test_f3_hold_when_still_plain():
    bad = "한도는 1억 원이다. 지점 분산은 효과가 없다."
    md, reason, _ = asyncio.run(f3.enforce(AI(bad), bad, "anthropic", "m", 100))
    assert reason and "말투" in reason


# ── F2 ──────────────────────────────────────────────
def test_f2_locate_fuzzy_and_apply():
    md = "신협은 **예금보험공사**가 보호합니다. 다른 문장입니다."
    out, done = f2.apply_fixes(md, [{"sentence": "신협은 예금보험공사가 보호합니다.",
                                     "replacement": "신협은 신협중앙회 예금자보호기금이 보호합니다."}])
    assert out.startswith("신협은 신협중앙회") and done[0]["applied"]


def test_f2_parse_json_fenced():
    assert f2.parse_json('```json\n{"items": []}\n```') == {"items": []}


def _ref(official=""):
    return SimpleNamespace(summaries=[], sources=["https://www.kdic.or.kr/a"],
                           official=official, digest="자료",
                           to_prompt_injection=lambda: "자료")


def _blog():
    return SimpleNamespace(ai_config={"writing_ai": {"provider": "anthropic",
                                                     "model": "claude-sonnet-5"}})


SET = {"fact_gate": {"fact_check": {"enabled": True}}}
ITEM = '{"items":[{"sentence":"신협은 예금보험공사가 보호합니다.","reason":"신협중앙회","confidence":"높음"}]}'


def test_f2_fix_then_pass():
    ai = AI(ITEM, '{"fixes":[{"sentence":"신협은 예금보험공사가 보호합니다.",'
                  '"replacement":"신협은 신협중앙회가 보호합니다."}]}', '{"items":[]}')
    out = asyncio.run(fg.run(ai, "신협은 예금보험공사가 보호합니다.", _ref(), SET, _blog(), "t"))
    assert out.hold_reason is None and out.markdown == "신협은 신협중앙회가 보호합니다."
    assert ai.calls[0]["model"] == "claude-haiku-4-5"
    assert ai.calls[1]["model"] == "claude-sonnet-5"


def test_f2_hold_when_high_remains():
    ai = AI(ITEM, '{"fixes":[]}', ITEM.replace("신협은 예금보험공사가 보호합니다.", "x"))
    out = asyncio.run(fg.run(ai, "신협은 예금보험공사가 보호합니다. 끝입니다.", _ref(), SET, _blog(), "t"))
    assert out.hold_reason and "사실 검사" in out.hold_reason


def test_f2_call_failure_does_not_block():
    out = asyncio.run(fg.run(AI(), "본문입니다.", _ref(), SET, _blog(), "t"))
    assert out.hold_reason is None and out.record["f2_error"]


def test_no_switch_is_unchanged():
    ai = AI()
    out = asyncio.run(fg.run(ai, "www.dic.go.kr 이다.", _ref(), {}, _blog(), "t"))
    assert out.markdown == "www.dic.go.kr 이다." and not ai.calls
    assert fg.with_prompt({"content_generation": {"system_prompt": "a"}}) == \
        {"content_generation": {"system_prompt": "a"}}


# ── O1 ──────────────────────────────────────────────
def test_o1_api_hit_counts_only_with_switch():
    ref = SimpleNamespace(summaries=[], sources=["https://blog.naver.com/x"], official="금감원 API")
    assert oh.count_official(ref, [".go.kr"], oh.api_counts({})) == 0
    on = {"fact_gate": {"official_api_counts": True}}
    assert oh.count_official(ref, [".go.kr"], oh.api_counts(on)) == 1


# ── O2 ──────────────────────────────────────────────
def test_o2_urls_for_matches_title_words():
    st = {"fact_gate": {"official_seeds": [
        {"keywords": ["예금자보호"], "urls": ["a", "b"]},
        {"keywords": ["배당소득세", "금융소득"], "urls": ["c"]}]}}
    assert seeds.urls_for(st, "예금자 보호 한도 1억") == ["a", "b"]
    assert seeds.urls_for(st, "배당소득세와 금융소득종합과세") == ["c"]
    assert seeds.urls_for({}, "예금자보호") == []


def test_o2_dense_text_skips_menu():
    menu = "".join(f'<a href="#">메뉴{i}</a>' for i in range(80))
    html = f"<body><div>{menu}</div><div class='c'>{'본문 ' * 100}</div></body>"
    assert seeds.dense_text(html).startswith("본문")


def test_o2_pick_puts_seeds_first():
    s, a, b = (SimpleNamespace(url=u) for u in ("s", "a", "b"))
    assert [d.url for d in seeds.pick([s], [a, s, b], 1)] == ["s", "a"]


# ── O3 ──────────────────────────────────────────────
def test_o3_switch_and_retry_picks_next():
    assert hold_retry.switch({}) == (False, 0)
    st = {"fact_gate": {"next_title_on_hold": {"enabled": True}}}
    calls = []

    class Trig:
        async def find_available_titles(self, blog_id, limit, module_settings):
            return [SimpleNamespace(id=1, last_held_at=None),
                    SimpleNamespace(id=2, last_held_at=None)]

    class Ex:
        inventory_trigger = Trig()

        async def execute_for_blog(self, module, blog, **kw):
            calls.append(kw["force_title_id"])
            return {"success": True, "skipped": False}

    res = asyncio.run(hold_retry.retry(Ex(), None, SimpleNamespace(id=15), None, True,
                                       st, "근거 부족으로 보류: x", (1,)))
    assert calls == [2] and res["held_titles"] == [1]
    assert asyncio.run(hold_retry.retry(Ex(), None, SimpleNamespace(id=15), None, True,
                                        st, "다른 실패", (1,))) is None


def test_f2_parse_json_newline_in_string():
    assert f2.parse_json('{"items":[{"sentence":"가\n나"}]}')["items"][0]["sentence"] == "가\n나"


def test_f2_facts_reach_check_and_fix_prompts():
    st = {"fact_gate": {"fact_check": {"enabled": True, "facts": ["예금자보호 한도는 1억 원"]}}}
    ai = AI(ITEM, '{"fixes":[]}', '{"items":[]}')
    asyncio.run(fg.run(ai, "신협은 예금보험공사가 보호합니다.", _ref(), st, _blog(), "t"))
    assert all("예금자보호 한도는 1억 원" in c["prompt"] for c in ai.calls)
    assert "확정 사실" not in f2.facts_block([])
