"""사실 관문 기록장 — 글마다 한 줄(JSON)을 logs/fact_gate.jsonl 에 덧붙인다.

app.log 는 돌려 쓰기(rotate)로 지워지고 한 줄이 3,000자에서 잘린다.
마케팅 아침 분석·블로그오토 일일 점검이 F2 가 잡은 문장·고친 문장을
글 단위로 읽을 수 있게 따로 남긴다(B4, 2026-10-20 마케팅 판정).

모듈 설정 ``fact_gate.journal`` 이 true 일 때만 쓴다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ....core.logger import LoggerConfig, get_logger

logger = get_logger("fact_gate", "app.log")

FILE = "fact_gate.jsonl"


def path() -> Path:
    """기록장 경로(logs 볼륨 — 앱·워커 컨테이너가 같이 본다)."""
    return Path(LoggerConfig.LOG_DIR) / FILE


def entry(blog: Any, title: str, hold: Optional[str], rec: dict) -> dict:
    """기록장 한 줄. 잡은 문장(F2 전부)·고친 문장·재검사·F1·F3 를 담는다."""
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "blog_id": getattr(blog, "id", None),
        "title": title,
        "hold": hold,
        "f1_removed": rec.get("f1_removed"),
        "f3": rec.get("f3"),
        "f2_items": rec.get("f2_items"),
        "f2_fixes": rec.get("f2_fixes"),
        "f2_recheck": rec.get("f2_recheck"),
        "f2_error": rec.get("f2_error"),
    }


def write(blog: Any, title: str, hold: Optional[str], rec: dict) -> None:
    """한 줄 덧붙이기. 실패해도 글 생성은 막지 않는다."""
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry(blog, title, hold, rec),
                               ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[FACT_GATE] 기록장 쓰기 실패 | %s", e)
