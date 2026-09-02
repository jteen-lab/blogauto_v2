"""키워드 모듈 개편 회귀 테스트 — 스케줄 승계·섹션 분할·작업 대상·AI 제거.

사용자 지시:
    1. 실행 간격 숫자 입력 → 다른 모듈과 같은 스케줄 UI 승계
    2. 단계 체크박스 나열 → 단계별 섹션 + 섹션 체크로 설정 활성화
    3. 모든 작업은 키워드 DB 기준으로 (모듈이 여러 개여도 안 꼬이게)
    4. 키워드 모듈에서 제목 생성 AI 제거
"""
import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]


def _form():
    return (BASE / "app/static/js/modules/form.js").read_text(encoding="utf-8")


def _tpl():
    return (BASE / "app/static/js/modules/keyword-form-template.js").read_text(
        encoding="utf-8")


def _sched():
    return (BASE / "app/static/js/modules/keyword-schedule-template.js").read_text(
        encoding="utf-8")


class TestScheduleInherited:
    """다른 모듈과 같은 스케줄 방식."""

    def test_mode_choice_exists(self):
        s = _sched()
        assert 'value="fixed_time"' in s and 'value="interval"' in s

    def test_fixed_times_ui(self):
        s = _sched()
        assert "addKeywordTime()" in s and "removeKeywordTime(time)" in s

    def test_active_hours_matrix(self):
        s = _sched()
        # 수집 모듈과 같은 헬퍼를 쓴다 — 동작이 갈라지지 않게
        for helper in ("selectAllHours()", "clearAllHours()",
                       "selectWorkingHours()", "toggleHour(dayIdx, hour-1)",
                       "toggleDay(dayIdx)"):
            assert helper in s, helper

    def test_no_raw_minute_input(self):
        # 분 단위 숫자만 받던 옛 UI 는 없어야 한다
        assert "interval_minutes" not in _tpl()
        assert "interval_minutes" not in _sched()

    def test_helpers_defined(self):
        js = _form()
        assert "addKeywordTime()" in js and "removeKeywordTime(time)" in js

    def test_matrix_initialized_for_keyword(self):
        js = _form()
        assert "['collect', 'data', 'generate', 'keyword'].includes" in js

    def test_serialized_like_other_modules(self):
        js = _form()
        assert "schedule_mode: k.schedule_mode" in js
        assert "fixed_times: k.fixed_times" in js
        assert "interval_hours: k.interval_hours" in js
        assert "data.schedule_matrix = this.schedule;" in js

    def test_template_loaded(self):
        html = (BASE / "app/templates/modules/list.html").read_text(
            encoding="utf-8")
        assert "keyword-schedule-template.js" in html


class TestSchedulerReadsNested:
    """스케줄러가 새 모양을 읽는다."""

    def _src(self):
        return (BASE / "app/scheduler/flow_scheduler.py").read_text(
            encoding="utf-8")

    def test_fixed_time_nested(self):
        src = self._src()
        assert 'if action_type in ("bulk_collect", "keyword", "title_gen"):' in src

    def test_interval_nested(self):
        src = self._src()
        assert '**(module_settings.get("schedule") or {})' in src

    def test_interval_hours_supported(self):
        src = self._src()
        assert "int(hours * 60) if hours else default_interval" in src

    def test_fixed_time_skips_immediate_run(self):
        """고정 시간 모듈이 등록 직후 도는 것을 막는다."""
        src = self._src()
        assert '"keyword", "title_gen",\n                        )' in src


class TestSections:
    """단계별 섹션 + 섹션 체크로 설정 활성화."""

    @pytest.mark.parametrize("step,label", [
        ("step_collect", "① 수집"),
        ("step_measure", "② 측정"),
        ("step_classify", "③ 분류"),
        ("step_rejudge", "④ 재판정"),
    ])
    def test_section_present(self, step, label):
        tpl = _tpl()
        assert f'x-model="formData.keyword.{step}"' in tpl
        assert label in tpl

    def test_settings_open_only_when_checked(self):
        tpl = _tpl()
        assert 'x-show="formData.keyword.step_collect"' in tpl
        assert 'x-show="formData.keyword.step_classify"' in tpl
        assert 'x-show="formData.keyword.step_rejudge"' in tpl

    def test_thresholds_shared_between_measure_and_rejudge(self):
        """재판정만 켜도 기준값을 볼 수 있어야 한다."""
        tpl = _tpl()
        assert ('x-show="formData.keyword.step_measure || '
                'formData.keyword.step_rejudge"') in tpl

    def test_collect_settings_inside_collect_section(self):
        tpl = _tpl()
        collect = tpl[tpl.index("① 수집"):tpl.index("② 측정")]
        for field in ("seeds_text", "modifiers_text", "collect_limit",
                      "seed_limit", "src_google_trending"):
            assert field in collect, field

    def test_measure_settings_inside_measure_section(self):
        tpl = _tpl()
        measure = tpl[tpl.index("② 측정"):tpl.index("③ 분류")]
        for field in ("min_volume", "max_volume", "min_saturation",
                      "pub_window_days", "measure_limit"):
            assert field in measure, field


class TestTitleAiRemoved:
    def test_no_ai_select_in_keyword_form(self):
        tpl = _tpl()
        assert "ai_provider" not in tpl and "ai_model" not in tpl

    def test_not_serialized(self):
        js = _form()
        # keyword 직렬화 블록만 잘라 본다(그 뒤는 title_gen 블록이다)
        start = js.index("} else if (this.formData.type_code === 'keyword')")
        end = js.index("} else if (this.formData.type_code === 'title_gen')")
        assert "ai_provider" not in js[start:end]

    def test_models_loaded_only_for_title_module(self):
        js = _form()
        assert "if (typeCode === 'title_gen') {" in js
        assert "typeCode === 'keyword' || typeCode === 'title_gen'" not in js

    def test_title_module_keeps_ai(self):
        tpl = (BASE / "app/static/js/modules/title-gen-form-template.js").read_text(
            encoding="utf-8")
        assert "formData.title.ai_provider" in tpl


class TestWorkTargetsAreDbBased:
    """모든 단계가 키워드 DB 를 기준으로 대상을 고른다.

    모듈이 여러 개 돌아도 서로 꼬이지 않으려면, 앞 단계가 넘겨준 목록이
    아니라 DB 상태로 대상을 정해야 한다.
    """

    def _pool(self):
        return (BASE / "app/services/keyword_lab/pool_ops.py").read_text(
            encoding="utf-8")

    def test_measure_selects_from_db(self):
        src = self._pool()
        # 검색량이 빈 행 / 아직 안 잰 행을 DB 에서 고른다
        assert "KeywordCandidate.search_volume.is_(None)" in src

    def test_classify_selects_from_db(self):
        src = self._pool()
        assert "KeywordCandidate.topic_id.is_(None)" in src
        assert "KeywordCandidate.classify_tried_at.is_(None)" in src

    def test_rejudge_scans_db(self):
        src = self._pool()
        assert "select(KeywordCandidate).where(KeywordCandidate.user_id == user_id)" in src

    def test_runner_does_not_hand_off_lists(self):
        """수집 결과를 측정에 직접 넘기지 않는다 — DB 를 거친다."""
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        measure_call = src[src.index('if "measure" in steps:'):
                           src.index('if "classify" in steps:')]
        # 수집 결과(out["collect"])를 인자로 넘기지 않는다
        assert 'out["collect"]' not in measure_call
        assert "pool_measure(" in measure_call

    def test_measure_scoped_to_user_not_batch(self):
        src = (BASE / "app/services/keyword_lab/service.py").read_text(
            encoding="utf-8")
        assert "KeywordCandidate.measured_at.is_(None)" in src
