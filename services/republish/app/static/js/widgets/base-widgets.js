/**
 * 기본 위젯 모음
 *
 * 가장 기본적인 입력 요소들을 위젯으로 제공합니다.
 * - text-input: 텍스트 입력
 * - number-input: 숫자 입력
 * - select: 드롭다운 선택
 * - checkbox: 체크박스
 * - radio-card: 카드형 라디오 버튼
 */

(function() {
    const baseClass = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent';

    /**
     * 텍스트 입력 위젯
     */
    WidgetRegistry.register('text-input', {
        render(key, schema, value, onChange) {
            return `
                <input type="text"
                       x-model="paramValues['${key}']"
                       placeholder="${schema.placeholder || schema.default || ''}"
                       class="${baseClass}">
            `;
        }
    });

    /**
     * 숫자 입력 위젯 (기본 - 포커스 유실 방지)
     * x-model.lazy로 blur 시에만 업데이트하여 포커스 유지
     */
    WidgetRegistry.register('number-input', {
        render(key, schema, value, onChange) {
            const min = schema.minimum !== undefined ? schema.minimum : '';
            const max = schema.maximum !== undefined ? schema.maximum : '';
            const step = schema.step || 1;
            const rangeText = schema.minimum !== undefined || schema.maximum !== undefined
                ? `<span class="text-xs text-gray-400 ml-2">(${min}~${max})</span>`
                : '';

            return `
                <div class="flex items-center gap-2">
                    <input type="number"
                           x-model.number.lazy="paramValues['${key}']"
                           ${min !== '' ? `min="${min}"` : ''}
                           ${max !== '' ? `max="${max}"` : ''}
                           step="${step}"
                           placeholder="${schema.default || ''}"
                           class="${baseClass} flex-1">
                    ${rangeText}
                </div>
            `;
        }
    });

    /**
     * 스핀박스 위젯 (화살표 버튼 포함)
     * 숫자 입력 + 증감 버튼으로 구성
     * 포커스 유실 방지를 위해 로컬 상태 관리
     */
    WidgetRegistry.register('spinbox', {
        render(key, schema, value, onChange) {
            const min = schema.minimum !== undefined ? schema.minimum : 0;
            const max = schema.maximum !== undefined ? schema.maximum : 9999;
            const step = schema.step || 1;
            const uniqueId = 'spinbox_' + key;

            return `
                <div class="spinbox-widget" x-data="spinboxComponent('${key}', ${min}, ${max}, ${step})">
                    <div class="spinbox-container">
                        <button type="button"
                                @click="decrement"
                                :disabled="localValue <= ${min}"
                                class="spinbox-btn spinbox-btn-left">
                            <span>−</span>
                        </button>
                        <input type="number"
                               id="${uniqueId}"
                               x-model.number="localValue"
                               @blur="syncToParent"
                               @keyup.enter="syncToParent"
                               min="${min}"
                               max="${max}"
                               step="${step}"
                               class="spinbox-input">
                        <button type="button"
                                @click="increment"
                                :disabled="localValue >= ${max}"
                                class="spinbox-btn spinbox-btn-right">
                            <span>+</span>
                        </button>
                    </div>
                    <div class="spinbox-range">
                        <span class="text-xs text-gray-400">${min} ~ ${max}</span>
                    </div>
                </div>
            `;
        }
    });

    /**
     * 범위 입력 위젯 (시작 ~ 종료)
     * 두 개의 숫자 필드를 나란히 배치
     */
    WidgetRegistry.register('range-input', {
        render(key, schema, value, onChange) {
            const startKey = schema.startKey || key + '_start';
            const endKey = schema.endKey || key + '_end';
            const min = schema.minimum !== undefined ? schema.minimum : 0;
            const max = schema.maximum !== undefined ? schema.maximum : 9999;
            const step = schema.step || 1;

            return `
                <div class="range-input-widget">
                    <div class="range-input-container">
                        <div class="range-input-field">
                            <label class="range-input-label">시작</label>
                            <div class="spinbox-container">
                                <button type="button"
                                        @click="paramValues['${startKey}'] = Math.max(${min}, (paramValues['${startKey}'] || ${min}) - ${step})"
                                        class="spinbox-btn spinbox-btn-left">−</button>
                                <input type="number"
                                       x-model.number.lazy="paramValues['${startKey}']"
                                       min="${min}" max="${max}" step="${step}"
                                       class="spinbox-input">
                                <button type="button"
                                        @click="paramValues['${startKey}'] = Math.min(${max}, (paramValues['${startKey}'] || ${min}) + ${step})"
                                        class="spinbox-btn spinbox-btn-right">+</button>
                            </div>
                        </div>
                        <span class="range-separator">~</span>
                        <div class="range-input-field">
                            <label class="range-input-label">종료</label>
                            <div class="spinbox-container">
                                <button type="button"
                                        @click="paramValues['${endKey}'] = Math.max(${min}, (paramValues['${endKey}'] || ${max}) - ${step})"
                                        class="spinbox-btn spinbox-btn-left">−</button>
                                <input type="number"
                                       x-model.number.lazy="paramValues['${endKey}']"
                                       min="${min}" max="${max}" step="${step}"
                                       class="spinbox-input">
                                <button type="button"
                                        @click="paramValues['${endKey}'] = Math.min(${max}, (paramValues['${endKey}'] || ${max}) + ${step})"
                                        class="spinbox-btn spinbox-btn-right">+</button>
                            </div>
                        </div>
                    </div>
                    <p class="range-input-hint">${schema.hint || '포스트 수 범위를 설정하세요'}</p>
                </div>
            `;
        }
    });

    /**
     * 드롭다운 선택 위젯
     */
    WidgetRegistry.register('select', {
        render(key, schema, value, onChange) {
            const options = (schema.enum || []).map(opt => {
                const label = schema.enumLabels && schema.enumLabels[opt]
                    ? schema.enumLabels[opt]
                    : opt;
                return `<option value="${opt}">${label}</option>`;
            }).join('');

            return `
                <select x-model="paramValues['${key}']" class="${baseClass}">
                    ${options}
                </select>
            `;
        }
    });

    /**
     * 체크박스 위젯
     */
    WidgetRegistry.register('checkbox', {
        render(key, schema, value, onChange) {
            return `
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox"
                           x-model="paramValues['${key}']"
                           class="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500">
                    <span class="ml-3 text-sm text-gray-700">${schema.checkboxLabel || schema.description || ''}</span>
                </label>
            `;
        }
    });

    /**
     * 텍스트 영역 위젯 (여러 줄 입력)
     */
    WidgetRegistry.register('textarea', {
        render(key, schema, value, onChange) {
            const rows = schema.rows || 4;
            return `
                <textarea x-model="paramValues['${key}']"
                          rows="${rows}"
                          placeholder="${schema.placeholder || ''}"
                          class="${baseClass} resize-y"></textarea>
            `;
        }
    });

    /**
     * 비밀번호/API 키 입력 위젯 (마스킹)
     */
    WidgetRegistry.register('password-input', {
        render(key, schema, value, onChange) {
            const uniqueId = 'pwd_' + key + '_' + Math.random().toString(36).substr(2, 9);
            return `
                <div class="relative" x-data="{ show: false }">
                    <input :type="show ? 'text' : 'password'"
                           x-model="paramValues['${key}']"
                           placeholder="${schema.placeholder || '••••••••••••'}"
                           class="${baseClass} pr-10">
                    <button type="button"
                            @click="show = !show"
                            class="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600">
                        <svg x-show="!show" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                        </svg>
                        <svg x-show="show" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/>
                        </svg>
                    </button>
                </div>
            `;
        }
    });

    /**
     * 카드형 라디오 버튼 위젯
     * options: [{ value, label, icon, description }]
     */
    WidgetRegistry.register('radio-card', {
        render(key, schema, value, onChange) {
            const options = schema.options || [];

            if (options.length === 0 && schema.enum) {
                // enum에서 options 생성
                schema.enum.forEach(val => {
                    options.push({
                        value: val,
                        label: schema.enumLabels && schema.enumLabels[val] ? schema.enumLabels[val] : val,
                        icon: null,
                        description: null
                    });
                });
            }

            const cards = options.map(opt => `
                <label class="flex-1 cursor-pointer">
                    <input type="radio"
                           name="widget_${key}"
                           value="${opt.value}"
                           x-model="paramValues['${key}']"
                           class="sr-only peer">
                    <div class="p-4 border-2 rounded-lg text-center transition-all
                                peer-checked:border-blue-500 peer-checked:bg-blue-50
                                hover:border-gray-400 border-gray-200">
                        ${opt.icon ? `<span class="text-2xl block mb-2">${opt.icon}</span>` : ''}
                        <span class="font-medium text-gray-900 block">${opt.label}</span>
                        ${opt.description ? `<span class="text-xs text-gray-500 mt-1 block">${opt.description}</span>` : ''}
                    </div>
                </label>
            `).join('');

            return `<div class="flex gap-3">${cards}</div>`;
        }
    });

    console.log('[BaseWidgets] 기본 위젯 로드 완료:', WidgetRegistry.list());
})();
