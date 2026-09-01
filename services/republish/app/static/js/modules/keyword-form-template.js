/**
 * 키워드 모듈 폼 템플릿 — list.js getFullFormTemplate() 에서 삽입.
 *
 * 순서도: docs/flowcharts/keyword_module.md
 */
window.getKeywordFormTemplate = function () {
    return `
    <div x-show="formData.type_code === 'keyword'" class="space-y-5 border-t border-gray-200 pt-4">

        <div class="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
            수요(검색량)를 재고 포화도가 낮은 키워드만 골라 제목까지 만들어 재고에 넣습니다.
            <b>재고가 충분하면 돌지 않습니다</b> — 매번 도는 것은 API 낭비입니다.
        </div>

        <!-- 시드 -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">시드 키워드 (선택)</label>
            <input type="text" x-model="formData.keyword.seeds_text"
                   class="w-full px-3 py-2 border border-gray-300 rounded-lg"
                   placeholder="예: 전기기사, 컴활 1급  (비우면 블로그 카테고리를 씁니다)">
            <p class="mt-1 text-xs text-gray-500">
                공백·가운뎃점은 보낼 때 자동으로 정리됩니다. 네이버가 그런 키워드를 거부합니다.
            </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label class="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" x-model="formData.keyword.use_blog_categories" class="rounded">
                블로그의 활성 카테고리를 시드로 사용
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" x-model="formData.keyword.recurse_adopted" class="rounded">
                채택된 키워드를 다음 회차 시드로 (소재 고갈 방지)
            </label>
        </div>

        <!-- 수식어 -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">수식어</label>
            <input type="text" x-model="formData.keyword.modifiers_text"
                   class="w-full px-3 py-2 border border-gray-300 rounded-lg"
                   placeholder="방법, 추천, 후기, 비교, 초보">
            <p class="mt-1 text-xs text-gray-500">
                시드 하나로 후보를 여러 개 만듭니다. 5개씩 묶어 보내므로 API 호출은 늘지 않습니다.
            </p>
        </div>

        <!-- 판정 기준 -->
        <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
            공급은 누적 문서수가 아니라 <b>최근 N일 발행량</b>으로 봅니다.
            누적은 10년치 총합이라 지금 경쟁이 붙는지 알려 주지 않습니다.
            검색량 <b>상한</b>도 둡니다 — 대형 키워드는 써도 묻힙니다.
        </div>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div>
                <label class="block text-xs text-gray-500 mb-1">검색량 하한</label>
                <input type="number" min="0" x-model.number="formData.keyword.min_volume"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">검색량 상한</label>
                <input type="number" min="0" x-model.number="formData.keyword.max_volume"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">발행량 기간(일)</label>
                <input type="number" min="1" max="365" x-model.number="formData.keyword.pub_window_days"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">포화도 하한</label>
                <input type="number" step="0.05" min="0" x-model.number="formData.keyword.min_saturation"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">회차당 시드 수</label>
                <input type="number" min="1" max="50" x-model.number="formData.keyword.seed_limit"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">회차당 측정 수</label>
                <input type="number" min="1" max="100" x-model.number="formData.keyword.measure_limit"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
        </div>

        <!-- 제목 생성 -->
        <div class="border-t border-gray-100 pt-4 space-y-3">
            <label class="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" x-model="formData.keyword.make_titles" class="rounded">
                채택 키워드로 제목을 만들어 재고에 넣기
            </label>
            <div x-show="formData.keyword.make_titles" class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs text-gray-500 mb-1">키워드당 제목 수</label>
                    <input type="number" min="1" max="10" x-model.number="formData.keyword.titles_per_keyword"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">재고 하한 (이보다 많으면 안 돎)</label>
                    <input type="number" min="0" x-model.number="formData.keyword.min_inventory"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
            </div>
        </div>

        <!-- 주기 -->
        <div class="border-t border-gray-100 pt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">실행 간격 (분)</label>
            <input type="number" min="30" x-model.number="formData.keyword.interval_minutes"
                   class="w-40 px-3 py-2 border border-gray-300 rounded-lg text-sm">
            <p class="mt-1 text-xs text-gray-500">
                성장 프로파일과 별개입니다. 성장 프로파일은 발행 주기를 정하고,
                키워드 생산은 재고가 부족한지로 돕니다.
            </p>
        </div>
    </div>
    `;
};
