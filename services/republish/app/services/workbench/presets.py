"""프리셋 — 수동 작업에서 자주 쓰는 구성을 저장한다.

테스트는 1회성이라 저장하지 않는다. 수동 생성·발행처럼 **반복하는 작업**만
구성을 남긴다(계획서 §8). 저장되는 것은 구성뿐이다 — 어떤 모듈을 어떤
순서로, 어느 블로그로. **결과물은 저장되지 않는다.**

새 테이블 없이 시스템 설정 한 칸에 JSON 으로 둔다. 프리셋은 많아야
수십 개라 이 정도면 충분하고, 마이그레이션이 없다.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from ...core.logger import get_logger
from ..system_settings_service import SystemSettingsService

logger = get_logger("workbench_presets", "app.log")

STORE_KEY = "workbench_presets"
MAX_PRESETS = 50


async def _load(db: Any) -> List[Dict[str, Any]]:
    raw = await SystemSettingsService.get(STORE_KEY, db)
    if not raw:
        return []
    try:
        rows = json.loads(raw)
        return rows if isinstance(rows, list) else []
    except (TypeError, ValueError):
        logger.warning("[WORKBENCH] 프리셋 저장분이 깨져 있어 비웁니다")
        return []


async def _save(db: Any, rows: List[Dict[str, Any]]) -> None:
    """저장하고 **반드시 커밋한다.**

    설정 저장 함수는 커밋하지 않고 메모리에만 값을 얹는다(여러 개를
    모아 한 번에 커밋하라고 그렇게 돼 있다). 커밋을 빠뜨리면 그
    프로세스가 살아 있는 동안에는 멀쩡해 보이다가, 컨테이너가 다시
    뜨는 순간 통째로 사라진다 — 실제로 그렇게 잃었다(2026-09-15).
    """
    await SystemSettingsService.set(
        STORE_KEY, json.dumps(rows, ensure_ascii=False), db)
    await db.commit()


async def list_presets(db: Any) -> List[Dict[str, Any]]:
    """저장된 구성 목록 — 최근 것부터."""
    rows = await _load(db)
    return sorted(rows, key=lambda r: r.get("saved_at", ""), reverse=True)


async def save_preset(db: Any, name: str,
                      config: Dict[str, Any]) -> Dict[str, Any]:
    """구성을 저장한다. 같은 이름이면 덮어쓴다."""
    label = (name or "").strip()
    if not label:
        return {"success": False, "message": "프리셋 이름이 비었습니다"}
    rows = await _load(db)
    rows = [r for r in rows if r.get("name") != label]
    if len(rows) >= MAX_PRESETS:
        return {"success": False,
                "message": f"프리셋은 {MAX_PRESETS}개까지입니다"}
    rows.append({"name": label, "config": config or {},
                 "saved_at": datetime.now().isoformat(timespec="seconds")})
    await _save(db, rows)
    logger.info("[WORKBENCH] 프리셋 저장 | %s", label)
    return {"success": True, "message": f"「{label}」 저장됨"}


async def delete_preset(db: Any, name: str) -> Dict[str, Any]:
    """구성을 지운다."""
    rows = await _load(db)
    kept = [r for r in rows if r.get("name") != name]
    if len(kept) == len(rows):
        return {"success": False, "message": "그 이름의 프리셋이 없습니다"}
    await _save(db, kept)
    return {"success": True, "message": f"「{name}」 삭제됨"}
