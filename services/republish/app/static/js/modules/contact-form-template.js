/**
 * 문의폼(contact_form) 모듈 폼 템플릿 — list.js getFullFormTemplate()에서 삽입.
 *
 * 설정은 템플릿 선택(formData.contact_template_code) 하나. 대상 블로그는 이
 * 모듈을 담은 플로우에 연결된 블로그(flow.blog_links)로 실행 시 결정된다.
 * 실행(수동/오토런)은 멱등: 폼 없으면 생성, 구성 바뀌면 수정, 같으면 스킵.
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
    </div>
    `;
};
