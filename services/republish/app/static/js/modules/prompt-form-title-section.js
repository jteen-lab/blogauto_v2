/**
 * 제목 재조합 설정 — 묶음 단위.
 *
 * 프롬프트 템플릿은 제목의 키워드로 갈리는데 제목 설정은 하나뿐이었다.
 * 견적 글과 청소 글은 뼈대가 다른데 제목만 한 틀에서 나왔다.
 *
 * 한 묶음은 넷이다 — 제목 스타일 · 제목 길이 · 스타일별 지시 · 추가 지시.
 * 묶음 1 은 템플릿 1(기본)과, 묶음 2 는 템플릿 2 와 짝이다.
 *
 * 순서도: docs/flowcharts/title_recombine_rotation.md
 */

/** 한 묶음의 칸들. `p` 는 값이 사는 경로(묶음 1 이면 최상위, 2.. 면 x-for 변수). */
function getTitleBundleFields(p, opts) {
    const withTemplatePicker = !!(opts && opts.withTemplatePicker);
    return `
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">제목 스타일 선택</label>
            <div class="grid grid-cols-2 md:grid-cols-5 gap-2">
                <template x-for="style in promptModule.titleStyles" :key="style.value">
                    <label class="flex items-center p-2 border rounded-lg cursor-pointer transition-colors"
                           :class="${p}.selectedStyles.includes(style.value) ? 'bg-blue-50 border-blue-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                        <input type="checkbox" :value="style.value"
                               :checked="${p}.selectedStyles.includes(style.value)"
                               @change="toggleStyleIn(${p}.selectedStyles, style.value)"
                               class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                        <div class="ml-2"><span class="text-sm font-medium" x-text="style.icon + ' ' + style.label"></span></div>
                    </label>
                </template>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 p-2 bg-white border border-gray-200 rounded-lg">
            <label class="text-sm font-medium text-gray-700">제목 길이</label>
            <input type="number" min="0" max="80" x-model.number="${p}.minLength"
                   class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
            <span class="text-sm text-gray-500">~</span>
            <input type="number" min="0" max="80" x-model.number="${p}.maxLength"
                   class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
            <span class="text-sm text-gray-500">자</span>
            <span class="text-xs text-gray-400">
                0이면 제한 없음. <b>AI는 글자수를 세지 못하므로</b> 결과를 직접 재고
                벗어나면 한 번 다시 만듭니다.
            </span>
        </div>
        <div>
            <div class="flex flex-wrap items-center gap-2 mb-2">
                <label class="text-sm font-medium text-gray-700">스타일별 지시 (선택)</label>
                ${withTemplatePicker ? `
                <select x-model="promptModule.styleTemplate"
                        @change="applyStyleTemplate()"
                        class="px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500">
                    <option value="">템플릿 선택…</option>
                    <template x-for="t in promptModule.styleTemplates" :key="t.code">
                        <option :value="t.code" x-text="t.label"></option>
                    </template>
                </select>
                <button type="button" @click="recommendStyleTemplate()"
                        class="px-2 py-1 text-xs text-blue-600 border border-blue-200 rounded hover:bg-blue-50">
                    니치로 추천
                </button>
                <span x-show="promptModule.styleTemplateHint" class="text-xs text-gray-500"
                      x-text="promptModule.styleTemplateHint"></span>` : ''}
            </div>
            <div class="space-y-1.5">
                <template x-for="style in promptModule.titleStyles" :key="style.value">
                    <div x-show="${p}.selectedStyles.includes(style.value)"
                         class="flex items-center gap-2">
                        <span class="w-20 shrink-0 text-xs text-gray-600" x-text="style.icon + ' ' + style.label"></span>
                        <input type="text"
                               x-model="${p}.stylePrompts[style.value]"
                               :placeholder="promptModule.styleDefaults[style.value] || ''"
                               class="flex-1 px-2 py-1 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500">
                    </div>
                </template>
            </div>
            <p class="text-xs text-gray-400 mt-1">
                <b>분위기가 아니라 형태</b>를 적으세요 — "따뜻하게" 대신 "당신으로 부를 것".
                비우면 회색 글씨의 기본값이 쓰입니다.
            </p>
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">추가 지시사항 (선택)</label>
            <textarea x-model="${p}.customPrompt" rows="2"
                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
                      placeholder="예: 한국 시장에 맞는 표현 사용, 이모지 포함하지 않기"></textarea>
            <p class="text-xs text-gray-400 mt-1">
                <b>모든 스타일에 공통</b>으로 붙습니다. 스타일별 내용을 여기 적으면
                모든 스타일이 그것을 지키려 해 결과가 같아집니다.
            </p>
        </div>`;
}

/** 2. 제목 재조합 설정 섹션 */
function getPromptTitleSection() {
    return `
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">🏷️ 제목 재조합 설정</h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox" x-model="promptModule.titleRecombine.enabled" class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>
                                <div x-show="promptModule.titleRecombine.enabled" x-transition class="space-y-3">

                                    <p class="text-xs text-gray-600 leading-relaxed bg-blue-50 border border-blue-200 rounded-lg px-3 py-2"
                                       x-show="promptModule.rotation.enabled" x-transition>
                                        프롬프트 템플릿이 <b>제목의 키워드로 갈립니다.</b>
                                        제목 설정도 <b>묶음</b>으로 갈립니다.
                                        묶음마다 <b>쓸 템플릿을 고르세요</b> — 고르지 않으면
                                        제자리(묶음 2 → 템플릿 2)에 쓰이고, 아무도 맡지 않은
                                        템플릿은 묶음 1 을 씁니다.
                                    </p>

                                    <!-- 묶음 1 (기본) -->
                                    <div class="p-4 bg-gray-50 rounded-lg space-y-4"
                                         :class="promptModule.rotation.enabled ? 'border border-blue-200' : ''">
                                        <b class="block text-xs text-blue-700" x-show="promptModule.rotation.enabled">
                                            묶음 1 (기본)
                                            <span class="font-normal text-gray-500" x-text="bundleAssignText(-1)"></span>
                                        </b>
                                        ${getTitleBundleFields('promptModule.titleRecombine', { withTemplatePicker: true })}
                                    </div>

                                    <!-- 묶음 2.. -->
                                    <div class="space-y-3" x-show="promptModule.rotation.enabled" x-transition>
                                        <template x-for="(b, bi) in promptModule.titleRecombine.variants" :key="'tb' + bi">
                                            <div class="p-4 bg-white border border-blue-200 rounded-lg space-y-4">
                                                <div class="flex items-center justify-between gap-2">
                                                    <b class="text-xs text-blue-700" x-text="'묶음 ' + (bi + 2)"></b>
                                                    <div class="flex items-center gap-2">
                                                        <input type="text" x-model="b.label" placeholder="이름 (선택)"
                                                               class="w-32 px-2 py-1 border border-gray-300 rounded text-xs">
                                                        <button type="button" @click="promptModule.titleRecombine.variants.splice(bi, 1)"
                                                                class="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded">삭제</button>
                                                    </div>
                                                </div>

                                                <!-- 어느 템플릿에 쓸지 고른다. 안 고르면 제자리 -->
                                                <div class="flex flex-wrap items-center gap-1.5 p-2 bg-blue-50 border border-blue-200 rounded">
                                                    <span class="text-xs font-medium text-gray-700">쓸 템플릿</span>
                                                    <template x-for="n in promptTemplateCount()" :key="'bt' + bi + '-' + n">
                                                        <button type="button" @click="toggleBundleTemplate(b, n)"
                                                                class="w-7 h-7 text-xs rounded border transition-colors"
                                                                :class="(b.templates || []).includes(n)
                                                                    ? 'border-blue-500 bg-blue-600 text-white font-semibold'
                                                                    : 'border-gray-300 bg-white text-gray-600 hover:bg-blue-100'"
                                                                x-text="n"></button>
                                                    </template>
                                                    <button type="button" x-show="(b.templates || []).length"
                                                            @click="b.templates = []"
                                                            class="px-2 py-1 text-xs text-gray-500 underline hover:text-gray-800">
                                                        고른 것 지우기
                                                    </button>
                                                    <span class="text-xs w-full"
                                                          :class="bundleTemplates(bi).length ? 'text-gray-600' : 'text-amber-800'"
                                                          x-text="bundleAssignText(bi)"></span>
                                                </div>
                                                ${getTitleBundleFields('b', {})}
                                            </div>
                                        </template>
                                        <button type="button" @click="addTitleBundle()"
                                                class="px-3 py-1.5 text-sm text-blue-700 border border-blue-300 rounded hover:bg-blue-50">
                                            + 묶음 추가
                                        </button>
                                        <p class="text-xs text-gray-500">
                                            지금 프롬프트 템플릿은 <b x-text="promptTemplateCount()"></b>개입니다.
                                            한 템플릿을 여러 묶음이 고르면 <b>위에 있는 묶음</b>이 쓰입니다.
                                        </p>
                                    </div>
                                </div>
                            </div>`;
}


/** 제목 묶음·분량 계산 — 모듈 폼 메서드에 섞어 넣는다. */
const titleBundleMethods = {
    /** 빈 지시는 저장하지 않는다 — 저장해 두면 기본값으로 못 돌아간다. */
    cleanStylePrompts(source) {
        return Object.fromEntries(
            Object.entries(source || {})
                .filter(([, v]) => v && String(v).trim())
                .map(([k, v]) => [k, String(v).trim()]));
    },

    /** 묶음 안의 스타일 체크. 묶음 1 과 2.. 가 같은 동작을 쓴다. */
    toggleStyleIn(list, styleValue) {
        const idx = list.indexOf(styleValue);
        if (idx !== -1) list.splice(idx, 1);
        else list.push(styleValue);
    },

    /** 제목 묶음 하나 더. 템플릿을 고르지 않으면 제자리에 쓰인다. */
    addTitleBundle() {
        this.promptModule.titleRecombine.variants.push({
            label: '', templates: [], selectedStyles: [], minLength: 0,
            maxLength: 0, customPrompt: '', stylePrompts: {}
        });
    },

    /** 이 묶음이 쓸 템플릿을 집거나 놓는다. */
    toggleBundleTemplate(bundle, number) {
        if (!Array.isArray(bundle.templates)) bundle.templates = [];
        const at = bundle.templates.indexOf(number);
        if (at !== -1) bundle.templates.splice(at, 1);
        else bundle.templates.push(number);
        bundle.templates.sort((a, b) => a - b);
    },

    /** 템플릿 N 이 쓸 묶음. 0 이면 묶음 1(기본). 서버 규칙과 같다.
     *  고른 묶음이 먼저고, 없으면 제자리 묶음이 맡는다. 제자리라도
     *  다른 템플릿을 골랐으면 비켜 준다.
     */
    titleBundleFor(number) {
        const rows = this.promptModule.titleRecombine.variants || [];
        for (let i = 0; i < rows.length; i++) {
            if ((rows[i].templates || []).includes(number)) return i + 1;
        }
        if (number < 2 || number - 2 >= rows.length) return 0;
        const row = rows[number - 2];
        return (row.templates || []).length ? 0 : number - 1;
    },

    /** 이 묶음이 실제로 맡는 템플릿 번호들. bi 는 -1 이면 묶음 1(기본). */
    bundleTemplates(bi) {
        const out = [];
        for (let n = 1; n <= this.promptTemplateCount(); n++) {
            if (this.titleBundleFor(n) === bi + 1) out.push(n);
        }
        return out;
    },

    /** 화면에 적을 한 줄 — 이 묶음이 어느 템플릿에 쓰이는지. */
    bundleAssignText(bi) {
        const mine = this.bundleTemplates(bi);
        if (!mine.length) {
            return bi < 0
                ? '· 아무도 맡지 않은 템플릿에 쓰입니다'
                : '⚠️ 맡은 템플릿이 없습니다 — 이 묶음은 쓰이지 않습니다.';
        }
        const how = bi >= 0 && !(this.promptModule.titleRecombine.variants[bi].templates || []).length
            ? ' (제자리)' : '';
        return '템플릿 ' + mine.join('·') + ' 에 쓰입니다' + how;
    },

    /** 프롬프트 템플릿이 몇 개인가 — 묶음이 남는지 알려 주려고 센다. */
    promptTemplateCount() {
        const rot = this.promptModule.rotation || {};
        if (!rot.enabled) return 1;
        return 1 + (rot.variants || []).length;
    },

    /** 구조 약속이 요구하는 글자 수 합계. 섹션 수는 빌더가 정한다. */
    structureTotal() {
        const b = this.promptModule.builderChars || {};
        const n = b.sections || 0;
        if (!n) return 0;   // 패턴을 아직 안 고르면 셀 수 없다
        return (b.intro || 0) + (b.section || 0) * n + (b.outro || 0);
    },

    /** 구조 합계가 모델 목표에 못 미치는가 — 그러면 발행에서 막힌다. */
    structureShortfall() {
        const total = this.structureTotal();
        if (!total) return 0;
        const target = this.targetChars();
        return total < target ? target - total : 0;
    },
};

window.titleBundleMethods = titleBundleMethods;
