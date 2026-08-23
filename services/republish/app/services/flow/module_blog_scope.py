"""프롬프트/생성 모듈의 '연동 블로그' 판정 (단일 기준).

플로우 저장 검증과 실행부가 같은 규칙을 쓰도록 여기 한 곳에 둔다. 판정 규칙은
프런트(`static/js/flows/form.js`)와 동일하며, 서버가 권위·프런트는 UX 용이다.

계획서: docs/plans/flow_module_blog_scope_plan.md
"""
from typing import Any, Dict, Iterable, List, Optional, Set

# 블로그를 연동할 수 있는 모듈 타입(생성 파이프라인을 도는 타입)
BLOG_SCOPED_TYPE_CODES = ("prompt", "generate")

# 플로우당 1개만 허용하는 모듈 타입
SINGLETON_TYPE_CODES = {
    "growth_profile": "성장 프로파일",
    "contact_form": "애드센스 필수구성",
}

# 애드센스 승인 상태에 따른 모듈 역할(Module.settings.adsense_role)
ROLE_ALWAYS = "always"              # 상태 무관(기본 · 기존 모듈 전부 이 값)
ROLE_ADSENSE_ONLY = "adsense_only"  # 승인 전에만 실행(애드센스 전용 공용 모듈)
ROLE_POST_APPROVAL = "post_approval"  # 승인 후에만 실행(정상 운영 모듈)

ADSENSE_ROLES = {
    ROLE_ALWAYS: "항상 실행",
    ROLE_ADSENSE_ONLY: "애드센스 승인 전에만",
    ROLE_POST_APPROVAL: "애드센스 승인 후에만",
}

# 승인 완료로 보는 상태
APPROVED_STATUS = "approved"


def _collect_blog_ids(settings: Optional[Dict[str, Any]]) -> Set[int]:
    """settings에서 연동 블로그 ID를 모은다.

    `blog_category_map`(블로그별 카테고리 매핑)이 있으면 그쪽을 우선하고,
    없으면 레거시 `blogs` 목록을 쓴다. `blogs`는 [1,2] 와 [{"id":1}] 두 형태를
    모두 허용한다(옛 저장분 호환).
    """
    if not settings:
        return set()

    ids: Set[int] = set()
    bcm = settings.get("blog_category_map")
    if isinstance(bcm, list) and bcm:
        for row in bcm:
            if isinstance(row, dict) and isinstance(row.get("blog_id"), int):
                ids.add(row["blog_id"])
        if ids:
            return ids

    for item in settings.get("blogs") or []:
        if isinstance(item, int):
            ids.add(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), int):
            ids.add(item["id"])
    return ids


def is_blog_scoped_module(module: Any) -> bool:
    """블로그를 연동할 수 있는 타입(prompt/generate)인지."""
    module_type = getattr(module, "module_type", None)
    code = getattr(module_type, "code", None)
    return code in BLOG_SCOPED_TYPE_CODES


def resolve_module_blog_ids(module: Any) -> Set[int]:
    """모듈에 연동된 블로그 ID 집합.

    빈 집합은 "블로그 한정 없음"(카테고리 모드 등)을 뜻하며, 이 경우 플로우에
    연결된 블로그 전체가 대상이 된다.
    """
    if not is_blog_scoped_module(module):
        return set()
    return _collect_blog_ids(getattr(module, "settings", None))


def resolve_scope_union(modules: Iterable[Any]) -> Set[int]:
    """여러 모듈의 연동 블로그 합집합(플로우 블로그 범위 강제용)."""
    union: Set[int] = set()
    for module in modules:
        union |= resolve_module_blog_ids(module)
    return union


def resolve_adsense_role(module: Any) -> str:
    """모듈의 애드센스 역할. 미지정이면 always(하위호환)."""
    settings = getattr(module, "settings", None) or {}
    role = settings.get("adsense_role")
    return role if role in ADSENSE_ROLES else ROLE_ALWAYS


def is_module_active_for_blog(module: Any, blog: Any) -> bool:
    """이 블로그에 대해 모듈을 지금 실행해야 하는지.

    모듈 전체를 켜고 끄지 않고 **블로그마다** 판정한다. 공용 니치 모듈에 여러
    블로그가 붙었을 때 일부만 승인되는 상황이 정상이기 때문이다
    (A는 승인 → 건너뜀 / B는 심사 중 → 계속 실행).
    """
    role = resolve_adsense_role(module)
    if role == ROLE_ALWAYS:
        return True

    approved = (getattr(blog, "adsense_status", None) == APPROVED_STATUS)
    if role == ROLE_ADSENSE_ONLY:
        return not approved
    if role == ROLE_POST_APPROVAL:
        return approved
    return True


def blogs_for_module(module: Any, blogs: List[Any]) -> List[Any]:
    """실행 대상 블로그를 좁힌다.

    1) 모듈에 연동된 블로그로 한정(연동이 없으면 받은 목록 그대로 — 하위호환)
    2) 애드센스 역할에 따라 블로그별로 다시 걸러낸다
    """
    scope = resolve_module_blog_ids(module)
    candidates = (
        blogs if not scope
        else [b for b in blogs if getattr(b, "id", None) in scope]
    )
    return [b for b in candidates if is_module_active_for_blog(module, b)]
