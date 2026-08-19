/**
 * 문의폼(contact_form) 모듈 폼 템플릿 — list.js getFullFormTemplate()에서 삽입.
 *
 * 설정은 두 축: 필드 템플릿(formData.contact_template_code) + 디자인 프리셋
 * (formData.contact_design_code). 대상 블로그는 이 모듈을 담은 플로우에 연결된
 * 블로그(flow.blog_links)로 실행 시 결정된다.
 * 실행(수동/오토런)은 멱등: 폼 없으면 생성, 구성(필드·디자인) 바뀌면 수정, 같으면 스킵.
 */
window.getContactFormModuleFormTemplate = function () {
    return `
    <div x-show="formData.type_code === 'contact_form'" class="space-y-4">
        <div class="p-3 bg-purple-50/60 border border-purple-200 rounded-lg">
            <h3 class="text-sm font-semibold text-gray-900 flex items-center gap-2">📨 문의폼 템플릿 선택</h3>
            <p class="text-xs text-gray-500 mt-1">
                이 모듈이 실행되면 <strong>플로우에 연결된 블로그</strong>마다 선택한 문의폼을
                자동으로 만들어 줍니다(Tally). 이미 있으면 그대로 두고, 템플릿이 바뀌면 수정합니다.
                Tally 연동은 <strong>설정 → API 설정 → 문의 폼(Tally 연동)</strong>에서 먼저 등록하세요.
            </p>
        </div>

        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">문의폼 템플릿</label>
            <select x-model="formData.contact_template_code"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent">
                <template x-for="t in contactFormTemplates" :key="t.code">
                    <option :value="t.code" x-text="t.name + ' — ' + t.description + ' (' + t.field_count + '개 항목)'"></option>
                </template>
                <template x-if="contactFormTemplates.length === 0">
                    <option value="basic">기본 (이름·이메일·문의 내용)</option>
                </template>
            </select>
            <p class="mt-1 text-xs text-gray-500">기본 제공 템플릿 중 선택하세요. 항목은 업데이트로 추가됩니다.</p>
        </div>

        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">문의폼 디자인</label>
            <p class="mb-2 text-xs text-gray-500">테마·색상·폰트를 결정합니다. 각 카드는 실제 폼 색상 미리보기입니다. 필드와 독립이라 같은 항목에 색만 바꿀 수 있습니다.</p>

            <!-- 디자인 미리보기 카드 갤러리 -->
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <template x-for="d in contactFormDesigns" :key="d.code">
                    <button type="button"
                            @click="formData.contact_design_code = d.code"
                            :class="formData.contact_design_code === d.code
                                ? 'ring-2 ring-purple-500 border-purple-400'
                                : 'border-gray-200 hover:border-gray-300'"
                            class="relative block border rounded-lg overflow-hidden text-left transition-all focus:outline-none">
                        <!-- 선택 체크 -->
                        <span x-show="formData.contact_design_code === d.code"
                              class="absolute top-1 right-1 z-10 w-5 h-5 rounded-full bg-purple-500 text-white text-xs flex items-center justify-center">✓</span>
                        <!-- 미니 폼 미리보기 -->
                        <div class="p-2.5 space-y-1.5" :style="{ backgroundColor: (d.preview && d.preview.background) || '#ffffff' }">
                            <div class="text-[11px] font-semibold truncate"
                                 :style="{ color: (d.preview && d.preview.text) || '#1f2937' }">문의하기</div>
                            <div class="h-3 rounded"
                                 :style="{ border: '1px solid ' + ((d.preview && d.preview.inputBorder) || '#d1d5db') }"></div>
                            <div class="h-3 rounded"
                                 :style="{ border: '1px solid ' + ((d.preview && d.preview.inputBorder) || '#d1d5db') }"></div>
                            <div class="mt-1 h-5 rounded flex items-center justify-center text-[10px] font-medium"
                                 :style="{ backgroundColor: (d.preview && d.preview.accent) || '#3b82f6', color: (d.preview && d.preview.buttonText) || '#ffffff' }">보내기</div>
                        </div>
                        <!-- 이름 -->
                        <div class="px-2 py-1.5 bg-white border-t border-gray-100">
                            <div class="text-xs font-medium text-gray-800 truncate" x-text="d.name"></div>
                            <div class="text-[10px] text-gray-400 truncate" x-text="d.description"></div>
                        </div>
                    </button>
                </template>
                <template x-if="contactFormDesigns.length === 0">
                    <div class="col-span-full text-xs text-gray-400 py-3 text-center border border-dashed border-gray-200 rounded-lg">
                        디자인 목록을 불러오는 중… (기본 외형 적용)
                    </div>
                </template>
            </div>
        </div>
    </div>
    `;
};
