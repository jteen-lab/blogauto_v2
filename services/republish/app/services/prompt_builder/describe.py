"""프롬프트 모듈에 적용된 프리셋을 사람이 읽을 이름으로 만든다 (2026-08-30).

플로우 수정 화면·1회 생성 버튼 옆에 "지금 어떤 프롬프트로 생성되는지"를 보여주기
위한 것이다. 모듈 카드에는 텍스트가 아니라 이름이 필요하다.

판정 순서
    1. 저장된 축 스냅샷(builder_selection) — 빌더에서 반영하며 남긴 것
    2. 없으면 **본문 대조로 역추론** — 각 블록 본문이 템플릿에 통째로 들어간다
       (빌더 밖에서 만든 프롬프트, 옛 모듈도 판정된다)
    3. 축이 안 잡히면 전용 프롬프트(full_prompt) 프리셋과 통째로 대조
       — 승인용 프롬프트를 템플릿에 붙여넣은 모듈이 실제로 있다
    4. 그래도 안 잡히면 "직접 작성" — 손으로 쓴 프롬프트다. 빈칸으로 두면
       사용자는 표시가 고장난 건지 프리셋이 없는 건지 구분하지 못한다

클라이언트에서 따로 추론하지 않고 서버가 한 번에 정한다. 두 곳에서 각자 추론하면
화면마다 다른 답이 나온다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .blocks import COMMONS, PATTERNS, PERSONAS, READERS, TONES
from .presets import PRESETS

AXES = {
    "persona": PERSONAS,
    "reader": READERS,
    "pattern": PATTERNS,
    "tone": TONES,
    "common": COMMONS,
}


def _template(settings: Optional[Dict[str, Any]]) -> str:
    generation = (settings or {}).get("content_generation") or {}
    return generation.get("user_prompt_template") or ""


def _snapshot(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    generation = (settings or {}).get("content_generation") or {}
    snap = generation.get("builder_selection")
    return snap if isinstance(snap, dict) else {}


def _infer_axes(template: str) -> Dict[str, str]:
    """본문에 어떤 블록이 들어 있는지로 축 선택을 되짚는다."""
    if not template.strip():
        return {}
    found: Dict[str, str] = {}
    for axis, blocks in AXES.items():
        for block in blocks:
            body = (block.get("body") or "").strip()
            if body and body in template:
                found[axis] = block["code"]
                break
    return found


def resolve_axes(settings: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """모듈에 적용된 축 코드. 스냅샷 우선, 없으면 본문 역추론."""
    snap = _snapshot(settings)
    if any(snap.get(a) for a in AXES):
        return {a: snap.get(a) or "" for a in AXES}
    return _infer_axes(_template(settings))


def matching_preset(settings: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """4축이 일치하는 프리셋. 없으면 None."""
    axes = resolve_axes(settings)
    if not all(axes.get(a) for a in ("persona", "reader", "pattern", "tone")):
        return None
    for preset in PRESETS:
        if preset.get("full_prompt"):
            continue
        if all(preset.get(a) == axes.get(a) for a in
               ("persona", "reader", "pattern", "tone")):
            return preset
    return None


def axis_labels(settings: Optional[Dict[str, Any]]) -> List[str]:
    """선택된 축의 사람이 읽을 이름 목록(프리셋이 없을 때 대신 보여준다)."""
    axes = resolve_axes(settings)
    labels: List[str] = []
    for axis, blocks in AXES.items():
        code = axes.get(axis)
        if not code:
            continue
        for block in blocks:
            if block["code"] == code:
                labels.append(block["label"])
                break
    return labels


def _squash(text: str) -> str:
    """공백 차이를 무시하고 비교하기 위한 정규화."""
    return " ".join(text.split())


def full_prompt_preset(settings: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """템플릿이 전용 프롬프트 프리셋 본문 그 자체인 경우 그 프리셋."""
    template = _squash(_template(settings))
    if not template:
        return None
    for preset in PRESETS:
        body = _squash(preset.get("full_prompt") or "")
        if body and (body == template or template.startswith(body)):
            return preset
    return None


def describe(settings: Optional[Dict[str, Any]]) -> str:
    """모듈 카드에 표시할 한 줄. 프롬프트가 아예 없으면 빈 문자열."""
    preset = matching_preset(settings)
    if preset:
        return str(preset.get("label") or "")
    labels = axis_labels(settings)
    if labels:
        return "직접 조합 · " + " / ".join(labels)
    whole = full_prompt_preset(settings)
    if whole:
        return str(whole.get("label") or "")
    if _template(settings).strip():
        return "직접 작성"
    return ""


def describe_approval(settings: Optional[Dict[str, Any]]) -> str:
    """승인 전에만 쓰는 프리셋 이름. 지정이 없으면 빈 문자열."""
    from ..generation.adsense_prompt_switch import find_preset, selected_code

    preset = find_preset(selected_code(settings))
    return str((preset or {}).get("label") or "")
