/**
 * 미매칭 발행글 정리 — 정식제목 탭의 곁딸린 화면.
 *
 * 블로그에 발행됐지만 정식제목과 짝이 없는 글을 추려 정식제목으로
 * 올리거나, 임시제목으로 내리거나, 아주 지운다.
 *
 * **왜 따로 뒀나**: 한 번에 200건만 받아 와 그보다 많으면 나머지를
 * 볼 길이 없었다. 이어 받기·전체 고르기·검색이 붙으면서 덩치가 커져
 * 화면 파일에서 떼어냈다.
 *
 * 붙이는 법: dataManagementApp() 의 return 안에 `...unmatchedCleanupPart(),`
 */
function unmatchedCleanupPart() {
    const PAGE_SIZE = 100;
    const MAX_PAGES = 50;          // 5,000건. 그 이상은 검색으로 좁힌다

    return {
        // ── 정리 창 ──────────────────────────────────────────
        showUnmatchedDialog: false,
        unmatchedTitlesItems: [],
        unmatchedTitlesTotal: 0,
        unmatchedSelectedIds: [],
        unmatchedPage: 1,
        unmatchedHasNext: false,
        unmatchedLoading: false,
        unmatchedSearch: '',

        async openUnmatchedTitlesDialog() {
            if (!this.selectedBlogId) {
                alert('블로그를 먼저 선택하세요.');
                return;
            }
            this.unmatchedSelectedIds = [];
            this.unmatchedSearch = '';
            this.showUnmatchedDialog = true;
            await this.reloadUnmatched();
        },

        /** 첫 쪽부터 다시. 검색어를 바꿀 때도 여기로 온다. */
        async reloadUnmatched() {
            this.unmatchedPage = 1;
            this.unmatchedTitlesItems = [];
            this.unmatchedHasNext = false;
            await this.fetchUnmatchedPage();
        },

        /** 지금 쪽을 받아 목록 뒤에 잇는다. */
        async fetchUnmatchedPage() {
            if (this.unmatchedLoading || !this.selectedBlogId) return;
            this.unmatchedLoading = true;
            try {
                const qs = new URLSearchParams({
                    match_status: 'unmatched',
                    page: String(this.unmatchedPage),
                    size: String(PAGE_SIZE),
                });
                if (this.unmatchedSearch.trim()) {
                    qs.append('search', this.unmatchedSearch.trim());
                }
                const res = await fetch(
                    `${API_BASE}/blogs/${this.selectedBlogId}/crawled-posts?${qs}`,
                    { credentials: 'include' });
                if (!res.ok) throw new Error('목록 조회 실패');
                const data = await res.json();
                const rows = data.items || [];
                // 이어 받기라 이미 있는 것은 빼고 붙인다
                const seen = new Set(this.unmatchedTitlesItems.map(r => r.id));
                this.unmatchedTitlesItems = [
                    ...this.unmatchedTitlesItems,
                    ...rows.filter(r => !seen.has(r.id)),
                ];
                this.unmatchedTitlesTotal = data.total || 0;
                this.unmatchedHasNext = !!data.has_next;
            } catch (e) {
                alert('미매칭 발행글 목록을 불러오지 못했습니다: ' + e.message);
            } finally {
                this.unmatchedLoading = false;
            }
        },

        /** 다음 쪽을 잇는다. */
        async loadMoreUnmatched() {
            if (!this.unmatchedHasNext || this.unmatchedLoading) return;
            this.unmatchedPage += 1;
            await this.fetchUnmatchedPage();
        },

        /** 남은 것을 끝까지 받아 온다. 전체 고르기 전에 쓴다. */
        async loadAllUnmatched() {
            let guard = 0;
            while (this.unmatchedHasNext && guard < MAX_PAGES) {
                await this.loadMoreUnmatched();
                guard += 1;
            }
        },

        /** 목록 바닥에 닿으면 다음 쪽을 알아서 잇는다. */
        onUnmatchedScroll(el) {
            if (!el || this.unmatchedLoading || !this.unmatchedHasNext) return;
            const left = el.scrollHeight - el.scrollTop - el.clientHeight;
            if (left < 120) this.loadMoreUnmatched();
        },

        // ── 전체 고르기 ──────────────────────────────────────
        /** 지금 목록이 모두 골라져 있는가.
         *
         *  **get 접근자로 두면 안 된다.** 이 묶음은 화면 쪽에서 `...` 로
         *  펼쳐 합치는데, 그때 접근자가 한 번 불려 값으로 굳는다. 그러면
         *  표시가 영영 바뀌지 않는다.
         */
        unmatchedAllChecked() {
            const rows = this.unmatchedTitlesItems || [];
            return rows.length > 0
                && rows.every(r => this.unmatchedSelectedIds.includes(r.id));
        },

        /** 받아 온 것을 모두 고르거나 모두 푼다.
         *
         *  아직 안 받은 쪽이 남아 있으면 먼저 끝까지 받는다 — 화면에
         *  없는 것이 조용히 빠지면 "전체"라는 말이 거짓이 된다.
         */
        async toggleAllUnmatched() {
            if (this.unmatchedAllChecked()) {
                this.unmatchedSelectedIds = [];
                return;
            }
            if (this.unmatchedHasNext) await this.loadAllUnmatched();
            this.unmatchedSelectedIds =
                (this.unmatchedTitlesItems || []).map(r => r.id);
        },

        // ── 정리 ─────────────────────────────────────────────
        /** 고른 발행글을 한 길로 보낸다.
         *
         * @param {string} action - 'promote-to-main' | 'promote-to-temp' | 'delete'
         * @param {number[]} ids - 대상. 비우면 정리 창에서 고른 것
         */
        async cleanupUnmatched(action, ids = null) {
            const target = (ids && ids.length)
                ? ids.map(n => parseInt(n, 10)).filter(Number.isInteger)
                : [...this.unmatchedSelectedIds];
            if (!target.length) return;

            const words = {
                'promote-to-main': ['정식제목으로 등록하고 곧바로 매칭 완료 처리합니다',
                                    '정식제목 등록'],
                'promote-to-temp': ['임시제목으로 등록합니다', '임시제목 등록'],
                'delete': ['영구 삭제합니다. 되돌릴 수 없습니다', '삭제'],
            }[action];
            if (!words) return;
            if (!confirm(`발행글 ${target.length}개를 ${words[0]}. 진행할까요?`)) {
                return;
            }

            try {
                const res = await fetch(
                    `${API_BASE}/blogs/${this.selectedBlogId}`
                    + `/unmatched-posts/${action}`,
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ post_ids: target }),
                    });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || `${words[1]} 실패`);
                alert(data.message
                    || `${data.promoted ?? data.created ?? data.deleted ?? target.length}개 ${words[1]} 완료`);

                // 처리한 것은 목록에서 걷어낸다
                const done = new Set(target);
                this.unmatchedTitlesItems =
                    (this.unmatchedTitlesItems || []).filter(r => !done.has(r.id));
                this.unmatchedSelectedIds =
                    this.unmatchedSelectedIds.filter(id => !done.has(id));
                this.selectedUnmatchedCrawled =
                    (this.selectedUnmatchedCrawled || [])
                        .filter(id => !done.has(parseInt(id, 10)));
                this.unmatchedTitlesTotal =
                    Math.max(0, this.unmatchedTitlesTotal - target.length);

                await this.refreshAfterCleanup();
            } catch (e) {
                alert(`${words[1]} 실패: ` + e.message);
            }
        },

        /** 정리 뒤 목록 되살리기. 어느 화면에서 불렀든 맞춰 준다. */
        async refreshAfterCleanup() {
            if (typeof this.loadMainTitlesWithCrawled === 'function'
                && this.selectedBlogId) {
                await this.loadMainTitlesWithCrawled();
            }
            if (typeof this.loadStats === 'function') this.loadStats();
        },

        // 정리 창에서 부르는 이름들 (예전 이름 유지)
        bulkPromoteUnmatchedToMain() {
            return this.cleanupUnmatched('promote-to-main');
        },
        bulkDemoteUnmatchedToTemp() {
            return this.cleanupUnmatched('promote-to-temp');
        },
        bulkDeleteUnmatchedTitles() {
            return this.cleanupUnmatched('delete');
        },

        // 목록에서 고른 미매칭 행을 바로 정리할 때
        cleanupSelectedUnmatched(action) {
            const ids = (this.selectedUnmatchedCrawled || [])
                .map(n => parseInt(n, 10)).filter(Number.isInteger);
            return this.cleanupUnmatched(action, ids);
        },
    };
}
