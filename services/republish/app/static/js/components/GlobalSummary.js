/**
 * GlobalSummary - 글로벌 요약탭 컴포넌트
 *
 * Features:
 * - 22개 요약탭 (블로그, 카테고리, 모듈, 플로우, 이번주, 오늘)
 * - 고정 요약탭 선택 기능 (localStorage 저장)
 * - 카운팅 실시간 연결
 * - 대시보드 요약 패널 슬라이드
 */
function globalSummary() {
    return {
        panelOpen: false,
        settingsSheetOpen: false,  // 설정 하단 시트 상태
        stats: {},
        activities: [],
        pinnedTabKeys: [],

        // 22개 전체 탭 정의
        allTabs: [
            // 블로그 (5개)
            { key: 'total_blogs', label: '전체 블로그', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'wordpress', label: '워드프레스', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'blogger', label: '구글 블로거', group: 'blog', bgClass: 'bg-blue-50', textClass: 'text-blue-600' },
            { key: 'active_blogs', label: '활성 블로그', group: 'blog', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'inactive_blogs', label: '비활성 블로그', group: 'blog', bgClass: 'bg-gray-100', textClass: 'text-gray-600' },
            // 카테고리 (3개)
            { key: 'topics', label: '주제', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'subtopics', label: '하위주제', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            { key: 'keywords', label: '키워드', group: 'category', bgClass: 'bg-green-50', textClass: 'text-green-600' },
            // 모듈 (5개)
            { key: 'total_modules', label: '전체 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'prompt_modules', label: '프롬프트 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'generate_modules', label: '생성 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'publish_modules', label: '발행 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            { key: 'republish_modules', label: '재발행 모듈', group: 'module', bgClass: 'bg-purple-50', textClass: 'text-purple-600' },
            // 플로우 (3개)
            { key: 'total_flows', label: '전체 플로우', group: 'flow', bgClass: 'bg-cyan-50', textClass: 'text-cyan-600' },
            { key: 'active_flows', label: '활성 플로우', group: 'flow', bgClass: 'bg-cyan-50', textClass: 'text-cyan-600' },
            { key: 'inactive_flows', label: '비활성 플로우', group: 'flow', bgClass: 'bg-gray-100', textClass: 'text-gray-600' },
            // 이번 주 (3개)
            { key: 'week_generate', label: '이번 주 생성', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            { key: 'week_publish', label: '이번 주 발행', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            { key: 'week_republish', label: '이번 주 재발행', group: 'week', bgClass: 'bg-orange-50', textClass: 'text-orange-600' },
            // 오늘 (3개)
            { key: 'today_generate', label: '오늘 생성', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
            { key: 'today_publish', label: '오늘 발행', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
            { key: 'today_republish', label: '오늘 재발행', group: 'today', bgClass: 'bg-red-50', textClass: 'text-red-600' },
        ],

        // 선택된 탭 객체 배열 (computed)
        get pinnedTabs() {
            return this.pinnedTabKeys
                .map(key => this.allTabs.find(t => t.key === key))
                .filter(Boolean);
        },

        async init() {
            // localStorage에서 고정 탭 설정 로드
            this.loadPinnedTabs();
            // 통계 데이터 로드
            await this.loadStats();
        },

        loadPinnedTabs() {
            try {
                const saved = localStorage.getItem('dashboard_pinned_tabs');
                if (saved) {
                    this.pinnedTabKeys = JSON.parse(saved);
                } else {
                    // 기본값: 활성 플로우, 활성 블로그, 오늘 생성, 오늘 발행
                    this.pinnedTabKeys = ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
                }
            } catch (e) {
                this.pinnedTabKeys = ['active_flows', 'active_blogs', 'today_generate', 'today_publish'];
            }
        },

        savePinnedTabs() {
            localStorage.setItem('dashboard_pinned_tabs', JSON.stringify(this.pinnedTabKeys));
        },

        isTabPinned(key) {
            return this.pinnedTabKeys.includes(key);
        },

        togglePinTab(key) {
            if (this.isTabPinned(key)) {
                this.pinnedTabKeys = this.pinnedTabKeys.filter(k => k !== key);
            } else {
                this.pinnedTabKeys.push(key);
            }
        },

        async loadStats() {
            try {
                const res = await fetch(`${API_BASE}/dashboard/stats`, { credentials: 'include' });
                if (res.ok) {
                    this.stats = await res.json();
                }
            } catch (error) {
                console.error('통계 로드 실패:', error);
            }
        },

        togglePanel() {
            this.panelOpen = !this.panelOpen;
            if (this.panelOpen) {
                this.loadActivities();
            }
        },

        openSettingsSheet() {
            // 고정 탭 설정 하단 시트 열기
            this.settingsSheetOpen = true;
            // body 스크롤 고정
            document.body.classList.add('sheet-open');
        },

        closeSettingsSheet() {
            // 닫을 때 고정 탭 저장
            this.savePinnedTabs();
            this.settingsSheetOpen = false;
            // body 스크롤 복원
            document.body.classList.remove('sheet-open');
        },

        openSettingsModal() {
            // 사용자/AI/API 설정 모달 열기 (settings.js의 전역 함수 호출)
            if (typeof window.openSettingsModal === 'function') {
                window.openSettingsModal();
            }
        },

        closePanel() {
            // 닫을 때 고정 탭 저장
            this.savePinnedTabs();
            this.panelOpen = false;
        },

        async loadActivities() {
            try {
                const res = await fetch(`${API_BASE}/dashboard/activities?limit=5`, { credentials: 'include' });
                if (res.ok) {
                    const data = await res.json();
                    this.activities = data.activities || [];
                }
            } catch (error) {
                console.error('활동 로드 실패:', error);
            }
        },

        formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;

            if (diff < 3600000) {
                const mins = Math.floor(diff / 60000);
                return mins <= 0 ? '방금' : `${mins}분 전`;
            }
            if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                return `${hours}시간 전`;
            }
            const days = Math.floor(diff / 86400000);
            return `${days}일 전`;
        }
    };
}
