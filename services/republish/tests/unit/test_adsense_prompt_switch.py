"""애드센스 승인용 프리셋 선택 테스트 (2026-08-30 재설계).

설계
    user_prompt_template            = 평소 쓰는 프롬프트(승인 후 기본값)
    settings.adsense_approval_preset = 승인 전에만 쓸 프리셋 코드

    승인 전 + 프리셋 지정 → 그 프리셋으로 생성
    그 외                → 평소 프롬프트 그대로

교체가 없으므로 승인되는 순간 자동으로 평소 프롬프트로 돌아간다.
"돌아갈 프롬프트가 없어 멈추는" 상황도 생기지 않는다.
"""
from types import SimpleNamespace

from app.services.generation import adsense_prompt_switch as sw

NICHE = "제목: {title}\n✦ 화자 — 데이터 분석가"


def _settings(preset="adsense-approval", template=NICHE):
    return {
        "content_generation": {"user_prompt_template": template},
        "adsense_approval_preset": preset,
    }


def _blog(status="preparing"):
    return SimpleNamespace(id=15, name="슈마즈", adsense_status=status)


def _prompt(settings):
    return (settings.get("content_generation") or {}).get("user_prompt_template")


# ---------- 프리셋 카탈로그 ----------

def test_approval_presets_are_full_prompt_only():
    """4축 조합 프리셋은 승인용 목록에 들어오면 안 된다."""
    presets = sw.approval_presets()
    assert presets
    assert all(p.get("full_prompt") for p in presets)


def test_known_approval_preset_exists():
    assert sw.find_preset("adsense-approval") is not None


def test_unknown_preset_returns_none():
    assert sw.find_preset("없는코드") is None
    assert sw.find_preset("") is None


# ---------- 승인 전 ----------

def test_uses_approval_prompt_before_approval():
    resolved = sw.resolve(_settings(), _blog("preparing"))
    assert "정보이득(Information Gain)" in _prompt(resolved)


def test_applies_for_every_pre_approval_status():
    for status in ("none", "preparing", "applied"):
        resolved = sw.resolve(_settings(), _blog(status))
        assert _prompt(resolved) != NICHE, status


# ---------- 승인 후 ----------

def test_returns_to_normal_prompt_after_approval():
    """승인되면 지정이 있어도 무시된다 — 교체 없이 자동 복귀."""
    resolved = sw.resolve(_settings(), _blog("approved"))
    assert _prompt(resolved) == NICHE


def test_no_preset_means_normal_prompt():
    resolved = sw.resolve(_settings(preset=""), _blog("preparing"))
    assert _prompt(resolved) == NICHE


def test_resolve_does_not_mutate_original():
    original = _settings()
    sw.resolve(original, _blog("preparing"))
    assert _prompt(original) == NICHE


def test_should_use_approval_matrix():
    assert sw.should_use_approval(_settings(), _blog("preparing")) is True
    assert sw.should_use_approval(_settings(), _blog("approved")) is False
    assert sw.should_use_approval(_settings(preset=""), _blog("preparing")) is False


# ---------- 잘못된 코드 ----------

def test_invalid_preset_is_reported():
    """카탈로그가 바뀌어 코드가 사라지면 조용히 평소 프롬프트로 생성된다.
    승인용을 쓰고 있다고 착각하게 되므로 알려야 한다."""
    reason = sw.invalid_preset_reason(_settings(preset="사라진코드"))
    assert reason is not None
    assert "사라진코드" in reason


def test_valid_preset_has_no_reason():
    assert sw.invalid_preset_reason(_settings()) is None


def test_empty_preset_has_no_reason():
    assert sw.invalid_preset_reason(_settings(preset="")) is None


def test_invalid_preset_falls_back_to_normal_prompt():
    """알림과 별개로, 잘못된 코드로 엉뚱한 프롬프트가 나가지는 않는다."""
    resolved = sw.resolve(_settings(preset="사라진코드"), _blog("preparing"))
    assert _prompt(resolved) == NICHE


# ---------- 배선 회귀 ----------

def test_generator_accepts_module_settings():
    """이 인자가 없으면 generator 가 DB 원본을 다시 읽어 해석이 무시된다."""
    import inspect

    from app.services.generation.generator import ContentGenerator

    for name in ("generate", "_execute_pipeline"):
        params = inspect.signature(getattr(ContentGenerator, name)).parameters
        assert "module_settings" in params, name


def test_flow_executor_resolves_and_passes():
    import inspect

    from app.services.generation.flow_generate_executor import FlowGenerateExecutor

    src = inspect.getsource(FlowGenerateExecutor)
    assert "module_settings=module_settings" in src, "해석된 설정을 넘기지 않음"
    assert "_aps.resolve(" in src, "승인용 프롬프트 해석 없음"


def test_builder_excludes_approval_presets():
    """빌더 프리셋 목록은 '평소 프롬프트'만 다룬다."""
    from pathlib import Path

    src = Path("app/static/js/prompt_builder/app.js").read_text(encoding="utf-8")
    assert "filter((p) => !p.full_prompt)" in src


def test_approval_preset_endpoint_path_matches_router():
    """JS 가 부르는 경로와 실제 라우터 prefix 가 어긋나면 셀렉트가 빈 채로 뜬다.
    실제로 /api/v1/prompt-blocks 로 잘못 적어 404 가 났다(2026-08-30)."""
    from pathlib import Path

    from app.routers.prompt_blocks import router

    js = Path("app/static/js/modules/prompt-form.js").read_text(encoding="utf-8")
    expected = f"{router.prefix}/approval-presets"
    assert expected in js, f"JS 경로 불일치 — 기대: {expected}"


# ---------- 빌더 선택 저장/복원 (2026-08-30) ----------

def test_builder_selection_is_saved_and_loaded():
    """텍스트만 저장하면 다시 열었을 때 무엇을 골랐는지 알 수 없다.

    축 코드를 함께 저장·복원해야 프리셋·항목 강조가 살아난다.
    """
    from pathlib import Path

    js = Path("app/static/js/modules/prompt-form.js").read_text(encoding="utf-8")
    assert "builder_selection: this.promptModule.contentGeneration.builderSelection" in js
    assert "builderSelection: cg.builder_selection" in js


def test_builder_exposes_snapshot_and_restore():
    from pathlib import Path

    js = Path("app/static/js/prompt_builder/app.js").read_text(encoding="utf-8")
    for fn in ("selectionSnapshot()", "restoreSelection(snap)",
               "get activePresetLabel()", "get isAppliedToModule()"):
        assert fn in js, fn


def test_apply_passes_snapshot():
    """반영 시 텍스트와 함께 선택 스냅샷을 넘겨야 저장된다."""
    from pathlib import Path

    js = Path("app/static/js/prompt_builder/app.js").read_text(encoding="utf-8")
    assert "this.onApply(this.builtPrompt, this.selectionSnapshot())" in js


def test_builder_infers_selection_from_saved_template():
    """스냅샷이 없는 기존 모듈도 저장된 본문에서 선택을 되짚어야 한다.

    빌더 밖에서 만든 프롬프트도 각 블록 본문을 그대로 담고 있어 판정할 수 있다.
    """
    from pathlib import Path

    js = Path("app/static/js/prompt_builder/app.js").read_text(encoding="utf-8")
    assert "inferSelection(template)" in js
    assert "restoreFrom(snapshot, template)" in js


def test_adsense_state_is_merged_not_replaced():
    """편집 모드에서 adsense 객체를 통째로 바꾸면 별도로 불러온
    approvalPresetOptions 가 사라져 셀렉트가 빈 채로 뜬다(= 저장이 리셋된 것처럼 보임)."""
    from pathlib import Path

    js = Path("app/static/js/modules/prompt-form.js").read_text(encoding="utf-8")
    idx = js.index("this.promptModule.adsense = {")
    assert "...this.promptModule.adsense," in js[idx:idx + 200]
