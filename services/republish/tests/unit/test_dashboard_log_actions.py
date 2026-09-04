"""동작로그 액션 필터가 실제 모듈 구성과 어긋나지 않는지 지킨다.

collect·bulk_collect 모듈은 없앴는데(alembic 073/074) 액션 드롭다운에는
남아 있었다. 반대로 새로 만든 keyword·title_gen 모듈은 실행 로그를
남기는데도 고를 수가 없었다. 화면과 백엔드가 갈라진 자리다.
"""
import pathlib
import re

import pytest

from app.routers.dashboard_logs import (
    _ACTION_DISPLAY,
    _COUNT_ACTIONS,
    _WORK_ACTIONS,
    _get_action_type,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "app/templates/components/global_summary.html"
SCRIPT = ROOT / "app/static/js/components/GlobalSummary.js"

# 플로우 실행기가 실제로 남기는 action 값 (flows_execute.py)
LIVE_ACTIONS = ("keyword", "title_gen")
DEAD_ACTIONS = ("collect", "bulk_collect")


def _dropdown_values() -> list:
    """액션 드롭다운의 option value 목록."""
    html = TEMPLATE.read_text(encoding="utf-8")
    start = html.index("<label class=\"text-gray-500 ml-2\">액션:</label>")
    block = html[start:html.index("</select>", start)]
    return re.findall(r'<option value="([^"]*)"', block)


class TestDropdown:
    @pytest.mark.parametrize("action", LIVE_ACTIONS)
    def test_live_module_selectable(self, action):
        assert action in _dropdown_values()

    @pytest.mark.parametrize("action", DEAD_ACTIONS)
    def test_dead_module_removed(self, action):
        assert action not in _dropdown_values()

    def test_dropdown_values_are_filterable(self):
        """고를 수 있는데 서버가 무시하면 필터가 먹히지 않는다."""
        src = (ROOT / "app/routers/dashboard_logs.py").read_text(
            encoding="utf-8")
        allowed = src[src.index("elif action_type in ("):
                      src.index("):", src.index("elif action_type in ("))]
        for value in _dropdown_values():
            if not value or value.startswith("queue_"):
                continue  # 빈 값=전체, queue_* 는 별도 분기
            assert f'"{value}"' in allowed, f"{value} 를 서버가 거른다"


class TestLabels:
    @pytest.mark.parametrize("action", LIVE_ACTIONS + DEAD_ACTIONS)
    def test_badge_not_system(self, action):
        """옛 로그도 '시스템' 으로 뭉개지 않는다."""
        assert _get_action_type(action) == action
        assert action in _ACTION_DISPLAY

    @pytest.mark.parametrize("action", LIVE_ACTIONS + DEAD_ACTIONS)
    def test_js_label_exists(self, action):
        js = SCRIPT.read_text(encoding="utf-8")
        block = js[js.index("getActionLabel(actionType)"):]
        assert f"{action}:" in block[:block.index("},")]

    def test_unknown_stays_system(self):
        assert _get_action_type("무엇인가") == "system"


class TestWorkTab:
    @pytest.mark.parametrize("action", LIVE_ACTIONS)
    def test_new_modules_in_work_tab(self, action):
        assert action in _WORK_ACTIONS

    @pytest.mark.parametrize("action", DEAD_ACTIONS)
    def test_old_logs_stay_in_work_tab(self, action):
        """서버에 남은 옛 로그가 '활동' 탭으로 옮겨가지 않게."""
        assert action in _WORK_ACTIONS

    @pytest.mark.parametrize("action", LIVE_ACTIONS)
    def test_count_summary_shown(self, action):
        """수집 계열은 '성공' 대신 건수를 보여준다."""
        assert action in _COUNT_ACTIONS
