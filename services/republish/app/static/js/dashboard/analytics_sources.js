/**
 * analytics_sources.js — 유입 분석 패널의 '유입 경로' 칸.
 *
 * 네이버/구글/직접/기타로 나눈 방문과 방문 많은 페이지(옛 글 포함)를
 * /api/v1/analytics/sources 에서 받아 그린다. analytics_panel.js 뒤에 붙는다.
 * 순서도: docs/flowcharts/analytics_sources.md
 */
const _origDash_sources = compactDashboard;
compactDashboard = function () {
    const app = _origDash_sources();

    app.gaSources = null;   // /analytics/sources 응답

    /** 기존 불러오기(요약·글별) 뒤에 경로 칸도 함께 불러온다. */
    const _origLoad = app.loadAnalytics;
    app.loadAnalytics = async function () {
        await _origLoad.call(this);
        this.gaSources = await this.gaGet(
            `/api/v1/analytics/sources?days=${this.gaDays}&limit=20` +
            (this.gaBlogId ? `&blog_id=${this.gaBlogId}` : ''));
    };

    app.gaChannelLabel = function (key) {
        return {
            sessions: '전체 방문', naver: '네이버', google: '구글',
            direct: '직접', other: '기타',
        }[key] || key;
    };

    return app;
};
