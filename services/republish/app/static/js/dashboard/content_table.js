/** content_table.js - 최근 생성 콘텐츠 테이블 헬퍼 */

// compactDashboard 확장: 콘텐츠 테이블 상태 뱃지 + 날짜 포맷
const _origDash_ct = compactDashboard;
compactDashboard = function () {
    const app = _origDash_ct();

    /** 콘텐츠 상태별 뱃지 객체 반환 { text, class } */
    app.getStatusBadge = function (status) {
        var badges = {
            published: { text: '발행', cls: 'bg-[#0C447C] text-white' },
            ready:     { text: '생성', cls: 'bg-[#0F6E56] text-white' },
            draft:     { text: '생성', cls: 'bg-[#0F6E56] text-white' },
            failed:    { text: '실패', cls: 'bg-[#993C1D] text-white' },
            publishing:{ text: '발행중', cls: 'bg-blue-400 text-white' },
        };
        return badges[status] || { text: status || '대기', cls: 'bg-gray-200 text-gray-600' };
    };

    /** 타임스탬프를 MM.DD 형식으로 변환 */
    app.formatDate = function (ts) {
        if (!ts) return '';
        var d = new Date(ts);
        return String(d.getMonth() + 1).padStart(2, '0') +
               '.' +
               String(d.getDate()).padStart(2, '0');
    };

    /** 타임스탬프를 MM.DD HH:MM 형식으로 변환 */
    app.formatDateTime = function (ts) {
        if (!ts) return '';
        var d = new Date(ts);
        return String(d.getMonth() + 1).padStart(2, '0') +
               '.' + String(d.getDate()).padStart(2, '0') +
               ' ' + String(d.getHours()).padStart(2, '0') +
               ':' + String(d.getMinutes()).padStart(2, '0');
    };

    /** 제목 텍스트 말줄임 처리 */
    app.truncateTitle = function (title, maxLen) {
        var limit = maxLen || 30;
        if (!title) return '';
        return title.length > limit
            ? title.substring(0, limit) + '...'
            : title;
    };

    /** 콘텐츠 항목 존재 여부 확인 */
    app.hasContents = function () {
        return this.contents && this.contents.length > 0;
    };

    return app;
};
