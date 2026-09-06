"""유입 분석은 대시보드에 있어야 한다.

처음에 설정 창에 넣었다. 유입은 매일 보는 숫자지 한 번 설정하고 잊는
값이 아니다. 연결(토큰·속성)도 같은 자리에 둔다 — 연결은 설정 창에,
결과는 대시보드에 두면 처음 쓰는 사람이 둘을 오간다.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DASH = (ROOT / "app/templates/dashboard/dashboard_v2.html").read_text(
    encoding="utf-8")
SETTINGS = (ROOT / "app/templates/settings/modal.html").read_text(
    encoding="utf-8")
PANEL = (ROOT / "app/static/js/dashboard/analytics_panel.js").read_text(
    encoding="utf-8")


class TestPlacement:
    def test_panel_on_dashboard(self):
        assert "유입 분석" in DASH

    def test_not_in_settings(self):
        """두 곳에 있으면 어느 쪽이 진짜인지 알 수 없다."""
        assert "유입 분석" not in SETTINGS
        assert "analytics/properties" not in SETTINGS

    def test_script_loaded(self):
        assert "analytics_panel.js" in DASH

    def test_extends_existing_component(self):
        """대시보드는 컴포넌트 하나를 확장해 쓴다."""
        assert "const _origDash_analytics = compactDashboard;" in PANEL


class TestSelfContained:
    """연결까지 이 패널에서 끝나야 설정 창을 오갈 일이 없다."""

    @pytest.mark.parametrize("api", [
        "/api/v1/analytics/account",      # 토큰 저장
        "/api/v1/analytics/properties",   # 속성 조회·연결
        "/api/v1/analytics/summary",      # 합계
        "/api/v1/analytics/posts",        # 글별 성적
        "/api/v1/analytics/collect",      # 지금 수집
    ])
    def test_uses_api(self, api):
        assert api in PANEL

    def test_property_link_is_per_blog(self):
        """속성은 블로그마다 따로다."""
        assert "linkGaProperty" in PANEL
        assert "blog_id: blog.id" in PANEL


class TestReadability:
    """코드값을 그대로 보여주면 사용자가 못 읽는다."""

    @pytest.mark.parametrize("label", [
        "그대로 둠", "보강", "제목 손질", "새로 씀", "판정 보류",
    ])
    def test_action_labels_in_korean(self, label):
        assert label in PANEL

    def test_no_raw_action_codes_in_table(self):
        """표에는 라벨 함수를 통해서만 찍는다."""
        table = DASH[DASH.index("재발행 때"):DASH.index("</table>",
                                                     DASH.index("재발행 때"))]
        assert "gaActionLabel(row.action)" in table
        assert 'x-text="row.action"' not in table

    def test_missing_delta_is_dash_not_zero(self):
        """비교 대상이 없는데 0% 로 적으면 유지된 것처럼 보인다."""
        block = PANEL[PANEL.index("app.gaDelta ="):
                      PANEL.index("app.gaDeltaClass =")]
        assert "return '-';" in block


class TestLazyLoad:
    def test_loads_only_when_opened(self):
        """대시보드 첫 로딩을 늦추지 않는다."""
        block = PANEL[PANEL.index("app.toggleAnalytics"):
                      PANEL.index("app.loadAnalytics =")]
        assert "if (this.gaExpanded && this.gaConn === null)" in block

    def test_setup_opens_when_unconnected(self):
        """연결이 없으면 뭘 해야 할지 보여야 한다."""
        assert "if (!this.gaConn.connected) this.gaSetupOpen = true;" in PANEL

    def test_empty_state_tells_what_to_do(self):
        assert "'지금 수집'을 눌러 받아오세요" in DASH


class TestControlsSurviveLoading:
    """기간·블로그를 골라도 기본값으로 돌아가던 문제.

    조작 UI 가 `x-if="!gaLoading"` 안에 있었다. 고르는 순간 loadAnalytics 가
    gaLoading 을 켜고, 그 블록이 통째로 파괴됐다 다시 만들어진다. 새로 만든
    select 는 고른 값을 모른다.
    """

    def _panel(self) -> str:
        start = DASH.index('<span class="font-semibold text-gray-800">유입 분석</span>')
        return DASH[start:DASH.index("<!-- 차트 행", start)]

    def test_selects_outside_the_destroyed_block(self):
        panel = self._panel()
        controls_at = panel.index('x-model.number="gaDays"')
        guard_at = panel.index('<template x-if="!gaLoading">')
        assert controls_at < guard_at, "조작 UI 가 로딩 블록 안에 있다"

    def test_blog_select_outside_too(self):
        panel = self._panel()
        assert (panel.index('x-model="gaBlogId"')
                < panel.index('<template x-if="!gaLoading">'))

    def test_setup_box_outside_too(self):
        """토큰을 입력하던 중 상자가 사라지면 안 된다."""
        panel = self._panel()
        assert (panel.index('x-model="gaToken"')
                < panel.index('<template x-if="!gaLoading">'))


class TestScopeIsVisible:
    """표만 보면 어느 블로그의 결과인지 알 수 없었다."""

    def test_blog_column_in_table(self):
        header = DASH[DASH.index(">블로그<"):DASH.index("</thead>",
                                                      DASH.index(">블로그<"))]
        assert ">제목<" in header
        assert 'x-text="row.blog' in DASH

    def test_api_returns_blog_name(self):
        src = (ROOT / "app/routers/analytics.py").read_text(encoding="utf-8")
        assert '"blog": blog_names.get(' in src

    def test_scope_label_shown(self):
        assert "gaScopeLabel()" in DASH
        assert "app.gaScopeLabel = function" in PANEL

    def test_collect_respects_selected_blog(self):
        """전체를 돌면 방금 고른 블로그와 결과가 어긋난다."""
        block = PANEL[PANEL.index("app.collectAnalytics"):
                      PANEL.index("app.gaGet =")]
        assert "blog_id=${this.gaBlogId}" in block

    def test_skip_reason_is_shown(self):
        block = PANEL[PANEL.index("app.collectAnalytics"):
                      PANEL.index("app.gaGet =")]
        assert "수집 안 함" in block


class TestPairingIsUnambiguous:
    """블로그명과 드롭다운이 좌우로 멀어 짝이 헷갈렸다."""

    def test_row_is_boxed(self):
        row = DASH[DASH.index("blogs || [])"):DASH.index("linkGaProperty")]
        assert "border-2" in row
        assert "rounded-lg" in row

    def test_linked_row_is_highlighted(self):
        row = DASH[DASH.index("blogs || [])"):DASH.index("linkGaProperty")]
        assert "b.property_id" in row
        assert "emerald" in row

    def test_whole_row_is_clickable(self):
        """label 로 감싸면 이름을 눌러도 드롭다운이 열린다."""
        row = DASH[DASH.index("blogs || [])"):DASH.index("linkGaProperty")]
        assert "<label" in row
