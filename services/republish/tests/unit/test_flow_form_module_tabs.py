"""플로우 폼의 모듈 탭이 실제 모듈 타입과 맞는지 지킨다.

수집·대량 수집 모듈 타입은 없앴는데(alembic 073/074) 탭은 남아 있었다.
눌러도 목록이 늘 비어 있는 탭이다 — 사용자는 모듈이 없는 건지 화면이
고장난 건지 알 수 없다.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FORM = (ROOT / "app/templates/flows/_form.html").read_text(encoding="utf-8")


def _tabs() -> list:
    return re.findall(r"activeModuleTab = '([a-z_]+)'", FORM)


class TestTabsMatchModuleTypes:
    @pytest.mark.parametrize("dead", ["collect", "bulk_collect"])
    def test_removed_types_have_no_tab(self, dead):
        assert dead not in _tabs()

    @pytest.mark.parametrize("live", ["keyword", "title_gen", "data",
                                      "growth_profile", "contact_form"])
    def test_live_types_have_a_tab(self, live):
        assert live in _tabs()

    def test_prompt_and_generate_share_one_tab(self):
        assert "prompt_generate" in _tabs()

    def test_every_tab_resolves_to_a_seeded_type(self):
        """탭이 있는데 모듈 타입이 없으면 영원히 빈 탭이다."""
        from app.models.module_type import ModuleType

        seeded = {t["code"] for t in ModuleType.get_default_types()}
        seeded.add("prompt_generate")   # prompt + generate 합친 탭
        # keyword·title_gen 은 마이그레이션(057 등)으로 들어간다
        seeded |= {"keyword", "title_gen"}
        assert set(_tabs()) <= seeded

    def test_no_dead_count_badges_left(self):
        """탭만 지우고 배지를 남기면 죽은 코드가 쌓인다."""
        for dead in ("'collect'", "'bulk_collect'"):
            assert f"getSelectedCountByTypes([{dead}])" not in FORM

    def test_default_tab_still_exists(self):
        js = (ROOT / "app/static/js/flows/form.js").read_text(encoding="utf-8")
        default = re.search(r"activeModuleTab: '([a-z_]+)'", js).group(1)
        assert default in _tabs()
