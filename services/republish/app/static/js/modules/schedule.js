/**
 * 스케줄 매트릭스 컴포넌트
 * 24시간 x 7일 스케줄 설정 UI
 */

class ScheduleMatrix {
    constructor(options = {}) {
        this.options = {
            container: null,
            initialSchedule: null,
            onChange: null,
            readOnly: false,
            ...options
        };

        this.days = ['월', '화', '수', '목', '금', '토', '일'];
        this.schedule = this.initializeSchedule();
        this.activeHoursCount = 0;
        this.todayActiveHours = 0;

        this.init();
    }

    // 스케줄 초기화
    initializeSchedule() {
        if (this.options.initialSchedule) {
            return JSON.parse(JSON.stringify(this.options.initialSchedule));
        }

        // 기본값: 평일 9-21시
        return Array(7).fill().map((_, dayIdx) =>
            Array(24).fill().map((_, hour) =>
                dayIdx < 5 && hour >= 9 && hour <= 21
            )
        );
    }

    // 컴포넌트 초기화
    init() {
        if (!this.options.container) {
            throw new Error('Container element is required');
        }

        this.render();
        this.attachEvents();
        this.updateStats();
    }

    // UI 렌더링
    render() {
        const container = typeof this.options.container === 'string'
            ? document.querySelector(this.options.container)
            : this.options.container;

        if (!container) {
            throw new Error('Container not found');
        }

        container.innerHTML = this.getTemplate();
    }

    // HTML 템플릿 생성
    getTemplate() {
        return `
            <div class="schedule-matrix-container">
                <!-- 빠른 설정 버튼 -->
                <div class="quick-buttons flex flex-wrap gap-2 mb-4">
                    <button type="button" class="btn-select-all px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                        전체 선택
                    </button>
                    <button type="button" class="btn-clear-all px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                        전체 해제
                    </button>
                    <button type="button" class="btn-working-hours px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                        평일 9-21시
                    </button>
                    <button type="button" class="btn-weekend px-3 py-1 text-xs bg-purple-100 text-purple-800 rounded-full hover:bg-purple-200">
                        주말만
                    </button>
                </div>

                <!-- 도움말 -->
                <p class="text-xs text-gray-500 mb-3">
                    파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 전체 선택/해제
                </p>

                <!-- 스케줄 테이블 -->
                <div class="schedule-table-container overflow-x-auto">
                    <table class="schedule-table w-full text-xs border-collapse">
                        <thead>
                            <tr>
                                <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                                ${this.days.map((day, dayIdx) => `
                                    <th class="day-header border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                        data-day="${dayIdx}">${day}</th>
                                `).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            ${Array.from({length: 24}, (_, hour) => `
                                <tr>
                                    <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium">
                                        ${String(hour).padStart(2, '0')}시
                                    </td>
                                    ${this.days.map((_, dayIdx) => `
                                        <td class="border border-gray-300 p-0">
                                            <button type="button"
                                                    class="time-btn w-full h-7 border-none cursor-pointer transition-colors duration-150 ${
                                                        this.schedule[dayIdx][hour] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'
                                                    }"
                                                    data-day="${dayIdx}"
                                                    data-hour="${hour}"
                                                    ${this.options.readOnly ? 'disabled' : ''}>
                                            </button>
                                        </td>
                                    `).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>

                <!-- 통계 정보 -->
                <div class="stats mt-4 p-3 bg-blue-50 rounded-lg">
                    <div class="flex items-center justify-between text-sm">
                        <span class="text-blue-800 font-medium">
                            활성 시간: <span class="active-hours-count">${this.activeHoursCount}</span>시간/주
                        </span>
                        <span class="text-blue-600 today-hours" style="display: ${this.todayActiveHours > 0 ? 'block' : 'none'}">
                            오늘: <span class="today-active-hours">${this.todayActiveHours}</span>시간
                        </span>
                    </div>
                </div>
            </div>
        `;
    }

    // 이벤트 연결
    attachEvents() {
        if (this.options.readOnly) return;

        const container = this.getContainer();

        // 시간 버튼 클릭
        container.addEventListener('click', (e) => {
            if (e.target.classList.contains('time-btn')) {
                const dayIdx = parseInt(e.target.dataset.day);
                const hour = parseInt(e.target.dataset.hour);
                this.toggleHour(dayIdx, hour);
            }

            // 요일 헤더 클릭
            if (e.target.classList.contains('day-header')) {
                const dayIdx = parseInt(e.target.dataset.day);
                this.toggleDay(dayIdx);
            }

            // 빠른 설정 버튼들
            if (e.target.classList.contains('btn-select-all')) {
                this.selectAll();
            } else if (e.target.classList.contains('btn-clear-all')) {
                this.clearAll();
            } else if (e.target.classList.contains('btn-working-hours')) {
                this.selectWorkingHours();
            } else if (e.target.classList.contains('btn-weekend')) {
                this.selectWeekend();
            }
        });
    }

    // 개별 시간 토글
    toggleHour(dayIdx, hour) {
        this.schedule[dayIdx][hour] = !this.schedule[dayIdx][hour];
        this.updateTimeButton(dayIdx, hour);
        this.updateStats();
        this.triggerChange();
    }

    // 요일 전체 토글
    toggleDay(dayIdx) {
        const allActive = this.schedule[dayIdx].every(h => h);
        this.schedule[dayIdx] = this.schedule[dayIdx].map(() => !allActive);
        this.updateDayButtons(dayIdx);
        this.updateStats();
        this.triggerChange();
    }

    // 전체 선택
    selectAll() {
        this.schedule = Array(7).fill().map(() => Array(24).fill(true));
        this.updateAllButtons();
        this.updateStats();
        this.triggerChange();
    }

    // 전체 해제
    clearAll() {
        this.schedule = Array(7).fill().map(() => Array(24).fill(false));
        this.updateAllButtons();
        this.updateStats();
        this.triggerChange();
    }

    // 평일 근무시간 선택 (9-21시)
    selectWorkingHours() {
        this.schedule = Array(7).fill().map((_, dayIdx) =>
            Array(24).fill().map((_, hour) =>
                dayIdx < 5 && hour >= 9 && hour <= 21
            )
        );
        this.updateAllButtons();
        this.updateStats();
        this.triggerChange();
    }

    // 주말만 선택
    selectWeekend() {
        this.schedule = Array(7).fill().map((_, dayIdx) =>
            Array(24).fill().map((_, hour) =>
                dayIdx >= 5 && hour >= 9 && hour <= 21
            )
        );
        this.updateAllButtons();
        this.updateStats();
        this.triggerChange();
    }

    // 버튼 상태 업데이트
    updateTimeButton(dayIdx, hour) {
        const button = this.getContainer().querySelector(`[data-day="${dayIdx}"][data-hour="${hour}"]`);
        if (button) {
            const isActive = this.schedule[dayIdx][hour];
            button.className = `time-btn w-full h-7 border-none cursor-pointer transition-colors duration-150 ${
                isActive ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'
            }`;
        }
    }

    updateDayButtons(dayIdx) {
        for (let hour = 0; hour < 24; hour++) {
            this.updateTimeButton(dayIdx, hour);
        }
    }

    updateAllButtons() {
        for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
            this.updateDayButtons(dayIdx);
        }
    }

    // 통계 업데이트
    updateStats() {
        // 전체 활성 시간 계산
        let count = 0;
        this.schedule.forEach(day => {
            day.forEach(hour => {
                if (hour) count++;
            });
        });
        this.activeHoursCount = count;

        // 오늘 요일 기준 활성 시간 계산
        const todayIdx = (new Date().getDay() + 6) % 7; // 월=0, 일=6
        this.todayActiveHours = this.schedule[todayIdx].filter(h => h).length;

        // UI 업데이트
        const container = this.getContainer();
        const activeHoursSpan = container.querySelector('.active-hours-count');
        const todayHoursSpan = container.querySelector('.today-active-hours');
        const todayHoursContainer = container.querySelector('.today-hours');

        if (activeHoursSpan) {
            activeHoursSpan.textContent = this.activeHoursCount;
        }

        if (todayHoursSpan) {
            todayHoursSpan.textContent = this.todayActiveHours;
        }

        if (todayHoursContainer) {
            todayHoursContainer.style.display = this.todayActiveHours > 0 ? 'block' : 'none';
        }
    }

    // 변경 이벤트 발생
    triggerChange() {
        if (this.options.onChange) {
            this.options.onChange(this.schedule, {
                activeHoursCount: this.activeHoursCount,
                todayActiveHours: this.todayActiveHours
            });
        }

        // 커스텀 이벤트 발생
        const event = new CustomEvent('schedule:change', {
            detail: {
                schedule: this.schedule,
                stats: {
                    activeHoursCount: this.activeHoursCount,
                    todayActiveHours: this.todayActiveHours
                }
            }
        });
        document.dispatchEvent(event);
    }

    // 컨테이너 요소 반환
    getContainer() {
        return typeof this.options.container === 'string'
            ? document.querySelector(this.options.container)
            : this.options.container;
    }

    // 스케줄 데이터 반환
    getSchedule() {
        return JSON.parse(JSON.stringify(this.schedule));
    }

    // 스케줄 설정
    setSchedule(newSchedule) {
        this.schedule = JSON.parse(JSON.stringify(newSchedule));
        this.updateAllButtons();
        this.updateStats();
    }

    // 통계 정보 반환
    getStats() {
        return {
            activeHoursCount: this.activeHoursCount,
            todayActiveHours: this.todayActiveHours,
            avgDailyHours: this.activeHoursCount / 7
        };
    }

    // 읽기 전용 모드 설정
    setReadOnly(readOnly) {
        this.options.readOnly = readOnly;
        const buttons = this.getContainer().querySelectorAll('.time-btn, .btn-select-all, .btn-clear-all, .btn-working-hours, .btn-weekend, .day-header');
        buttons.forEach(button => {
            button.disabled = readOnly;
            if (readOnly) {
                button.style.pointerEvents = 'none';
                button.style.opacity = '0.6';
            } else {
                button.style.pointerEvents = '';
                button.style.opacity = '';
            }
        });
    }

    // 컴포넌트 제거
    destroy() {
        const container = this.getContainer();
        if (container) {
            container.innerHTML = '';
        }
    }
}

// 전역으로 사용할 수 있도록 추가
window.ScheduleMatrix = ScheduleMatrix;