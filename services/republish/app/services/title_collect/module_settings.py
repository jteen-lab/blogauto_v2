"""제목 모듈 settings → 작업대 payload 변환.

**화면과 모듈이 같은 실행기를 쓴다.** 임시제목 탭의 작업대가 하는 일을
모듈이 자동으로도 하려면, 둘이 같은 코드를 타야 한다. 다른 코드를 타면
한쪽에서만 나는 버그가 생긴다.

모듈 settings 는 `{"title": {...}}` 모양이고 작업대 payload 는
`{"collect": {...}, "gen": {...}}` 모양이다. 그 사이를 여기서 잇는다.

**하위 호환**: 옛 title_gen 모듈은 `title` 아래에 L1 설정만 평평하게
갖고 있다(`dry_run`·`cluster_limit`·…). `collect`/`gen` 키가 없으면 그
평평한 값을 생성(L1) 설정으로 읽는다 — 이미 만들어 둔 모듈이 조용히
멈추면 안 된다.

계획서: docs/plans/title_tab_workplan.md §1
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# 옛 모듈에서 L1 설정으로 읽을 키들
LEGACY_GEN_KEYS = (
    "dry_run", "use_angles", "angle_sample", "cluster_enabled",
    "cluster_threshold", "cluster_min_size", "cluster_max_size",
    "titles_per_cluster", "titles_per_keyword", "cluster_limit",
    "keyword_limit", "ai_provider", "ai_model",
)


def normalize(settings: Optional[dict]) -> Dict[str, Any]:
    """모듈 settings 를 작업대 payload 로.

    Returns:
        {"collect": {...}, "gen": {...}} — 작업대가 그대로 받는 모양.
    """
    raw = settings or {}
    title = raw.get("title") if isinstance(raw.get("title"), dict) else raw

    collect = title.get("collect")
    gen = title.get("gen")

    if not isinstance(collect, dict):
        # 옛 모듈에는 수집 설정이 없다. 꺼진 것으로 본다 — 켜져 있다고
        # 짐작해서 돌리면 사용자가 모르는 사이 수집이 시작된다.
        collect = {"enabled": False}

    if not isinstance(gen, dict):
        gen = {k: title[k] for k in LEGACY_GEN_KEYS if k in title}
        # 옛 모듈은 제목 생성이 존재 이유였다. 켜진 것으로 본다.
        gen.setdefault("enabled", bool(title.get("enabled", True)))
        gen.setdefault("l1_enabled", True)
        gen.setdefault("l3_enabled", False)

    return {"collect": dict(collect), "gen": dict(gen)}


def is_enabled(settings: Optional[dict]) -> bool:
    """이 모듈이 할 일이 하나라도 있는가."""
    payload = normalize(settings)
    return bool(payload["collect"].get("enabled")
                or payload["gen"].get("enabled"))
