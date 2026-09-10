"""워커 실패가 플로우에 되먹여지는가.

스케줄러는 Celery 에 넘긴 순간 성공으로 적는다. 워커에서 실제 생성이 실패해도
통계가 성공으로 남으면 **아무도 실패를 모른다.**

실측(2026-09-09 머니조아): 생성 3회 연속 실패인데 상태는 `성공 2 · 실패 0 ·
연속실패 0` 이었고, 다음 실행은 정상 주기대로 하루 뒤로 잡혀 하루가 날아갔다.
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestRecordWorkerFailure:
    """디스패치 때 낙관적으로 적은 성공을 실패로 되돌린다."""

    def _state(self, ok=2, ng=0, streak=0, total=2):
        from app.models.flow_execution_state import FlowExecutionState

        state = FlowExecutionState()
        state.successful_executions = ok
        state.failed_executions = ng
        state.consecutive_failures = streak
        state.total_executions = total
        return state

    def test_success_becomes_failure(self):
        state = self._state()
        state.record_worker_failure()
        assert state.successful_executions == 1
        assert state.failed_executions == 1
        assert state.consecutive_failures == 1

    def test_total_is_not_touched(self):
        """실행 횟수 자체는 맞다 — 결과만 틀렸다."""
        state = self._state(total=2)
        state.record_worker_failure()
        assert state.total_executions == 2

    def test_streak_accumulates(self):
        """연속 5회면 스케줄러가 일시정지시킨다. 그 카운트가 살아 있어야 한다."""
        state = self._state(ok=5, streak=0)
        for _ in range(3):
            state.record_worker_failure()
        assert state.consecutive_failures == 3

    def test_never_goes_negative(self):
        state = self._state(ok=0)
        state.record_worker_failure()
        assert state.successful_executions == 0
        assert state.failed_executions == 1


class TestOutcome:
    """스킵을 실패로 세면 연속 실패 일시정지가 잘못 걸린다."""

    @pytest.mark.parametrize("result,expected", [
        ({"success": True}, "success"),
        ({"success": False}, "failed"),
        ({"success": True, "skipped": True}, "skipped"),
        ({"success": False, "skipped": True}, "skipped"),
        ({}, "failed"),
    ])
    def test_outcome(self, result, expected):
        from app.core.celery_flow_state import outcome_of

        assert outcome_of(result) == expected


class TestRetryPicksAnotherTitle:
    """같은 제목으로 재시도하면 결과가 같다.

    실패 사유가 제목에 딸린 것이면(근거 부족·중복) 세 번을 걸어도 세 번 다
    실패한다. 재시도에서는 제목을 풀어 재고에서 다시 고르게 한다.
    """

    SRC = (ROOT / "app/core/celery_tasks.py").read_text(encoding="utf-8")

    def _retry_call(self):
        """generate_content 안의 self.retry(...) 호출 노드."""
        tree = ast.parse(self.SRC)
        func = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "generate_content"
        )
        calls = [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "retry"
            and any(k.arg == "exc" for k in n.keywords)
        ]
        assert calls, "예외 재시도 호출을 찾지 못했다"
        return calls[0]

    def test_retry_overrides_kwargs(self):
        call = self._retry_call()
        assert any(k.arg == "kwargs" for k in call.keywords), \
            "kwargs 를 넘기지 않으면 Celery 가 원래 인자를 그대로 쓴다"

    def test_title_is_unpinned_on_retry(self):
        call = self._retry_call()
        kw = next(k for k in call.keywords if k.arg == "kwargs")
        pairs = {
            k.value: v for k, v in zip(kw.value.keys, kw.value.values)
            if isinstance(k, ast.Constant)
        }
        assert "title_id" in pairs, "재시도 인자에 title_id 가 없다"
        assert isinstance(pairs["title_id"], ast.Constant)
        assert pairs["title_id"].value == 0, \
            "재시도는 title_id=0 이어야 워커가 다른 제목을 고른다"

    def test_other_args_are_carried_over(self):
        """블로그·모듈·플로우가 빠지면 재시도가 엉뚱한 곳에서 돈다."""
        call = self._retry_call()
        kw = next(k for k in call.keywords if k.arg == "kwargs")
        keys = {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
        assert {"blog_id", "module_id", "flow_id", "user_id",
                "stage_params_dict", "force"} <= keys


class TestWiring:
    SRC = (ROOT / "app/core/celery_tasks.py").read_text(encoding="utf-8")

    def test_generate_syncs_state(self):
        assert "sync_state(db, blog_id, \"generate\", result)" in self.SRC

    def test_state_module_is_separate(self):
        """celery_tasks.py 가 500줄을 넘지 않도록 분리했다."""
        assert (ROOT / "app/core/celery_flow_state.py").exists()
        assert len(self.SRC.splitlines()) <= 500
