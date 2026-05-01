/** perf_panel.js - 워커 상태 + 활동 로그 패널 헬퍼 */

// compactDashboard 확장: 워커/로그 표시 유틸리티 메서드
const _origDash_perf = compactDashboard;
compactDashboard = function () {
    const app = _origDash_perf();

    /* ── 워커 상태 ── */

    /** 워커 상태 도트 색상 클래스 반환 */
    app.getWorkerDotClass = function (key) {
        var w = this.workers?.[key];
        if (!w || w.status === 'unknown') return 'bg-gray-400';
        if (w.status === 'offline') return 'bg-red-400';
        if (w.active_tasks > 0) return 'bg-blue-400 animate-pulse';
        return 'bg-green-400';
    };

    /** 워커 상태 텍스트 반환 */
    app.getWorkerStatusText = function (key) {
        var w = this.workers?.[key];
        if (!w || w.status === 'unknown') return '확인중';
        if (w.status === 'offline') return 'Offline';
        return w.active_tasks > 0
            ? '작업중(' + w.active_tasks + ')'
            : 'Online';
    };

    /** 워커 상태 텍스트 색상 클래스 반환 */
    app.getWorkerTextClass = function (key) {
        var w = this.workers?.[key];
        if (!w || w.status === 'unknown') return 'text-gray-500';
        if (w.status === 'offline') return 'text-red-600';
        if (w.active_tasks > 0) return 'text-blue-600';
        return 'text-green-600';
    };

    /** 워커 표시 이름 반환 */
    app.getWorkerLabel = function (key) {
        var labels = {
            generation: '생성',
            publish: '발행',
            utility: '유틸',
        };
        return labels[key] || key;
    };

    /* ── 활동 로그 ── */

    /** 로그 메시지에서 플랫폼 뱃지 문자 추출 ([워], [구] 등) */
    app.getLogBadge = function (msg) {
        var m = msg?.match(/^\[(.)\]/);
        return m ? m[1] : null;
    };

    /** 플랫폼 뱃지 배경 클래스 반환 */
    app.getLogBadgeClass = function (badge) {
        if (badge === '워') return 'bg-blue-500';
        if (badge === '구') return 'bg-orange-500';
        if (badge === '네') return 'bg-green-500';
        if (badge === '티') return 'bg-sky-500';
        return 'bg-gray-500';
    };

    /** 로그 메시지에서 뱃지 접두사 제거 */
    app.getLogText = function (msg) {
        return msg?.replace(/^\[.\]\s*/, '').trim() || msg || '';
    };

    /** 타임스탬프를 HH:MM 형식으로 변환 */
    app.formatLogTime = function (ts) {
        if (!ts) return '';
        var d = new Date(ts);
        return String(d.getHours()).padStart(2, '0') +
               ':' +
               String(d.getMinutes()).padStart(2, '0');
    };

    /** 로그 레벨 뱃지 클래스 반환 */
    app.getLevelClass = function (level) {
        if (level === 'SUCCESS') return 'bg-green-100 text-green-700';
        if (level === 'ERROR') return 'bg-red-100 text-red-700';
        if (level === 'WARN') return 'bg-yellow-100 text-yellow-700';
        return 'bg-gray-100 text-gray-600';
    };

    /** 로그 레벨 표시 텍스트 반환 */
    app.getLevelText = function (level) {
        var map = {
            SUCCESS: '성공',
            ERROR: '오류',
            WARN: '경고',
            INFO: '정보',
        };
        return map[level] || level || '';
    };

    /** 로그 항목 존재 여부 확인 */
    app.hasLogs = function () {
        return this.logs && this.logs.length > 0;
    };

    /** 표시할 로그 목록 반환 (최대 8개) */
    app.visibleLogs = function () {
        return (this.logs || []).slice(0, 8);
    };

    return app;
};
