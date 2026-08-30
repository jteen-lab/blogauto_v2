"""애드센스 승인 시 프롬프트 전환·정지 판정 테스트 (2026-08-30).

규칙
    승인 전            → 아무것도 하지 않는다(승인용 프롬프트 유지)
    승인 + 승인후 지정  → 교체
    승인 + 미지정      → 생성 정지
"""
from types import SimpleNamespace

import pytest

from app.services.generation import adsense_prompt_switch as sw

APPROVAL = (
    "당신은 해당 분야를 오래 다뤄 온 편집자입니다.\n"
    "■ 최우선 원칙 — 정보이득(Information Gain)\n"
    "사람을 위한(people-first) 고품질 글을 쓰세요."
)
NICHE = "제목: {title}\n✦ 화자 — 데이터 분석가"


def _settings(template=APPROVAL, post="", blogs=(15,)):
    return {
        "blogs": list(blogs),
        "content_generation": {"user_prompt_template": template},
        "post_approval_prompt": post,
    }


def _blog(status="approved", blog_id=15):
    return SimpleNamespace(id=blog_id, name="슈마즈", adsense_status=status)


# ---------- 승인용 프롬프트 판정 ----------

def test_detects_approval_prompt_by_signature():
    """프리셋 코드가 저장되지 않아 본문 지문으로 판정한다."""
    assert sw.uses_approval_prompt(_settings()) is True


def test_niche_prompt_is_not_approval():
    assert sw.uses_approval_prompt(_settings(template=NICHE)) is False


def test_partial_signature_is_not_enough():
    """문구 하나만 있으면 승인용으로 보지 않는다(오탐 방지)."""
    partial = {"content_generation": {"user_prompt_template": "people-first 로 씁니다"}}
    assert sw.uses_approval_prompt(partial) is False


def test_empty_template():
    assert sw.uses_approval_prompt({}) is False


def test_survives_user_edits_around_signature():
    edited = _settings(template="앞말\n" + APPROVAL + "\n뒷말 추가")
    assert sw.uses_approval_prompt(edited) is True


# ---------- 생성 정지 ----------

def test_blocks_when_approved_without_replacement():
    reason = sw.block_reason(_settings(post=""), _blog("approved"))
    assert reason is not None
    assert "승인 후 사용할 프롬프트" in reason


def test_no_block_before_approval():
    """승인 전에는 승인용 프롬프트로 계속 생성한다."""
    assert sw.block_reason(_settings(post=""), _blog("preparing")) is None


def test_no_block_when_replacement_exists():
    assert sw.block_reason(_settings(post=NICHE), _blog("approved")) is None


def test_no_block_when_already_niche_prompt():
    """이미 니치 프롬프트면 승인돼도 멈출 이유가 없다."""
    assert sw.block_reason(_settings(template=NICHE), _blog("approved")) is None


def test_blank_replacement_counts_as_missing():
    assert sw.block_reason(_settings(post="   "), _blog("approved")) is not None


# ---------- 전환 ----------

def test_needs_switch_only_when_approved_with_replacement():
    assert sw.needs_switch(_settings(post=NICHE), _blog("approved")) is True
    assert sw.needs_switch(_settings(post=NICHE), _blog("preparing")) is False
    assert sw.needs_switch(_settings(post=""), _blog("approved")) is False


def test_switched_settings_replaces_template():
    result = sw.switched_settings(_settings(post=NICHE))
    assert result["content_generation"]["user_prompt_template"] == NICHE


def test_switch_does_not_mutate_original():
    original = _settings(post=NICHE)
    sw.switched_settings(original)
    assert original["content_generation"]["user_prompt_template"] == APPROVAL


# ---------- 1:N 제약 ----------

def test_persist_allowed_for_single_blog_module():
    assert sw.can_persist_switch(_settings(blogs=(15,)), _blog(blog_id=15)) is True


def test_persist_blocked_for_multi_blog_module():
    """블로그마다 승인 상태가 다를 수 있어 DB 통째 교체는 성립하지 않는다."""
    assert sw.can_persist_switch(_settings(blogs=(15, 16)), _blog(blog_id=15)) is False


def test_persist_blocked_when_blog_not_in_module():
    assert sw.can_persist_switch(_settings(blogs=(16,)), _blog(blog_id=15)) is False


def test_module_blog_ids_accepts_dict_form():
    assert sw.module_blog_ids({"blogs": [{"id": 15}, 16]}) == [15, 16]


def test_module_blog_ids_empty():
    assert sw.module_blog_ids({}) == []


# ---------- generator 시그니처 (S1 회귀) ----------

def test_generator_accepts_module_settings():
    """호출자가 해석한 설정을 넘길 수 있어야 한다.

    이 인자가 없으면 generator 가 DB 원본을 다시 읽어 전환이 통째로 무시된다.
    2026-08-28 구현이 그래서 죽은 코드였다.
    """
    import inspect

    from app.services.generation.generator import ContentGenerator

    for name in ("generate", "_execute_pipeline"):
        params = inspect.signature(getattr(ContentGenerator, name)).parameters
        assert "module_settings" in params, f"{name} 에 module_settings 없음"


def test_generator_prefers_passed_settings_over_db():
    """넘겨받은 설정이 있으면 그것을 쓴다(소스 확인)."""
    import inspect

    from app.services.generation.generator import ContentGenerator

    src = inspect.getsource(ContentGenerator._execute_pipeline)
    assert "module_settings if module_settings is not None" in src


def test_flow_executor_passes_settings_and_gates():
    """실행기가 해석된 설정을 넘기고, 정지 사유를 검사해야 한다."""
    import inspect

    from app.services.generation.flow_generate_executor import FlowGenerateExecutor

    src = inspect.getsource(FlowGenerateExecutor)
    assert "module_settings=module_settings" in src, "해석된 설정을 넘기지 않음"
    assert "block_reason" in src, "생성 정지 게이트 없음"
