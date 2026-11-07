"""고칠 글 목록 — 사실 관문이 막았지만 공개된 채 남은 글 (2026-11-07).

리뉴얼이 보류되면 새 글로 바뀌지 않을 뿐 옛 글은 그대로 공개돼 있다. 기록이 renewal.jsonl 에
섞여 있으면 잊힌다(11/7 시범 보류 9편). 내용 문제로 막힌 글만 따로 모아 고칠 때까지 남긴다.

logs/renewal_fix_list.jsonl 에 덧붙이기만 한다. 같은 글은 마지막 줄이 현재 상태다.

순서도: docs/flowcharts/renewal_retitle_candidates.md (1. 고칠 글 목록)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ...core.logger import LoggerConfig, get_logger

logger = get_logger("renewal_fixlist", "app.log")

FIX_LIST = "renewal_fix_list.jsonl"
_FACT_HOLD = "사실 관문 통과 못 함"
# 검사가 돌지 못한 것이지 글이 틀렸다는 판정이 아니다
_NOT_VERDICT = ("호출 실패", "재검사 실패", "다시 쓰기 실패")


def fact_reason(error: Optional[str]) -> Optional[str]:
    """보류 사유가 내용 문제면 그 글자, 아니면 None. 순수 함수."""
    text = error or ""
    if _FACT_HOLD not in text or any(w in text for w in _NOT_VERDICT):
        return None
    return text


def _path() -> Path:
    return Path(LoggerConfig.LOG_DIR) / FIX_LIST


def _append(row: Dict[str, Any]) -> None:
    """한 줄 덧붙임. 실패해도 리뉴얼 결과는 그대로."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[RENEWAL_FIX] 기록 실패(무시) | %s", e)


def add(blog: Any, post_id: int, url: str, title: str, reason: str) -> None:
    """고칠 글 한 줄."""
    _append({"at": datetime.now().isoformat(timespec="seconds"),
             "blog_id": getattr(blog, "id", None), "blog": getattr(blog, "name", None),
             "post": post_id, "url": url, "title": title, "reason": reason})
    logger.info("[RENEWAL_FIX] 고칠 글 추가 | post=%s | %s", post_id, url)


def close(post_id: int, note: str) -> None:
    """고쳤음 — 목록에서 뺀다."""
    _append({"at": datetime.now().isoformat(timespec="seconds"), "post": post_id,
             "closed": True, "note": note})


def read_lines() -> List[Dict[str, Any]]:
    """기록 줄 전부. 파일이 없거나 깨진 줄은 건너뛴다."""
    try:
        raw = _path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: List[Dict[str, Any]] = []
    for line in raw:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def open_items(lines: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """아직 안 고친 글. 같은 글은 마지막 줄 기준. 순수 함수."""
    last: Dict[int, Dict[str, Any]] = {}
    for row in lines:
        if row.get("closed"):
            last.pop(row.get("post"), None)
        elif row.get("post") is not None:
            last[row["post"]] = row
    return list(last.values())


def close_if_open(post_id: int, note: str) -> None:
    """목록에 있는 글이면 닫는다(리뉴얼이 성공했을 때)."""
    if any(r.get("post") == post_id for r in open_items(read_lines())):
        close(post_id, note)
