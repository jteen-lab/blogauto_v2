/**
 * 애드센스 필수구성 모듈 — 필수페이지(개인정보/약관/소개/문의) 섹션 템플릿.
 *
 * getContactFormModuleFormTemplate()가 문의폼 섹션 뒤에 이어붙인다.
 * 문체 프리셋 선택 + 페이지별 본문 직접 편집(override). 편집 안 한 페이지는
 * 프리셋 기본을 따르며, 프리셋을 바꾸면 자동 반영된다.
 */
window.getContactFormPagesSection = function () {
    return `
    <div x-show="formData.type_code === 'contact_form'" class="space-y-4 border-t border-gray-200 pt-4">
        <div class="p-3 bg-indigo-50/60 border border-indigo-200 rounded-lg">
            <label class="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" x-model="formData.generate_pages"
                       class="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500">
                <span class="text-sm font-semibold text-gray-900">📋 필수 페이지 4종 함께 생성</span>
            </label>
            <p class="text-xs text-gray-500 mt-1 ml-6">
                개인정보처리방침·이용약관·소개·문의 페이지를 <strong>플로우에 연결된 블로그</strong>마다
                자동 생성/갱신합니다(멱등). 문의폼 URL이 있으면 각 페이지의 문의 영역에 폼이 삽입됩니다.
            </p>
        </div>

        <div x-show="formData.generate_pages" class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">페이지 문체 프리셋</label>
                <!-- select+x-for는 옵션 비동기 로드 시 선택값이 첫 항목으로 보인다 → 버튼 목록으로 처리 -->
                <div class="space-y-1.5">
                    <template x-for="p in requiredPagePresets" :key="p.code">
                        <button type="button"
                                @click="formData.pages_preset_code = p.code; onPagesPresetChange()"
                                :class="formData.pages_preset_code === p.code
                                    ? 'ring-2 ring-indigo-500 border-indigo-400 bg-indigo-50/50'
                                    : 'border-gray-200 hover:border-gray-300 bg-white'"
                                class="w-full flex items-start gap-2 px-3 py-2 border rounded-lg text-left transition-all focus:outline-none">
                            <span class="mt-0.5 w-4 h-4 shrink-0 rounded-full border flex items-center justify-center text-[10px]"
                                  :class="formData.pages_preset_code === p.code
                                      ? 'bg-indigo-500 border-indigo-500 text-white'
                                      : 'border-gray-300 text-transparent'">✓</span>
                            <span class="min-w-0">
                                <span class="block text-sm font-medium text-gray-800" x-text="p.name"></span>
                                <span class="block text-xs text-gray-500" x-text="p.description"></span>
                            </span>
                        </button>
                    </template>
                    <template x-if="requiredPagePresets.length === 0">
                        <div class="text-xs text-gray-400 py-3 text-center border border-dashed border-gray-200 rounded-lg">
                            프리셋 목록을 불러오는 중… (표준 문체 적용)
                        </div>
                    </template>
                </div>
                <p class="mt-1 text-xs text-gray-500">프리셋을 고른 뒤 필요한 페이지만 아래에서 직접 수정할 수 있습니다.</p>
            </div>

            <!-- 페이지별 편집(접이식) -->
            <template x-for="pt in ['privacy','terms','about','contact']" :key="pt">
                <div class="border border-gray-200 rounded-lg overflow-hidden" x-data="{ open: false }">
                    <button type="button" @click="open = !open"
                            class="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 text-left">
                        <span class="text-sm font-medium text-gray-800">
                            <span x-text="pageTypeLabel(pt)"></span>
                            <span x-show="isPageEdited(pt)"
                                  class="ml-2 px-1.5 py-0.5 text-[10px] bg-amber-100 text-amber-700 rounded-full">직접 편집됨</span>
                        </span>
                        <svg class="w-4 h-4 text-gray-400 transition-transform" :class="open ? 'rotate-180' : ''"
                             fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                        </svg>
                    </button>
                    <div x-show="open" x-collapse class="p-3 space-y-2">
                        <textarea x-model="formData.pages_body[pt]" rows="10"
                                  class="w-full px-3 py-2 text-xs font-mono border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                  spellcheck="false"></textarea>
                        <div class="flex items-center justify-between">
                            <p class="text-[11px] text-gray-400">
                                토큰: {{blog_name}} {{blog_url}} {{operator}} {{today}} {{author_block}} {{contact}}
                                <br>{{contact}}는 문의 페이지에선 폼을 바로 보여주고, 다른 페이지에선 바로가기 링크만 넣습니다.
                                <br>"{{blog_name}}은(는)"처럼 쓰면 이름 받침에 맞춰 조사가 자동으로 정리됩니다.
                            </p>
                            <button type="button" @click="resetPageBody(pt)"
                                    x-show="isPageEdited(pt)"
                                    class="text-[11px] text-indigo-600 hover:text-indigo-800 underline">프리셋 기본값으로 되돌리기</button>
                        </div>
                    </div>
                </div>
            </template>
        </div>
    </div>
    `;
};
