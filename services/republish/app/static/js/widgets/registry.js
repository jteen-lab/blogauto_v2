/**
 * 위젯 레지스트리 시스템
 *
 * param_schema의 widget 속성에 따라 적절한 UI 컴포넌트를 렌더링합니다.
 * 노드 시스템의 플러그인 철학을 유지하면서 다양한 입력 폼을 지원합니다.
 */

const WidgetRegistry = {
    // 등록된 위젯 저장소
    widgets: {},

    /**
     * 위젯 등록
     * @param {string} name - 위젯 이름 (예: 'time-picker')
     * @param {object} widget - 위젯 객체 { render, getValue, setValue }
     */
    register(name, widget) {
        this.widgets[name] = widget;
        console.log(`[WidgetRegistry] 위젯 등록: ${name}`);
    },

    /**
     * 위젯 조회
     * @param {string} name - 위젯 이름
     * @returns {object|null} 위젯 객체
     */
    get(name) {
        return this.widgets[name] || null;
    },

    /**
     * 위젯 존재 여부 확인
     * @param {string} name - 위젯 이름
     * @returns {boolean}
     */
    has(name) {
        return !!this.widgets[name];
    },

    /**
     * showIf 조건 평가
     * @param {object} condition - 조건 객체 (예: { "schedule_type": "fixed_time" })
     * @param {object} values - 현재 폼 값들
     * @returns {boolean} 표시 여부
     */
    evaluateShowIf(condition, values) {
        if (!condition) return true;

        // 단순 조건: { "field": "value" }
        if (typeof condition === 'object' && !Array.isArray(condition)) {
            for (const [field, expected] of Object.entries(condition)) {
                const actual = values[field];

                // 배열인 경우 포함 여부 확인
                if (Array.isArray(expected)) {
                    if (!expected.includes(actual)) return false;
                } else {
                    if (actual !== expected) return false;
                }
            }
            return true;
        }

        return true;
    },

    /**
     * 기본값 추출
     * @param {object} propSchema - 속성 스키마
     * @returns {any} 기본값
     */
    getDefaultValue(propSchema) {
        if (propSchema.default !== undefined) {
            return propSchema.default;
        }

        // 타입별 기본값
        switch (propSchema.type) {
            case 'boolean':
                return false;
            case 'integer':
            case 'number':
                return propSchema.minimum || 0;
            case 'string':
                if (propSchema.enum && propSchema.enum.length > 0) {
                    return propSchema.enum[0];
                }
                return '';
            case 'object':
                return {};
            case 'array':
                return [];
            default:
                return null;
        }
    },

    /**
     * 등록된 모든 위젯 목록
     * @returns {string[]}
     */
    list() {
        return Object.keys(this.widgets);
    }
};

// 전역 등록
window.WidgetRegistry = WidgetRegistry;

/**
 * 스핀박스 Alpine.js 컴포넌트
 * 포커스 유실을 방지하기 위해 로컬 상태를 관리합니다.
 *
 * @param {string} key - paramValues 키
 * @param {number} min - 최소값
 * @param {number} max - 최대값
 * @param {number} step - 증감 단위
 */
function spinboxComponent(key, min, max, step) {
    return {
        localValue: 0,
        key: key,
        min: min,
        max: max,
        step: step,

        init() {
            // 부모 컴포넌트의 paramValues에서 초기값 가져오기
            const parentValue = this.getParentValue();
            this.localValue = parentValue !== undefined ? parentValue : min;

            // paramValues 변경 감시 (외부에서 값이 변경될 때 동기화)
            this.$watch('$root.paramValues', (newValues) => {
                if (newValues && newValues[this.key] !== undefined) {
                    const newVal = newValues[this.key];
                    if (newVal !== this.localValue) {
                        this.localValue = newVal;
                    }
                }
            });
        },

        getParentValue() {
            // Alpine.js 컨텍스트에서 paramValues 접근
            if (this.$root && this.$root.paramValues) {
                return this.$root.paramValues[this.key];
            }
            // 편집 모달의 경우 editParams 접근
            if (this.$root && this.$root.editParams) {
                return this.$root.editParams[this.key];
            }
            return undefined;
        },

        increment() {
            const newValue = Math.min(this.max, this.localValue + this.step);
            this.localValue = newValue;
            this.syncToParent();
        },

        decrement() {
            const newValue = Math.max(this.min, this.localValue - this.step);
            this.localValue = newValue;
            this.syncToParent();
        },

        syncToParent() {
            // 값 범위 제한
            if (this.localValue < this.min) this.localValue = this.min;
            if (this.localValue > this.max) this.localValue = this.max;

            // 부모 컴포넌트의 paramValues에 동기화
            if (this.$root && this.$root.paramValues) {
                this.$root.paramValues[this.key] = this.localValue;
            }
            // 편집 모달의 경우 editParams에 동기화
            if (this.$root && this.$root.editParams) {
                this.$root.editParams[this.key] = this.localValue;
            }
        }
    };
}

// 전역 등록
window.spinboxComponent = spinboxComponent;
