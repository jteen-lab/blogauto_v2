/**
 * 페이지네이션 목록 API 공통 헬퍼(모듈/플로우).
 *
 * `/api/v1/modules`는 페이지네이션 API라 개수를 지정하지 않으면 서버 기본값
 * (20개)만 돌려준다. 예전에 플로우 화면이 개수를 지정하지 않아, 모듈이 20개를
 * 넘긴 뒤로 나머지가 화면에서 조용히 사라졌다(선택된 프롬프트 모듈이 안 보이고
 * 블로그 자동 잠금까지 풀리는 회귀). 고정 size 를 크게 잡는 방식도 언젠가 같은
 * 문제를 반복하므로, 여기서는 has_next 가 false 가 될 때까지 이어받아
 * **모듈 개수와 무관하게 전부** 반환한다.
 */
(function () {
    'use strict';

    var PAGE_SIZE = 100;   // 서버가 허용하는 최대 페이지 크기
    var MAX_PAGES = 200;   // 무한루프 방지(최대 2만 개)

    /**
     * 페이지를 끝까지 이어받아 전체 항목을 반환한다.
     * @param {string} path API 경로 (예: '/api/v1/modules')
     * @param {string} key 응답에서 배열이 담긴 필드명 (예: 'modules')
     * @param {string} label 오류/경고 메시지용 이름
     * @param {Object} [params] 추가 쿼리 파라미터
     * @returns {Promise<Array>} 전체 항목 배열
     */
    async function fetchAllPages(path, key, label, params) {
        var all = [];
        var page = 1;

        while (page <= MAX_PAGES) {
            var query = new URLSearchParams(params || {});
            query.set('page', String(page));
            query.set('size', String(PAGE_SIZE));

            var resp = await fetch(path + '?' + query.toString(), {
                credentials: 'include'
            });
            if (!resp.ok) {
                throw new Error(label + ' 목록 조회 실패 (HTTP ' + resp.status + ')');
            }

            var data = await resp.json();
            var items = data[key] || [];
            all = all.concat(items);

            // 마지막 페이지이거나 더 받을 게 없으면 종료
            if (!data.has_next || items.length === 0) {
                if (typeof data.total === 'number' && all.length < data.total) {
                    console.warn(
                        '[list-api] ' + label + ' 일부만 조회됨:',
                        all.length, '/', data.total
                    );
                }
                return all;
            }
            page += 1;
        }

        console.warn(
            '[list-api] ' + label + ' 페이지 상한 도달 — 조회 중단:', all.length, '개'
        );
        return all;
    }

    /**
     * 모든 모듈을 조회한다.
     * @param {Object} [params] 추가 쿼리 파라미터 (예: {module_type_code: 'prompt'})
     */
    window.fetchAllModules = function (params) {
        return fetchAllPages('/api/v1/modules', 'modules', '모듈', params);
    };

    /**
     * 모든 플로우를 조회한다.
     * @param {Object} [params] 추가 쿼리 파라미터 (예: {status: 'active'})
     */
    window.fetchAllFlows = function (params) {
        return fetchAllPages('/api/v1/flows', 'flows', '플로우', params);
    };
})();
