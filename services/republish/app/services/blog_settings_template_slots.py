"""템플릿 이미지 슬롯 — 블로그 하나에 배경을 여러 장.

**왜 필요한가**: 대표 이미지가 매번 같으면 목록에서 한 블로그의 글이 한눈에
묶여 보인다. 니치·키워드·순번에 따라 배경을 바꾸면 그 인상이 사라진다.

**저장 모양**

    slot 0      overlay_config["template_image"]      기존 키. 손대지 않는다
    slot 1~9    overlay_config["template_images"][]   추가 배경

기존 단수 키를 그대로 두는 게 하위 호환의 전부다. 이미 단수로 운영 중인
블로그는 이 파일이 없는 것처럼 동작한다.

**파일 이름**도 슬롯을 탄다. `save_uploaded_file` 이 블로그당 한 이름
(`template_21.png`)만 쓰기 때문에, 슬롯이 없으면 두 번째 업로드가 첫 번째를
덮어쓴다.

계획서: docs/plans/topic_discovery_and_structure_plan.md §3-4
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("template_slots", "app.log")

MAX_SLOT = 9
BASE_SLOT = 0

IMAGES_KEY = "template_images"
SINGLE_KEY = "template_image"
MODE_KEY = "template_image_mode"


def filename_for(file_type: str, blog_id: int, ext: str, slot: int = 0) -> str:
    """슬롯별 파일 이름. 0 은 기존 이름 그대로 — 덮어쓰기를 막는다."""
    if file_type != "template" or not slot:
        return f"{file_type}_{blog_id}{ext}"
    return f"{file_type}_{blog_id}_{int(slot)}{ext}"


def entries(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """추가 배경 목록. 없으면 빈 목록."""
    rows = (config or {}).get(IMAGES_KEY) or []
    return [r for r in rows if isinstance(r, dict) and r.get("path")]


def path_of(config: Optional[Dict[str, Any]], slot: int) -> Optional[str]:
    """슬롯의 파일 경로. 없으면 None."""
    if not slot:
        return (config or {}).get(SINGLE_KEY)
    for row in entries(config):
        if int(row.get("slot") or 0) == int(slot):
            return row.get("path")
    return None


def put(config: Optional[Dict[str, Any]], slot: int,
        path: str) -> Dict[str, Any]:
    """슬롯에 경로를 넣는다(원본 불변).

    슬롯 0 은 기존 단수 키에 쓴다. 1 이상은 목록에 넣거나 갈아끼운다.
    """
    updated = dict(config or {})
    if not slot:
        updated[SINGLE_KEY] = path
        return updated

    rows = [dict(r) for r in entries(updated)]
    for row in rows:
        if int(row.get("slot") or 0) == int(slot):
            row["path"] = path
            break
    else:
        rows.append({"slot": int(slot), "path": path,
                     "topic_ids": [], "keywords": []})
    rows.sort(key=lambda r: int(r.get("slot") or 0))
    updated[IMAGES_KEY] = rows
    logger.info("[TEMPLATE_SLOT] 슬롯 %d 저장 | %s", slot, path)
    return updated


def drop(config: Optional[Dict[str, Any]], slot: int) -> Dict[str, Any]:
    """슬롯을 지운다(원본 불변)."""
    updated = dict(config or {})
    if not slot:
        updated.pop(SINGLE_KEY, None)
        return updated

    rows = [r for r in entries(updated)
            if int(r.get("slot") or 0) != int(slot)]
    if rows:
        updated[IMAGES_KEY] = rows
    else:
        updated.pop(IMAGES_KEY, None)
    return updated


def next_slot(config: Optional[Dict[str, Any]]) -> Optional[int]:
    """비어 있는 다음 슬롯. 꽉 찼으면 None."""
    used = {int(r.get("slot") or 0) for r in entries(config)}
    for slot in range(1, MAX_SLOT + 1):
        if slot not in used:
            return slot
    return None


def for_picker(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`variant_picker` 가 먹는 모양으로. 기본 배경도 후보에 넣는다.

    추가 배경이 하나도 없으면 빈 목록을 돌려준다 — 그래야 호출부가 기존
    단수 경로로 폴백한다.
    """
    rows = entries(config)
    if not rows:
        return []
    base = (config or {}).get(SINGLE_KEY)
    out: List[Dict[str, Any]] = []
    if base:
        out.append({"path": base, "topic_ids": [], "keywords": []})
    out.extend({"path": r["path"],
                "topic_ids": r.get("topic_ids") or [],
                "keywords": r.get("keywords") or []} for r in rows)
    return out


# ── 라우터 글루 ────────────────────────────────────────────────────────
# 폰트는 슬롯이 없다. 라우터가 매번 분기하지 않도록 여기서 가른다.

FONT_KEY = "font_file"


def slot_path(config: Optional[Dict[str, Any]], file_type: str,
              slot: int) -> Optional[str]:
    """슬롯(또는 폰트)의 파일 경로."""
    if file_type != "template":
        return (config or {}).get(FONT_KEY)
    return path_of(config, slot)


def slot_put(config: Optional[Dict[str, Any]], file_type: str, slot: int,
             path: str) -> Dict[str, Any]:
    """슬롯(또는 폰트)에 경로를 넣은 새 설정."""
    if file_type != "template":
        updated = dict(config or {})
        updated[FONT_KEY] = path
        return updated
    return put(config, slot, path)


def slot_drop(config: Optional[Dict[str, Any]], file_type: str,
              slot: int) -> Dict[str, Any]:
    """슬롯(또는 폰트)을 지운 새 설정."""
    if file_type != "template":
        updated = dict(config or {})
        updated.pop(FONT_KEY, None)
        return updated
    return drop(config, slot)
