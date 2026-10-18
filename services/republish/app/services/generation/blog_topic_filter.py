"""모듈 설정으로 거르는 제목 — 지운 주제 잠시 피하기 · 피할 주제 유형.

수작남(블로그 13) 마케팅 진단(2026-10-19, 형 승인):
  - 10월 새 글 16편 중 10편 이상이 9/29 에 지운 글과 같은 주제를 다시 쓴 글이었고,
    10/1 이후 새 글 네이버 색인이 0/13 이다(9월엔 13/13). 네이버가 아직 들고 있는
    지운 옛 주소와 비슷한 문서로 보고 걸렀을 가능성이 크다.
  - 전화번호·영업시간·공식 신청 방법 같은 주제는 공식·공공 사이트가 위를 다 차지해
    수작남이 30위 안에도 못 든다.

둘 다 **모듈 settings 최상위 키**로 켠다(모듈 화면 저장에 지워지지 않는 자리).

    avoid_topics = {"until": "YYYY-MM-DD", "titles": [지운 글 제목, ...],
                    "reason": "..."}
    skip_title_patterns = [{"pattern": 정규식, "label": "공식 사이트 우세"}, ...]

둘 다 **이번 회차만 건너뛴다**(보관 아님 — 제목은 창고에 남아 다른 블로그가 쓴다).
until 이 지나면 avoid_topics 는 저절로 꺼진다.

순서도: docs/flowcharts/title_topic_gate.md (모듈 설정 거름망)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, List, Optional, Set

from ...core.logger import get_logger
from .link_relevance import tokenize

logger = get_logger("blog_topic_filter", "app.log")

AVOID_KEY = "avoid_topics"
SKIP_KEY = "skip_title_patterns"

# 주제가 아니라 글 형식을 말하는 낱말 — 겹쳐도 같은 주제가 아니다.
FORM_WORDS: Set[str] = set(
    "방법 방법은 정리 알아보기 이유 효과 꿀팁 추천 주의사항 총정리 가이드 노하우 "
    "차이 종류 비교 관리 증상 원인 효능 가지 선택 기준 확인 무엇 어떻게 좋은 쉽게 "
    "필수 알아야 위한 대한 관련 하는 있는 좋을까 신청 후기 준비 사용 이용".split())
# 같은 주제 기준(10/19 모의: 10월 새 글 10쌍 모두 잡고 수작남 제목 창고 418개 중
# 156개만 걸림 → 남은 262개로 11/16 까지 충분)
MIN_SHARED = 2
MIN_SHARE = 0.5          # 짧은 쪽 의미 낱말의 절반 이상이 겹침
SINGLE_SHARE = 0.67      # 낱말 1개만 겹칠 땐 짧은 쪽의 2/3 이상


def _meaning(title: str) -> Set[str]:
    """형식 낱말·숫자 낱말을 뺀 의미 낱말."""
    return {t for t in tokenize(title or "")
            if t and not t[0].isdigit() and t not in FORM_WORDS}


def same_subject(a: str, b: str) -> bool:
    """두 제목이 같은 주제를 다루나(표현이 달라도)."""
    ta, tb = _meaning(a), _meaning(b)
    if not ta or not tb:
        return False
    shared = len(ta & tb)
    share = shared / min(len(ta), len(tb))
    return ((shared >= MIN_SHARED and share >= MIN_SHARE)
            or (shared >= 1 and share >= SINGLE_SHARE))


def _until(cfg: dict) -> Optional[date]:
    try:
        return date.fromisoformat(str(cfg.get("until") or ""))
    except ValueError:
        return None


def avoided(title: str, cfg: Any, today: Optional[date] = None) -> Optional[str]:
    """피할 주제 목록과 같은 주제면 그 옛 제목. 기간이 지났거나 설정 없으면 None."""
    if not isinstance(cfg, dict):
        return None
    until = _until(cfg)
    if until is None or (today or date.today()) > until:
        return None
    for old in cfg.get("titles") or []:
        if old and same_subject(title, str(old)):
            return str(old)
    return None


def skipped_by_pattern(title: str, patterns: Iterable[Any]) -> Optional[str]:
    """피할 주제 유형에 걸리면 그 이름. 잘못된 정규식은 건너뛴다."""
    for item in patterns or []:
        pattern = item.get("pattern") if isinstance(item, dict) else item
        label = item.get("label") if isinstance(item, dict) else None
        if not pattern:
            continue
        try:
            m = re.search(str(pattern), title or "")
        except re.error as e:
            logger.warning("[BLOG_TOPIC] 정규식 오류 무시 | %s | %s", pattern, e)
            continue
        if m:
            return f"{label or '피할 주제'}({m.group(0)})"
    return None


def verdict(title: str, settings: Optional[dict],
            today: Optional[date] = None) -> Optional[str]:
    """DB 없이 판정한다. 건너뛸 사유 문자열 또는 None."""
    settings = settings or {}
    old = avoided(title, settings.get(AVOID_KEY), today)
    if old:
        until = settings[AVOID_KEY].get("until")
        return f"제목 관문(지운주제) — {until}까지 피함, 지운 글 「{old[:30]}」과 같은 주제"
    hit = skipped_by_pattern(title, settings.get(SKIP_KEY) or [])
    if hit:
        return f"제목 관문(피할주제) — {hit}"
    return None


async def apply(db: Any, blog: Any, title: Any,
                module_settings: Optional[dict]) -> Optional[str]:
    """자동 생성 직전에 부른다. 건너뛰면 사유, 아니면 None. 판정 오류는 통과."""
    text = getattr(title, "title", "") or ""
    try:
        msg = verdict(text, module_settings)
    except Exception as e:  # noqa: BLE001 — 판정 오류로 생성을 막지 않는다
        logger.warning("[BLOG_TOPIC] 판정 실패(통과) | blog=%s | %s",
                       getattr(blog, "id", None), e)
        return None
    if msg:
        logger.info("[BLOG_TOPIC] 건너뜀 | blog=%s | title_id=%s | '%s' | %s",
                    getattr(blog, "id", None), getattr(title, "id", None),
                    text[:40], msg)
    return msg


def matched_count(titles: List[str], settings: Optional[dict],
                  today: Optional[date] = None) -> int:
    """제목 창고 중 몇 개가 걸리나(설정 전 모의용)."""
    return sum(1 for t in titles if verdict(t, settings, today))
