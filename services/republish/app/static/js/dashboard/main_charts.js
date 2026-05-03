/** main_charts.js - 시계열 트렌드 + 시간대별 차트 렌더링 */

// compactDashboard 확장: ApexCharts 기반 트렌드/시간대 차트
const _origDash_charts = compactDashboard;
compactDashboard = function () {
    const app = _origDash_charts();

    // 차트 인스턴스 보관
    app._trendChart = null;
    app._hourlyChart = null;

    /**
     * 7일 트렌드 영역 차트 렌더링
     * - 생성(초록) / 발행(파랑) 이중 시리즈
     */
    app.renderTrendChart = function () {
        const el = document.getElementById('trend-chart');
        if (!el || !this.trends.dates?.length) return;
        if (this._trendChart) this._trendChart.destroy();

        this._trendChart = new ApexCharts(el, {
            chart: {
                type: 'area',
                height: 220,
                toolbar: { show: false },
                fontFamily: 'Sora, sans-serif',
            },
            series: [
                { name: '생성', data: this.trends.generated || [] },
                { name: '발행', data: this.trends.published || [] },
                { name: '재발행', data: this.trends.republished || [] },
            ],
            xaxis: {
                categories: this.trends.dates || [],
                labels: {
                    style: { fontSize: '10px', colors: '#9ca3af' },
                    formatter: function (v) { return v ? v.slice(5) : ''; },
                },
            },
            yaxis: {
                labels: { style: { fontSize: '10px', colors: '#9ca3af' } },
            },
            colors: ['#0F6E56', '#0C447C', '#6366f1'],
            stroke: { width: 2, curve: 'smooth' },
            fill: {
                type: 'gradient',
                gradient: { opacityFrom: 0.15, opacityTo: 0.02 },
            },
            grid: { borderColor: '#f3f4f6', strokeDashArray: 3 },
            legend: {
                position: 'top',
                horizontalAlign: 'left',
                fontSize: '11px',
                fontWeight: 500,
                markers: { width: 8, height: 8, radius: 2 },
            },
            tooltip: { style: { fontSize: '11px' } },
            dataLabels: { enabled: false },
        });
        this._trendChart.render();
    };

    /**
     * 24시간 시간대별 막대 차트 렌더링
     */
    app.renderHourlyChart = function () {
        const el = document.getElementById('hourly-chart');
        if (!el || !this.hourly.counts?.length) return;
        if (this._hourlyChart) this._hourlyChart.destroy();

        var hourLabels = (this.hourly.hours || []).map(function (h) {
            return h + '시';
        });

        this._hourlyChart = new ApexCharts(el, {
            chart: {
                type: 'bar',
                height: 280,
                toolbar: { show: false },
                fontFamily: 'Sora, sans-serif',
            },
            series: [{ name: '생성', data: this.hourly.counts || [] }],
            xaxis: {
                categories: hourLabels,
                labels: {
                    style: { fontSize: '9px', colors: '#9ca3af' },
                    rotate: -45,
                    rotateAlways: true,
                },
            },
            yaxis: {
                labels: { style: { fontSize: '10px', colors: '#9ca3af' } },
            },
            colors: ['#0C447C'],
            plotOptions: {
                bar: { borderRadius: 3, columnWidth: '60%' },
            },
            grid: { borderColor: '#f3f4f6', strokeDashArray: 3 },
            dataLabels: { enabled: false },
            tooltip: { style: { fontSize: '11px' } },
        });
        this._hourlyChart.render();
    };

    // 기존 init 래핑: 데이터 로드 후 차트 렌더링 + 정리
    var _origAppInit = app.init;
    app.init = async function () {
        await _origAppInit.call(this);

        // DOM 갱신 후 차트 렌더링
        this.$nextTick(function () {
            this.renderTrendChart();
            this.renderHourlyChart();
        }.bind(this));

        window.addEventListener('beforeunload', function () {
            if (this._trendChart) this._trendChart.destroy();
            if (this._hourlyChart) this._hourlyChart.destroy();
        }.bind(this));
    };

    return app;
};
