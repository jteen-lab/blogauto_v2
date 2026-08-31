"""키워드 모듈 — 자동화 (2026-08-31).

`keyword_lab` 은 화면에서 버튼을 눌러야만 돌아 플로우·오토런·동작 로그
어디에도 붙지 않았다. 재고가 말라도 아무도 채우지 않는다.

**수동과 자동이 같은 실행기를 탄다.** 다른 코드를 타면 화면에서는 되는데
자동에서만 안 되는 일이 생긴다.

순서도: docs/flowcharts/keyword_module.md
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.keyword_lab.expander import combine, expand
from app.services.keyword_lab.settings import (
    DEFAULT_MODIFIERS, KeywordModuleSettings,
)
from app.services.keyword_lab.title_maker import SOURCE, TitleMaker

ROOT = Path(__file__).resolve().parents[2]


# ── 설정 ─────────────────────────────────────────────────
def test_defaults_are_conservative() -> None:
    """검색광고는 일일 호출 제한이 있다. 한 번에 다 돌리지 않는다."""
    cfg = KeywordModuleSettings.parse(None)
    assert cfg.seed_limit <= 10
    assert cfg.min_inventory > 0, "재고 하한이 없으면 매번 돈다"
    assert cfg.recurse_adopted is True, "재귀가 꺼지면 소재가 고갈된다"


def test_settings_read_from_module_shape() -> None:
    """모듈 settings 와 같은 모양을 읽어야 한다."""
    cfg = KeywordModuleSettings.parse({
        "keyword": {"seeds": "전기기사, 컴활", "min_volume": 300,
                    "titles_per_keyword": 99},
        "schedule": {"interval_minutes": 120},
    })
    assert cfg.seeds == ["전기기사", "컴활"]
    assert cfg.min_volume == 300
    assert cfg.titles_per_keyword == 10, "터무니없는 값은 잘라야 한다"
    assert cfg.interval_minutes == 120


def test_bad_values_fall_back() -> None:
    cfg = KeywordModuleSettings.parse({"keyword": {
        "min_volume": "많이", "min_saturation": None, "modifiers": []}})
    assert cfg.min_volume == 100
    assert cfg.min_saturation == 0.2
    assert cfg.modifiers == DEFAULT_MODIFIERS, "비우면 기본값으로"


# ── 시드 확장 ────────────────────────────────────────────
def test_combine_includes_the_seed_itself() -> None:
    """시드가 좋은 키워드일 때 놓치면 안 된다."""
    out = combine("요리레시피", ["방법", "추천"])
    assert out[0] == "요리레시피"
    assert "요리레시피방법" in out


def test_combine_has_no_spaces() -> None:
    """네이버가 공백 든 키워드를 거부한다(400, 11001)."""
    for kw in combine("전기기사", ["실기 준비", "후기"]):
        assert " " not in kw


def test_expand_dedupes() -> None:
    cfg = KeywordModuleSettings.parse({"keyword": {"modifiers": ["방법"]}})
    seeds = [{"seed": "요리", "topic_id": 1, "subtopic_id": 2},
             {"seed": "요리", "topic_id": 1, "subtopic_id": 2}]
    out = [x["seed"] for x in expand(seeds, cfg)]
    assert out == ["요리", "요리방법"]


def test_expand_keeps_category() -> None:
    """결합해도 원래 카테고리를 잃으면 안 된다."""
    cfg = KeywordModuleSettings.parse({"keyword": {"modifiers": ["방법"]}})
    out = expand([{"seed": "요리", "topic_id": 12, "subtopic_id": 53}], cfg)
    assert all(x["topic_id"] == 12 for x in out)
    assert all(x["origin"] == "요리" for x in out)


# ── 제목 생성 ────────────────────────────────────────────
def test_title_parse_strips_numbering() -> None:
    out = TitleMaker._parse(
        '1. 전기기사 실기 몇 번 만에 붙나요\n'
        '- "전기기사 실기 준비 기간 정리"\n'
        '짧음\n'
        '전기기사 실기 몇 번 만에 붙나요\n', 5)
    assert out == ["전기기사 실기 몇 번 만에 붙나요", "전기기사 실기 준비 기간 정리"]


def test_titles_go_to_the_existing_inventory() -> None:
    """기존 재고 구조를 그대로 써야 min_inventory 가 이들을 센다."""
    src = (ROOT / "app/services/keyword_lab/title_maker.py").read_text(
        encoding="utf-8")
    assert "MainTitle(" in src
    assert 'status="available"' in src
    assert SOURCE == "keyword_module", "기존 transfer 와 구분돼야 비교가 된다"


# ── 실행기: 재고 기반 ────────────────────────────────────
@pytest.mark.asyncio
async def test_skips_when_inventory_is_enough() -> None:
    """매번 도는 것은 API 낭비다."""
    from app.services.keyword_lab.runner import KeywordModuleRunner

    runner = KeywordModuleRunner(db=SimpleNamespace(), user_id=1)
    runner._blog = AsyncMock(return_value=SimpleNamespace(id=19))
    runner._inventory = AsyncMock(return_value=100)

    result = await runner.run({"keyword": {"min_inventory": 30}}, blog_id=19)
    assert result["skipped"] is True
    assert "재고 충분" in result["message"]


@pytest.mark.asyncio
async def test_force_ignores_inventory() -> None:
    """수동 테스트는 재고가 충분해도 돌 수 있어야 한다."""
    from app.services.keyword_lab.runner import KeywordModuleRunner

    runner = KeywordModuleRunner(db=SimpleNamespace(), user_id=1)
    runner._blog = AsyncMock(return_value=SimpleNamespace(id=19))
    runner._inventory = AsyncMock(return_value=100)
    runner._user_settings = AsyncMock(return_value=None)

    result = await runner.run({"keyword": {}}, blog_id=19, force=True)
    # 설정이 없어 실패하지만, 재고로 건너뛰지는 않았다
    assert result.get("skipped") is not True
    assert "API 키" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_disabled_module_does_nothing() -> None:
    from app.services.keyword_lab.runner import KeywordModuleRunner

    runner = KeywordModuleRunner(db=SimpleNamespace(), user_id=1)
    result = await runner.run({"keyword": {"enabled": False}})
    assert result["skipped"] is True


# ── 스케줄러 연결 ────────────────────────────────────────
def test_scheduler_handles_keyword_action() -> None:
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert src.count('action_type == "keyword"') == 2, \
        "수동 실행·스케줄 콜백 두 경로 모두 필요하다"
    assert "_execute_keyword_module" in src


def test_keyword_interval_is_not_decided_by_growth_profile() -> None:
    """성장 프로파일은 '얼마나 자주 발행할까' 를 정한다.

    키워드 생산은 '재고가 부족한가' 로 돌아야 한다. 축이 다르다.
    """
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert 'if gp_settings and module_type_code != "keyword"' in src


def test_keyword_is_not_gp_required() -> None:
    """GP 가 없어도 등록돼야 한다 — 키워드는 GP 와 무관하다."""
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    block = re.search(r"GP_REQUIRED_ACTIONS = \{([^}]*)\}", src)
    assert block and "keyword" not in block.group(1)


# ── 수동·자동이 같은 코드를 탄다 ─────────────────────────
def test_manual_run_uses_the_same_runner() -> None:
    """다른 코드를 타면 화면에서는 되는데 자동에서만 안 되는 일이 생긴다."""
    router = (ROOT / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
    sched = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert "KeywordModuleRunner" in router
    assert "KeywordModuleRunner" in sched


def test_manual_run_exists_on_screen() -> None:
    """모듈이 되어도 사람이 눌러 돌릴 수 있어야 한다."""
    page = (ROOT / "app/templates/keyword_lab/index.html").read_text(
        encoding="utf-8")
    assert "runModule()" in page
    assert "모듈 한 회차 실행" in page


# ── 모듈 타입 등록 ───────────────────────────────────────
def test_module_type_registered_everywhere() -> None:
    """한 곳이라도 빠지면 화면에서 만들 수 없거나 플로우에 못 붙는다."""
    checks = {
        "app/static/js/modules/list.js": ["keyword: '🔑'", "'keyword': '키워드'"],
        "app/templates/modules/list.html": ["'code': 'keyword'"],
        "app/templates/flows/_form.html": ["activeModuleTab = 'keyword'"],
        "app/static/js/modules/form.js": ["type_code === 'keyword'"],
        "app/static/js/modules/keyword-form-template.js": ["formData.keyword"],
    }
    for path, needles in checks.items():
        src = (ROOT / path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in src, f"{path}: {needle}"


def test_migration_does_not_break_existing_flows() -> None:
    """모듈 타입은 DB 행이라 플로우가 물고 있으면 지우면 안 된다."""
    src = (ROOT / "alembic/versions/057_add_keyword_module_type.py").read_text(
        encoding="utf-8")
    assert "in_use" in src and "return" in src
