"""긴 회차를 프록시 타임아웃 없이 받는 경로 회귀 테스트.

배경: 테스트 실행이 80.8초 걸렸는데 Caddy 의 response_header_timeout 이
    60초라 연결이 끊겼다. 브라우저는 빈 본문을 받아
    "Unexpected end of JSON input" 을 던졌다(서버는 200 이었다).

    프록시 설정을 늘리는 것은 벽을 옮길 뿐이라, 요청을 붙잡지 않고
    토큰으로 받아 가게 바꿨다.
"""
from pathlib import Path

from app.routers import keyword_lab

BASE = Path(__file__).resolve().parents[2]


class TestRunEndpoints:
    def test_result_route_exists(self):
        paths = {r.path for r in keyword_lab.router.routes}
        assert "/api/v1/keyword-lab/run/{task_id}" in paths

    def test_run_accepts_background_flag(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        assert "background: bool = Body(False)" in src

    def test_background_runs_with_its_own_session(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        # 요청 세션은 응답과 함께 닫힌다
        assert "db_manager.get_session()" in src
        assert "asyncio.create_task(_run_in_background(" in src

    def test_failure_is_stored_not_lost(self):
        src = (BASE / "app/routers/keyword_lab.py").read_text(encoding="utf-8")
        assert '"status": "failed"' in src

    def test_key_helper(self):
        assert keyword_lab._run_key("abc") == "keyword_run:abc"


class TestClientPolling:
    def _js(self):
        return (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")

    def test_starts_in_background(self):
        assert "background: true" in self._js()

    def test_polls_result(self):
        js = self._js()
        assert "kwPoll(" in js
        assert "/api/v1/keyword-lab/run/${taskId}" in js

    def test_empty_body_has_a_readable_message(self):
        js = self._js()
        # JSON.parse 가 던지는 "Unexpected end of JSON input" 대신
        assert "서버가 빈 응답을 돌려줬습니다" in js

    def test_reads_text_before_parsing(self):
        # r.json() 을 바로 부르면 빈 본문에서 원인 모를 오류가 난다
        js = self._js()
        assert "const text = await r.text();" in js

    def test_transient_poll_failure_keeps_waiting(self):
        assert "continue;   // 일시적 실패는 계속 기다린다" in self._js()

    def test_elapsed_shown(self):
        tpl = (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
            encoding="utf-8")
        assert "kwTest.elapsed" in tpl
