"""리뉴얼 사실 관문 (2026-10-25 마케팅 검수, 형 '전부 적용').

미리보기 6편 중 4편에 사실 오류·지어낸 경험·근거 없는 일반화가 있었다. 보강(augment)은
원문을 믿고 늘리는 방식이라 옛 글의 틀린 전제(/1773 고추냉이=겨자무)를 그대로 키웠다.

  R1 규칙: 지어낸 1인칭 경험('저도'·'제 아이도'·'필자는')·'많은 사용자들이' 류 문장 지우기
  R2 검사: 다른 모델(기본 claude-sonnet-5)이 참고 자료·상식으로 틀린 문장과 **틀린 전제**를 뽑는다
  R3 고치기: '높음' 문장만 고쳐 쓴다(못 고치면 지움) → 다시 검사
  전제가 틀렸으면 경고로 끝내지 않고 호출측이 바로잡는 지시로 본문을 한 번 다시 쓴다.

엄격 주제(건강 약 용량·간격 / 법령 과태료·기준 / 금액 할인율·한도·지원금)는 검사 실패·
고친 뒤 남은 오류·전제 오류가 남으면 **갱신하지 않는다**. 그 밖의 글은 남은 문장을 지우고 간다.

순서도: docs/flowcharts/renewal_performance_pick.md (4. 사실 관문)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ...core.logger import get_logger
from ..generation.fact_gate import fact_check as f2

logger = get_logger("renewal_fact", "app.log")

DEFAULT_MODEL = ("anthropic", "claude-sonnet-5")
STRICT_TOPICS = (
    (r"해열제|진통제|감기약|영양제|복용|용량|투여|타이레놀|이부프로펜|아세트아미노펜|\d+\s*(?:mg|ml|㎎|㎖)",
     "건강(약 용량·간격)"),
    (r"과태료|벌금|과징금|처벌|법령|법률|시행령|설치\s*기준|의무|규정|신고\s*기한", "법령(과태료·기준)"),
    # 할인율·구매 한도·지원금 금액이 수시로 바뀌는 것(온누리상품권 등, 10/25 추가)
    (r"할인율|할인\s*한도|구매\s*한도|한도|지원금|보조금|상품권|온누리|지역화폐|환급금|캐시백",
     "금액(할인율·한도·지원금)"),
)
_FAKE_FIRST = re.compile(
    r"저도|저 역시|저는 |제가 |저희는 |제가 (?:직접|처음|써|사용|해)|제 (?:아이|딸|아들|남편|아내|경험)|저희 (?:아이|집|가족)|"
    r"필자(?:는|가|도|의)|직접 (?:써|해|먹어|가) ?(?:보니|봤)")
_VAGUE_CROWD = re.compile(
    r"(?:많은 )?(?:사용자|소비자|이용자|분|사람|이)들(?:이|은|도)[^.!?<]*"
    r"(?:보고|전하|전합|말하|말합|후기|경험|평가|만족|추천|느끼|입을 모)"
    r"|많은 (?:분|사람|이)(?:이|은|도)[^.!?<]*(?:보고|전하|말하|후기|경험|평가|만족|추천|느끼)"
    r"|(?:는|다는) 보고(?:도|가) 있습니다")
_SENTENCE = re.compile(r"[^<>.!?。]*[.!?。]")

CHECK_PROMPT = """당신은 한국 생활정보 블로그 글의 사실 검토자입니다. 이 글은 옛 글을 고쳐 쓴 것이라
옛 글의 틀린 전제를 그대로 따랐을 수 있습니다.

1) [본문]에서 틀렸거나 근거 없이 단정한 문장만 고르세요: 약 용량·복용 간격, 법령·과태료·설치 기준,
   할인율·구매 한도·지원금 금액, 가격표, 기관·제도 설명, 정의(무엇이 무엇과 같은지).
   - "sentence" 는 본문에서 글자 그대로 복사합니다.
   - "confidence": "높음" = 분명히 틀림·참고 자료와 어긋남·확인 안 되는 구체 숫자 단정,
     "중간" = 확인은 안 되지만 단정할 수 없음, "낮음" = 표현이 모호한 정도.
   - 수시로 바뀌는 할인율·한도·금액을 출처·기준일 없이 단정하면 "높음" 입니다.
   - "낮음" 은 적지 않습니다. 가장 중요한 것부터 최대 12개, reason·fix_hint 는 짧게.
2) 글 전체의 전제(제목이 묻는 것에 대한 기본 답)가 틀렸으면 "premise" 에 적습니다.
   예: '고추냉이와 와사비는 다른 식물' (실제로는 고추냉이=와사비, 튜브 제품은 대부분 서양고추냉이).
   전제가 맞으면 "premise" 는 빈 문자열.
- [참고 자료]가 당신의 기억과 다르면 참고 자료가 맞습니다.
- 문장 속 큰따옴표(")는 작은따옴표(')로 바꿔 적습니다.
- JSON 만 출력합니다:
{{"premise":"","items":[{{"sentence":"...","reason":"...","confidence":"높음|중간|낮음","fix_hint":"..."}}]}}

[제목] {title}

[참고 자료]
{refs}

[본문]
{body}"""


@dataclass
class FactOutcome:
    """관문 결과. hold 면 갱신하지 않는다. premise 가 있으면 호출측이 다시 쓴다."""

    html: str
    hold: Optional[str] = None
    premise: str = ""
    strict: Optional[str] = None
    record: dict = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def strict_topic(title: str, html: str = "") -> Optional[str]:
    """엄격 주제 이름(제목 기준, 약 용량은 본문 숫자도 본다). 아니면 None."""
    for pattern, label in STRICT_TOPICS:
        if re.search(pattern, title or ""):
            return label
    if re.search(r"\d+\s*(?:mg|ml|㎎|㎖)", html or "", re.I):
        return STRICT_TOPICS[0][1]
    return None


_TEX = ((r"\\[\[\]()]", ""), (r"\\text\{([^{}]*)\}", r"\1"), (r"\\times", "×"),
        (r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2"), (r"\\(?:,|;|quad)", " "))


def plain_math(html: str) -> str:
    """LaTeX 수식(\\[ \\text{} \\times \\frac{}{})을 보통 글자로 — 워드프레스에선 기호 그대로 보인다(10/25 /613)."""
    if "\\" not in (html or ""):
        return html
    out = html
    for pat, rep in _TEX:
        out = re.sub(pat, rep, out)
    return re.sub(r"[ \t]{2,}", " ", out)


def scrub_claims(html: str) -> tuple:
    """R1 지어낸 1인칭 경험·근거 없는 일반화 문장 지우기. (본문, 지운 문장)."""
    removed: List[str] = []

    def _cut(m: "re.Match[str]") -> str:
        s = m.group(0)
        if _FAKE_FIRST.search(s) or _VAGUE_CROWD.search(s):
            removed.append(s.strip())
            return ""
        return s

    out = _SENTENCE.sub(_cut, plain_math(html or ""))
    out = re.sub(r"<p[^>]*>\s*</p>", "", out)
    return re.sub(r"[ \t]{2,}", " ", out), removed


def plain(html: str) -> str:
    """검사 모델에 보낼 글자(태그 뺌)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


async def _check(ai: Any, html: str, refs: str, title: str, model: tuple) -> Optional[dict]:
    """검사 호출(실패하면 한 번 더). 그래도 실패면 None, 아니면 {"premise", "items"}."""
    for _ in range(2):
        got = await _check_once(ai, html, refs, title, model)
        if got is not None:
            return got
    return None


async def _check_once(ai: Any, html: str, refs: str, title: str, model: tuple) -> Optional[dict]:
    """검사 한 번. 10/25 재미리보기: 2,500토큰에서 잘려 실패 → 6,000."""
    prompt = CHECK_PROMPT.format(title=title, refs=(refs or "(없음)")[:f2.REF_LIMIT],
                                 body=plain(html))
    try:
        res = await ai.generate(prompt=prompt, provider=model[0], model=model[1],
                                max_tokens=6000, temperature=0.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("[RENEWAL_FACT] 검사 호출 실패 | %s", e)
        return None
    data = f2.parse_json((res or {}).get("content") or "")
    if not isinstance(data.get("items"), list):
        logger.warning("[RENEWAL_FACT] 검사 답 해석 실패 | %s",
                       ((res or {}).get("content") or "")[:200])
        return None
    items = [i for i in data["items"] if isinstance(i, dict) and i.get("sentence")]
    return {"premise": str(data.get("premise") or "").strip(), "items": items}


def _model(cfg: Optional[dict]) -> tuple:
    c = cfg if isinstance(cfg, dict) else {}
    return (c.get("provider") or DEFAULT_MODEL[0], c.get("model") or DEFAULT_MODEL[1])


async def run(ai: Any, html: str, refs: str, title: str,
              cfg: Optional[dict] = None, allow_premise: bool = True) -> FactOutcome:
    """R1 → R2 → R3. allow_premise=False 면(이미 다시 쓴 뒤) 전제 오류도 문장 고치기로 끝낸다."""
    out = FactOutcome(html=html, strict=strict_topic(title, html))
    rec = out.record
    out.html, rec["r1_removed"] = scrub_claims(out.html)
    if rec["r1_removed"]:
        out.notes.append(f"지어낸 경험·일반화 {len(rec['r1_removed'])}문장 지움")
    model = _model(cfg)
    got = await _check(ai, out.html, refs, title, model)
    rec["r2"] = got
    if got is None:
        # 전제를 바로잡아 다시 쓴 글(allow_premise=False)은 확인 못 하면 내보내지 않는다
        must = out.strict or not allow_premise
        out.hold = "사실 검사 호출 실패" if must else None
        out.notes.append("사실 검사 실패" + (" — 갱신 안 함" if must else " — 검사 없이 계속"))
        return out
    if got["premise"] and allow_premise:
        out.premise = got["premise"]
        return out
    await _fix(ai, out, got, refs, model, title)
    if not allow_premise and not out.hold and out.record.get("premise_left_after"):
        out.hold = "전제를 바로잡지 못함 — " + out.record["premise_left_after"][:60]
    _log(title, out)
    return out


async def _fix(ai: Any, out: FactOutcome, got: dict, refs: str, model: tuple,
               title: str) -> None:
    """'높음' 문장 고치기 → 다시 검사 → 남으면 엄격 주제는 보류, 아니면 지움."""
    rec = out.record
    bad = f2.high(got["items"])
    if got["premise"]:
        rec["premise_left"] = got["premise"]
    if not bad and not got["premise"]:
        return
    bad = bad[:8]
    fixes = await f2.fix(ai, bad, refs, model[0], model[1]) if bad else []
    given = {str(f.get("sentence") or "").strip() for f in fixes}
    fixes += [{"sentence": b["sentence"], "replacement": ""}
              for b in bad if str(b["sentence"]).strip() not in given]
    out.html, rec["r3_fixes"] = f2.apply_fixes(out.html, fixes)
    out.notes.append(f"틀린 문장 {len(bad)}개 고침")
    again = await _check(ai, out.html, refs, title, model)
    rec["r3_recheck"] = again
    left = f2.high((again or {}).get("items"))
    if (again or {}).get("premise"):
        rec["premise_left_after"] = again["premise"]
    if again is None or left or (again or {}).get("premise"):
        why = ("재검사 실패" if again is None else
               f"고친 뒤에도 틀린 문장 {len(left)}개: {left[0].get('sentence', '')[:50]}"
               f" ({left[0].get('reason', '')[:40]})" if left else "전제 오류 남음")
        if out.strict:
            out.hold = f"{out.strict} — {why}"
        elif left:
            out.html, _ = f2.apply_fixes(out.html, [{"sentence": i["sentence"], "replacement": ""}
                                                    for i in left])
            out.notes.append(f"남은 틀린 문장 {len(left)}개 지움")
        else:
            out.notes.append(why)


def _log(title: str, out: FactOutcome) -> None:
    logger.info("[RENEWAL_FACT] '%s' | 엄격=%s | 보류=%s | %s", (title or "")[:40],
                out.strict or "-", out.hold or "-", "; ".join(out.notes) or "문제 없음")


def premise_instruction(premise: str) -> str:
    """전제를 바로잡아 다시 쓰라는 지시(본문 프롬프트 끝)."""
    return ("[바로잡을 전제 — 반드시 지킬 것]\n"
            f"- 옛 글의 전제가 틀렸습니다: {premise}\n"
            "- 옛 글의 이 전제를 따르지 말고, 바른 사실을 첫 문단에서 먼저 밝힌 뒤 글 전체를 그에 맞게 쓰세요.\n"
            "- 확인되지 않은 가격·할인율·한도·용량 숫자는 쓰지 말고, 공식 확인처를 안내하세요.\n"
            "- '저도', '제 아이도', '필자는' 같은 지어낸 경험과 '많은 사용자들이' 같은 근거 없는 일반화는 쓰지 마세요.")
