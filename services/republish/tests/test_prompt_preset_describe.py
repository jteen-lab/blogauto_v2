"""모듈에 적용된 프리셋 표시 (2026-08-30).

플로우 수정 화면의 모듈 카드에 "지금 어떤 프롬프트로 생성되는지"가 뜨는지 지킨다.
실운영 14개 모듈 전부가 판정되는 것을 확인하고 만든 기능이라, 판정 경로 4가지가
모두 살아 있어야 한다.
"""
import json
import re
from pathlib import Path

from app.services.prompt_builder.blocks import PERSONAS, READERS, PATTERNS, TONES
from app.services.prompt_builder.describe import (
    describe,
    describe_approval,
    matching_preset,
    resolve_axes,
)
from app.services.prompt_builder.presets import PRESETS
from app.services.generation.adsense_prompt_switch import (
    APPROVAL_PRESET_KEY,
    approval_presets,
)

ROOT = Path(__file__).resolve().parents[1]


def _settings(template: str, **extra) -> dict:
    return {"content_generation": {"user_prompt_template": template}, **extra}


def _body(blocks, code: str) -> str:
    return next(b["body"] for b in blocks if b["code"] == code)


def test_snapshot_wins_over_inference():
    """빌더가 남긴 축 스냅샷이 있으면 본문 역추론보다 우선한다."""
    preset = next(p for p in PRESETS if not p.get("full_prompt"))
    settings = {
        "content_generation": {
            "user_prompt_template": "손으로 고친 본문",
            "builder_selection": {
                "persona": preset["persona"],
                "reader": preset["reader"],
                "pattern": preset["pattern"],
                "tone": preset["tone"],
            },
        }
    }
    assert describe(settings) == preset["label"]


def test_infers_preset_from_template_body():
    """스냅샷이 없어도 블록 본문 대조로 프리셋을 되짚는다."""
    preset = next(p for p in PRESETS if not p.get("full_prompt"))
    template = "\n\n".join([
        _body(PERSONAS, preset["persona"]),
        _body(READERS, preset["reader"]),
        _body(PATTERNS, preset["pattern"]),
        _body(TONES, preset["tone"]),
    ])
    assert matching_preset(_settings(template)) is not None
    assert describe(_settings(template)) == preset["label"]


def test_partial_axes_fall_back_to_labels():
    """축 일부만 잡히면 프리셋 대신 고른 항목 이름을 보여준다."""
    persona = PERSONAS[0]
    out = describe(_settings(persona["body"]))
    assert out.startswith("직접 조합")
    assert persona["label"] in out


def test_full_prompt_pasted_into_template_is_recognized():
    """전용 프롬프트를 통째로 붙여넣은 모듈도 이름이 뜬다.

    실운영 모듈 2개(수작남·애드센스 프롬프트)가 이 형태였다.
    """
    preset = next(p for p in PRESETS if p.get("full_prompt"))
    assert describe(_settings(preset["full_prompt"])) == preset["label"]


def test_handwritten_prompt_says_so_instead_of_blank():
    """손으로 쓴 프롬프트는 빈칸이 아니라 '직접 작성'이다.

    빈칸이면 사용자가 표시 고장과 구분하지 못한다.
    """
    assert describe(_settings("제목: {title}\n위 제목으로 글을 써주세요.")) == "직접 작성"


def test_no_prompt_is_blank():
    """프롬프트 자체가 없으면 칩을 만들지 않는다."""
    assert describe({}) == ""
    assert describe(_settings("   ")) == ""


def test_approval_preset_label_separate_from_normal():
    """승인 전 프롬프트는 평소 프리셋과 따로 표시된다."""
    ap = approval_presets()[0]
    settings = _settings("직접 쓴 평소 프롬프트", **{APPROVAL_PRESET_KEY: ap["code"]})
    assert describe_approval(settings) == ap["label"]
    assert describe(settings) == "직접 작성"
    assert describe_approval(_settings("x")) == ""


def test_module_response_fills_fields_for_prompt_type():
    """응답 스키마가 경로와 무관하게 값을 채운다(플로우 상세 포함)."""
    from datetime import datetime

    from app.schemas.module import ModuleResponse

    preset = next(p for p in PRESETS if p.get("full_prompt"))
    now = datetime(2026, 8, 30)
    payload = {
        "id": 1, "user_id": 1, "name": "테스트", "description": None,
        "module_type": {
            "id": 1, "code": "prompt", "name": "프롬프트",
            "display_order": 1, "created_at": now,
        },
        "settings": _settings(preset["full_prompt"]),
        "created_at": now, "updated_at": now,
    }
    resp = ModuleResponse.model_validate(payload)
    assert resp.prompt_preset == preset["label"]

    payload["module_type"]["code"] = "collect"
    assert ModuleResponse.model_validate(payload).prompt_preset is None


def test_flow_card_renders_the_server_value():
    """JS가 서버 필드명을 그대로 읽는지 — 이름이 어긋나면 조용히 빈칸이 된다."""
    js = (ROOT / "app/static/js/flows/form.js").read_text(encoding="utf-8")
    assert "module.prompt_preset" in js
    assert "module.adsense_approval_preset_label" in js
    for type_code in ("'prompt'", "'generate'"):
        assert type_code in js
    # 카드 정보 함수가 실제로 프리셋을 밀어 넣는지
    assert "pushPresetInfo(info, module)" in js


def test_card_template_shows_full_name_on_hover():
    """프리셋 이름은 잘리므로 title 로 전체가 보여야 한다."""
    html = (ROOT / "app/templates/flows/_module_select_card.html").read_text(
        encoding="utf-8"
    )
    assert ':title="info.value"' in html


def test_cache_token_bumped_for_form_js():
    """JS를 고쳤으면 ?v= 도 올라가야 브라우저가 새로 받는다."""
    html = (ROOT / "app/templates/flows/list.html").read_text(encoding="utf-8")
    m = re.search(r"flows/form\.js\?v=(\w+)", html)
    assert m and m.group(1) >= "20260830"
