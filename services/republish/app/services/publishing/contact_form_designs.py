"""문의폼 디자인 프리셋 카탈로그 (A안 — 필드와 독립된 디자인 축).

필드 템플릿(``contact_form_templates.py``)과 별개로, 폼의 **시각 디자인**(테마·
색상·폰트)을 재사용 프리셋으로 선택한다. contact_form 모듈은 ``template_code``
(필드)와 ``design_code``(디자인)를 각각 저장하고, 실행 시 둘을 조합해 Tally 폼을
만든다. 같은 필드에 색만 바꾸는 조합이 자유롭다.

디자인은 Tally ``settings.styles`` 객체로 전달된다(실호출 201 검증):
- ``theme``: LIGHT / DARK / CUSTOM
- ``color``: background / text / accent / buttonBackground / buttonText (HEX)
- ``font``: {provider, family} (Google Fonts)

``default``(기본)는 styles를 보내지 않아 Tally 기본 외형을 그대로 쓴다
(기존 폼의 config_hash 불변 → 불필요한 재수정 없음).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 한글 가독성용 기본 폰트(Google Fonts)
_KR_FONT: Dict[str, str] = {"provider": "Google", "family": "Noto Sans KR"}

DEFAULT_DESIGN_CODE = "default"


def _custom(
    accent: str,
    *,
    background: str = "#ffffff",
    text: str = "#1f2937",
    button_text: str = "#ffffff",
    font: Optional[Dict[str, str]] = _KR_FONT,
) -> Dict[str, Any]:
    """CUSTOM 테마 styles 생성 헬퍼(강조/버튼을 accent로 통일)."""
    styles: Dict[str, Any] = {
        "theme": "CUSTOM",
        "color": {
            "background": background,
            "text": text,
            "accent": accent,
            "buttonBackground": accent,
            "buttonText": button_text,
        },
    }
    if font:
        styles["font"] = dict(font)
    return styles


def _preview(
    accent: str,
    *,
    background: str = "#ffffff",
    text: str = "#1f2937",
    button_text: str = "#ffffff",
    input_border: str = "#d1d5db",
) -> Dict[str, str]:
    """UI 미리보기 카드용 대표 색상(실제 폼 외형 근사)."""
    return {
        "background": background,
        "text": text,
        "accent": accent,
        "buttonText": button_text,
        "inputBorder": input_border,
    }


# 기본 제공 디자인 프리셋. 업데이트로 확장 가능.
# styles=None → Tally 기본 외형(설정 미전송). preview는 UI 미리보기 전용(전송 안 함).
DESIGNS: List[Dict[str, Any]] = [
    {
        "code": "default",
        "name": "기본(밝은)",
        "description": "Tally 기본 밝은 외형",
        "styles": None,
        "preview": _preview("#3b82f6"),
    },
    {
        "code": "dark",
        "name": "다크",
        "description": "어두운 배경 테마",
        "styles": {"theme": "DARK", "font": dict(_KR_FONT)},
        "preview": _preview(
            "#818cf8", background="#1a1a1e", text="#e5e7eb", input_border="#3f3f46"
        ),
    },
    {
        "code": "brand_blue",
        "name": "브랜드 블루",
        "description": "밝은 배경 · 파란 강조/버튼",
        "styles": _custom("#2563eb"),
        "preview": _preview("#2563eb"),
    },
    {
        "code": "brand_green",
        "name": "내추럴 그린",
        "description": "밝은 배경 · 초록 강조/버튼",
        "styles": _custom("#059669"),
        "preview": _preview("#059669"),
    },
    {
        "code": "warm_orange",
        "name": "웜 오렌지",
        "description": "밝은 배경 · 주황 강조/버튼",
        "styles": _custom("#ea580c"),
        "preview": _preview("#ea580c"),
    },
    {
        "code": "minimal_mono",
        "name": "미니멀 모노",
        "description": "밝은 배경 · 무채색(차분한 검정 강조)",
        "styles": _custom("#111827", text="#111827"),
        "preview": _preview("#111827", text="#111827"),
    },
]


def get_design(code: str) -> Dict[str, Any]:
    """코드로 디자인 프리셋 조회(없으면 KeyError)."""
    for d in DESIGNS:
        if d["code"] == code:
            return d
    raise KeyError(f"알 수 없는 문의폼 디자인: {code}")


def get_styles(code: Optional[str]) -> Optional[Dict[str, Any]]:
    """디자인 코드 → Tally styles 객체(없거나 default면 None)."""
    if not code or code == DEFAULT_DESIGN_CODE:
        return None
    try:
        return get_design(code).get("styles")
    except KeyError:
        return None


def list_designs() -> List[Dict[str, Any]]:
    """UI용 디자인 목록(코드·이름·설명·미리보기 색상)."""
    return [
        {
            "code": d["code"],
            "name": d["name"],
            "description": d["description"],
            "preview": d.get("preview") or {},
        }
        for d in DESIGNS
    ]
