"""모듈이 정한 시각에, 제 일을, 정직한 결과로.

플로우 107 에서 한 번에 드러난 네 가지 결함을 못 박는다.

1. 모듈마다 fixed_times 를 정했는데 3시간 간격으로 돌았다
   — keyword/title_gen 이 fixed_time 게이트에서 빠져 있었다
2. 07시에 깨어난 김에 10시 모듈까지 같이 돌았다
3. '제목/도메인 수집' 모듈이 수집 대신 **생성기**를 돌렸다
   — 스케줄러만 TitleModuleRunner 를 직접 불렀다
4. AI 가 없어 0편인 회차가 SUCCESS 로 남았다
"""
import pathlib
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.scheduler.flow_scheduler import (
    _SELF_SCHEDULED,
    FlowScheduler,
)

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[2]


def _module(name, times, order, code="title_gen"):
    return SimpleNamespace(
        name=name, execution_order=order, settings={
            "schedule": {"schedule_mode": "fixed_time", "fixed_times": times}},
        module_type=SimpleNamespace(code=code))


def _flow(*modules):
    return SimpleNamespace(
        id=107, module_links=[SimpleNamespace(module=m) for m in modules])


def _sched():
    return FlowScheduler.__new__(FlowScheduler)


# 사용자가 실제로 등록한 구성
CHAIN = lambda: (_module("제목/도메인 수집", ["07:00", "19:00"], 0),
                 _module("URL추출기", ["09:00"], 1),
                 _module("제목 생성기", ["10:00"], 2))


class TestFixedTimeApplies:
    @pytest.mark.parametrize("action", ["keyword", "title_gen"])
    def test_self_scheduled(self, action):
        """여기 빠지면 fixed_times 를 넣어도 폴백 간격으로 돈다."""
        assert action in _SELF_SCHEDULED

    def test_both_gates_use_the_constant(self):
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        assert src.count("action_type in _SELF_SCHEDULED") == 2
        # 옛 하드코딩이 남아 있으면 한쪽만 고쳐진 것이다
        assert '"collect", "data", "bulk_collect")' not in src

    def test_nested_schedule_read(self):
        mods = CHAIN()
        times = FlowScheduler._module_fixed_times(
            _sched(), mods[0], "title_gen")
        assert times == ["07:00", "19:00"]

    def test_interval_mode_returns_none(self):
        m = _module("간격", ["07:00"], 0)
        m.settings["schedule"]["schedule_mode"] = "interval"
        assert FlowScheduler._module_fixed_times(
            _sched(), m, "title_gen") is None


class TestNextRunIsUnion:
    """첫 모듈만 보면 나머지 모듈의 시각은 영영 오지 않는다."""

    @pytest.mark.parametrize("now,expected", [
        ("08:00", "09:00"),   # 수집(07,19) 다음이 아니라 추출(09)
        ("09:30", "10:00"),
        ("11:00", "19:00"),
        ("20:00", "07:00"),   # 다음 날
    ])
    def test_earliest_across_modules(self, now, expected):
        mods = CHAIN()
        at = datetime.strptime(f"2026-09-05 {now}", "%Y-%m-%d %H:%M").replace(
            tzinfo=KST)
        slots = []
        for m in mods:
            slots += FlowScheduler._parse_times(
                FlowScheduler._module_fixed_times(_sched(), m, "title_gen"), at)
        assert min(slots).strftime("%H:%M") == expected


class TestOnlyDueModulesRun:
    @pytest.mark.parametrize("now,expected", [
        ("07:00", ["제목/도메인 수집"]),
        ("09:00", ["URL추출기"]),
        ("10:00", ["제목 생성기"]),
        ("19:00", ["제목/도메인 수집"]),
        ("13:53", []),          # 사용자가 로그를 본 시각 — 아무것도 아니다
    ])
    def test_due_now(self, now, expected):
        mods = CHAIN()
        at = datetime.strptime(f"2026-09-05 {now}", "%Y-%m-%d %H:%M").replace(
            tzinfo=KST)
        due = [m.name for m in mods
               if FlowScheduler._is_due_now(
                   FlowScheduler._module_fixed_times(_sched(), m, "title_gen"),
                   at)]
        assert due == expected

    def test_late_wakeup_still_counts(self):
        """재기동으로 몇 분 늦게 깨어나도 그 회차를 건너뛰지 않는다."""
        at = datetime(2026, 9, 5, 7, 20, tzinfo=KST)
        assert FlowScheduler._is_due_now(["07:00"], at)

    def test_far_off_does_not_count(self):
        at = datetime(2026, 9, 5, 8, 30, tzinfo=KST)
        assert not FlowScheduler._is_due_now(["07:00"], at)

    def test_midnight_wrap(self):
        """00:00 모듈이 00:10 에 깨어나도 어제 것으로 새지 않는다."""
        at = datetime(2026, 9, 5, 0, 10, tzinfo=KST)
        assert FlowScheduler._is_due_now(["00:00"], at)


class TestRightExecutor:
    def test_scheduler_uses_workbench(self):
        """수동 경로와 같은 실행기. 아니면 수집 모듈이 생성기를 돌린다."""
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _execute_title_module"):
                   src.index("async def _execute_collect_module")]
        assert "TitleWorkbench(" in body
        # 주석에는 남아 있어도 되지만 **호출**은 없어야 한다
        assert "TitleModuleRunner(" not in body

    def test_manual_path_unchanged(self):
        src = (ROOT / "app/routers/flows_execute.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _execute_title_module"):
                   src.index("async def _execute_collect_module")]
        assert "TitleWorkbench" in body


class TestHonestStatus:
    def test_ai_missing_is_not_success(self):
        from app.services.title_collect.workbench import _succeeded

        out = {"gen": {"l1": {"made": 0,
                              "error": "AI 제공자가 지정되지 않았습니다"}}}
        assert _succeeded(out) is False

    def test_partial_success_is_success(self):
        """수집은 됐는데 생성만 실패한 회차까지 실패로 적으면 진짜 실패가 묻힌다."""
        from app.services.title_collect.workbench import _succeeded

        out = {"collect": {"saved": 5, "search": {"saved": 5}},
               "gen": {"l1": {"made": 0, "error": "AI 없음"}}}
        assert _succeeded(out) is True

    def test_nothing_to_do_is_skipped(self):
        from app.services.title_collect.workbench import _skipped, _succeeded

        out = {"collect": {"saved": 0,
                           "search": {"saved": 0, "skipped": True}}}
        assert _skipped(out) is True
        assert _succeeded(out) is True

    def test_real_work_is_not_skipped(self):
        from app.services.title_collect.workbench import _skipped

        assert _skipped({"gen": {"l1": {"made": 22}}}) is False

    def test_run_for_module_sets_both(self):
        src = (ROOT / "app/services/title_collect/workbench.py").read_text(
            encoding="utf-8")
        assert src.count('out["success"] = _succeeded(out)') == 2
        assert src.count('out["skipped"] = _skipped(out)') == 2


class TestActionLabel:
    @pytest.mark.parametrize("settings,expected", [
        ({"title": {"collect": {"enabled": True, "search_enabled": True,
                                "extract_enabled": False},
                    "gen": {"enabled": False}}}, "제목 수집"),
        ({"title": {"collect": {"enabled": True, "search_enabled": False,
                                "extract_enabled": True},
                    "gen": {"enabled": False}}}, "URL 추출"),
        ({"title": {"collect": {"enabled": False},
                    "gen": {"enabled": True, "l1_enabled": True,
                            "l3_enabled": False}}}, "제목 생성"),
    ])
    def test_title_label(self, settings, expected):
        from app.services.module_action_label import label_for

        assert label_for("title_gen", settings, "모듈명") == expected

    def test_multiple_actions_joined(self):
        from app.services.module_action_label import label_for

        settings = {"title": {
            "collect": {"enabled": True, "search_enabled": True,
                        "extract_enabled": True},
            "gen": {"enabled": False}}}
        assert label_for("title_gen", settings, "x") == "제목 수집 + URL 추출"

    def test_falls_back_to_module_name(self):
        from app.services.module_action_label import label_for

        settings = {"title": {"collect": {"enabled": False},
                              "gen": {"enabled": False}}}
        assert label_for("title_gen", settings, "제목 생성기") == "제목 생성기"

    def test_keyword_label(self):
        from app.services.module_action_label import label_for

        assert label_for(
            "keyword", {"keyword": {"steps": ["collect"]}}, "x") == "키워드 수집"

    def test_chain_writes_label_not_module_name(self):
        src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")
        body = src[src.index("async def _execute_module_chain"):
                   src.index("async def _execute_title_module")]
        assert "module_name=label_for(" in body

    def test_log_displays_the_label(self):
        src = (ROOT / "app/routers/dashboard_logs.py").read_text(
            encoding="utf-8")
        assert "action_text = log.module_name.strip()" in src
