"""오토런이 키워드·제목 모듈을 실제로 돌리는지 지킨다.

플로우 107(제목 수집/생성/추출기)이 6회 실행돼 6회 모두 실패했는데
동작로그에는 한 줄도 남지 않았다. 원인 두 가지:

1. 모듈 조회 대상 목록에 keyword/title_gen 이 빠져 module=None 이 넘어가
   ``'NoneType' object has no attribute 'user_id'`` 로 죽었다.
2. 두 분기 모두 AutorunLog 를 저장하지 않아 실패가 화면에 안 보였다.

여기에 더해 단일 조회는 첫 모듈에서 break 하므로, 한 플로우에 넣은
수집·추출·생성 3개 중 1개만 돌 뻔했다.
"""
import pathlib
import re

import pytest

SRC = (pathlib.Path(__file__).resolve().parents[2]
       / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")


class TestModuleLookup:
    def test_chain_actions_declared(self):
        from app.scheduler.flow_scheduler import _CHAIN_ACTIONS

        assert set(_CHAIN_ACTIONS) == {"keyword", "title_gen"}

    @pytest.mark.parametrize("action", ["keyword", "title_gen"])
    def test_action_reaches_module_lookup(self, action):
        """조회 대상에서 빠지면 module=None 이 실행기로 넘어간다."""
        start = SRC.index("# 모듈이 필요한 액션 타입은 모듈 찾기")
        block = SRC[start:SRC.index("# 실행 상태 조회", start)]
        assert "_CHAIN_ACTIONS" in block
        from app.scheduler.flow_scheduler import _CHAIN_ACTIONS
        assert action in _CHAIN_ACTIONS

    def test_all_modules_of_type_collected(self):
        """첫 개에서 break 하면 수집만 돌고 추출·생성이 안 돈다."""
        block = SRC[SRC.index("chain: List[Module] = []"):
                    SRC.index("elif action_type in (\n"
                              "                    \"collect\"")]
        assert "execution_order" in block   # 순서대로
        assert "break" not in block         # 전부 모은다


class TestChainRunner:
    def test_saves_a_log_per_module(self):
        """로그를 안 남기면 돌았는지 확인할 방법이 없다."""
        body = SRC[SRC.index("async def _execute_module_chain"):
                   SRC.index("async def _execute_title_module")]
        assert "_save_autorun_log" in body
        assert "action=action_type" in body
        # 모듈마다 남긴다 — 루프 안에 있어야 한다
        loop = body[body.index("for module in modules:"):]
        assert "_save_autorun_log" in loop

    def test_one_failure_does_not_stop_the_rest(self):
        body = SRC[SRC.index("async def _execute_module_chain"):
                   SRC.index("async def _execute_title_module")]
        loop = body[body.index("for module in modules:"):]
        assert "except Exception" in loop

    def test_dispatch_uses_chain_runner(self):
        branch = SRC[SRC.index('elif action_type in _CHAIN_ACTIONS:'):]
        branch = branch[:branch.index('elif action_type == "contact_form"')]
        assert "_execute_module_chain" in branch

    def test_log_label_matches_action(self):
        """title_gen 분기가 '키워드 모듈 실행 완료' 를 찍던 자리."""
        assert "키워드 모듈 실행 완료" not in SRC
        from app.scheduler.flow_scheduler import _CHAIN_ACTIONS
        assert _CHAIN_ACTIONS["title_gen"] == "제목 모듈"


class TestLoggedActionsAreFilterable:
    @pytest.mark.parametrize("action", ["keyword", "title_gen"])
    def test_dashboard_can_filter(self, action):
        """스케줄러가 남기는 action 을 동작로그가 걸러낼 수 있어야 한다."""
        from app.routers.dashboard_logs import _ACTION_DISPLAY, _WORK_ACTIONS

        assert action in _WORK_ACTIONS
        assert action in _ACTION_DISPLAY
