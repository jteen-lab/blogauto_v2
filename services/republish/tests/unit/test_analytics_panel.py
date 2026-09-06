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
