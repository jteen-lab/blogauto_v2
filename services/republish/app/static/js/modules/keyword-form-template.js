/**
 * 키워드 모듈 폼 — list.js getFullFormTemplate() 에서 삽입.
 *
 * 단계(수집·측정·분류·재판정)를 **섹션으로 나누고**, 섹션 체크박스로
 * 켜야 그 설정이 열린다. 하나만 켜면 그 단계 전용 모듈이 된다.
 *
 * 스케줄은 다른 모듈과 같은 방식(고정 시간 / 간격 + 활성 시간대)을 쓴다.
 *
 * 순서도: docs/flowcharts/keyword_module.md
 */
window.getKeywordFormTemplate = function () {
    return `
    <div x-show="formData.type_code === 'keyword'" class="space-y-4 border-t border-gray-200 pt-4">

        <div class="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
            아래 단계를 <b>켠 것만</b> 수행합니다. 하나만 켜면 그 단계 전용 모듈이 되고,
            전부 켜면 한 모듈이 다 합니다. 모든 작업은 <b>키워드 DB를 기준</b>으로 돌기 때문에
            모듈을 여러 개 두어도 서로 꼬이지 않습니다.
        </div>

        <!-- ① 수집 -->
        <div class="border-2 rounded-lg overflow-hidden"
             :class="formData.keyword.step_collect ? 'border-amber-300' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer"
                   :class="formData.keyword.step_collect ? 'bg-amber-50' : 'bg-gray-50'">
                <input type="checkbox" x-model="formData.keyword.step_collect" class="rounded">
                <span class="text-sm font-semibold text-gray-800">① 수집</span>
                <span class="text-xs text-gray-500">시드·발견 → 새 키워드를 DB에 쌓습니다</span>
            </label>

            <div x-show="formData.keyword.step_collect" x-transition class="p-3 space-y-4 border-t border-gray-200">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">시드 키워드 (선택)</label>
                    <input type="text" x-model="formData.keyword.seeds_text"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg"
                           placeholder="예: 전기기사, 컴활 1급  (비우면 블로그 카테고리를 씁니다)">
                    <p class="mt-1 text-xs text-gray-500">
                        출발점입니다. 각 시드로 연관 키워드를 받아옵니다. 공백은 보낼 때 자동 정리됩니다.
                    </p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label class="flex items-center gap-2 text-sm text-gray-700">
                        <input type="checkbox" x-model="formData.keyword.use_blog_categories" class="rounded">
                        블로그의 활성 카테고리를 시드로 사용
                    </label>
                    <label class="flex items-center gap-2 text-sm text-gray-700">
                        <input type="checkbox" x-model="formData.keyword.recurse_adopted" class="rounded">
                        채택된 키워드를 다음 회차 시드로 (소재 고갈 방지)
                    </label>
                </div>

                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">수식어</label>
                    <input type="text" x-model="formData.keyword.modifiers_text"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg"
                           placeholder="방법, 추천, 후기, 비교, 초보">
                    <p class="mt-1 text-xs text-gray-500">
                        시드에 붙여 조회 대상을 늘립니다. 5개씩 묶어 보내므로 API 호출은 거의 늘지 않습니다.
                    </p>
                </div>

                <div>
                    <div class="text-xs font-medium text-gray-500 mb-1">발견 — 시드 없이 지금 뜨는 말</div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_google_trending" class="rounded mt-0.5">
                            <span>구글 실시간 인기 <span class="text-xs text-gray-500">(시드 불필요)</span></span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.discovery_niche_filter" class="rounded mt-0.5">
                            <span>발견 결과에 <b>니치 필터</b> <span class="text-xs text-gray-500">(무관한 트렌드어 차단)</span></span>
                        </label>
                    </div>

                    <div class="text-xs font-medium text-gray-500 mb-1">확장 — 시드에서 가지를 뻗는다</div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <label class="flex items-start gap-2 text-sm text-gray-500">
                            <input type="checkbox" checked disabled class="rounded mt-0.5">
                            <span>네이버 검색광고 <span class="text-xs">(연관+검색량 · 필수)</span></span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_naver_suggest" class="rounded mt-0.5">
                            <span>네이버 자동완성</span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_google_suggest" class="rounded mt-0.5">
                            <span>구글 자동완성</span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_gsc" class="rounded mt-0.5">
                            <span>서치콘솔 실측 쿼리 <span class="text-xs text-gray-500">(속성 등록 필요)</span></span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_google_planner" class="rounded mt-0.5">
                            <span>구글 키워드플래너 <span class="text-xs text-gray-500">(구간값)</span></span>
                        </label>
                        <label class="flex items-start gap-2 text-sm text-gray-700">
                            <input type="checkbox" x-model="formData.keyword.src_google_trends" class="rounded mt-0.5">
                            <span>구글 트렌드 <span class="text-xs text-gray-500">(연관·급상승)</span></span>
                        </label>
                    </div>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">회차당 시드 수</label>
                        <input type="number" min="1" max="50" x-model.number="formData.keyword.seed_limit"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    </div>
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">회차당 수집 한도</label>
                        <input type="number" min="10" max="500" x-model.number="formData.keyword.collect_limit"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                        <p class="mt-1 text-xs text-gray-400">시드별이 아니라 합계</p>
                    </div>
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">검색량 보강 수</label>
                        <input type="number" min="0" max="500" x-model.number="formData.keyword.enrich_limit"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    </div>
                </div>
            </div>
        </div>

        <!-- ② 측정 -->
        <div class="border-2 rounded-lg overflow-hidden"
             :class="formData.keyword.step_measure ? 'border-sky-300' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer"
                   :class="formData.keyword.step_measure ? 'bg-sky-50' : 'bg-gray-50'">
                <input type="checkbox" x-model="formData.keyword.step_measure" class="rounded">
                <span class="text-sm font-semibold text-gray-800">② 측정</span>
                <span class="text-xs text-gray-500">DB에서 아직 안 잰 키워드의 검색량·발행량을 잽니다</span>
            </label>

            <div x-show="formData.keyword.step_measure || formData.keyword.step_rejudge" x-transition
                 class="p-3 space-y-3 border-t border-gray-200">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                    <b>검색량 보강</b>(검색량이 빈 키워드를 검색광고로 채움) →
                    <b>공급 측정</b>(최근 N일 발행량, 키워드당 검색 API 2회) 순으로 돕니다.
                    아래 기준값은 <b>재판정</b>에도 같이 쓰입니다.
                </div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
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
                        <label class="block text-xs text-gray-500 mb-1">포화도 하한</label>
                        <input type="number" step="0.05" min="0" x-model.number="formData.keyword.min_saturation"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    </div>
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">발행량 기간(일)</label>
                        <input type="number" min="1" max="365" x-model.number="formData.keyword.pub_window_days"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    </div>
                </div>
                <div x-show="formData.keyword.step_measure">
                    <label class="block text-xs text-gray-500 mb-1">회차당 측정 수</label>
                    <input type="number" min="1" max="200" x-model.number="formData.keyword.measure_limit"
                           class="w-40 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <p class="mt-1 text-xs text-gray-400">키워드당 검색 API 2회가 듭니다</p>
                </div>
            </div>
        </div>

        <!-- ③ 분류 -->
        <div class="border-2 rounded-lg overflow-hidden"
             :class="formData.keyword.step_classify ? 'border-green-300' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer"
                   :class="formData.keyword.step_classify ? 'bg-green-50' : 'bg-gray-50'">
                <input type="checkbox" x-model="formData.keyword.step_classify" class="rounded">
                <span class="text-sm font-semibold text-gray-800">③ 분류</span>
                <span class="text-xs text-gray-500">DB의 미분류 키워드에 니치를 붙입니다</span>
            </label>

            <div x-show="formData.keyword.step_classify" x-transition
                 class="p-3 border-t border-gray-200">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                    카테고리 관리의 분류표로 니치를 붙입니다. <b>API 호출이 없어 비용이 들지 않습니다.</b>
                    아직 안 훑은 키워드부터 순서대로 가져가며, 분류표에 없는 말은 미분류로 남습니다.
                    니치가 붙어야 그 니치를 가진 블로그가 이 키워드를 씁니다.
                </div>
            </div>
        </div>

        <!-- ④ 재판정 -->
        <div class="border-2 rounded-lg overflow-hidden"
             :class="formData.keyword.step_rejudge ? 'border-purple-300' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer"
                   :class="formData.keyword.step_rejudge ? 'bg-purple-50' : 'bg-gray-50'">
                <input type="checkbox" x-model="formData.keyword.step_rejudge" class="rounded">
                <span class="text-sm font-semibold text-gray-800">④ 재판정</span>
                <span class="text-xs text-gray-500">DB 전체를 현재 기준값으로 다시 판정합니다</span>
            </label>

            <div x-show="formData.keyword.step_rejudge" x-transition
                 class="p-3 border-t border-gray-200">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                    <b>② 측정 섹션의 기준값</b>을 씁니다. API 호출은 없지만 전체 행을 훑으므로,
                    기준을 자주 바꾸지 않는다면 꺼 두는 편이 낫습니다.
                </div>
            </div>
        </div>

        <!-- 공통 -->
        <div class="border border-gray-200 rounded-lg p-3 space-y-3">
            <div class="text-sm font-semibold text-gray-800">공통</div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs text-gray-500 mb-1">재고 하한 (이보다 많으면 안 돎)</label>
                    <input type="number" min="0" x-model.number="formData.keyword.min_inventory"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <label class="flex items-start gap-2 text-sm text-gray-700 pt-5">
                    <input type="checkbox" x-model="formData.keyword.feedback_enabled" class="rounded mt-0.5">
                    <span>실측 성과 되먹임 <span class="text-xs text-gray-500">(노출된 축을 다음 시드로 먼저)</span></span>
                </label>
            </div>
        </div>

        ${window.getKeywordScheduleTemplate ? window.getKeywordScheduleTemplate() : ''}

        <!-- 제목 생성 (이전 방식) -->
        <details class="border border-gray-200 rounded-lg">
            <summary class="px-3 py-2 text-sm text-gray-600 cursor-pointer select-none">
                제목 생성 (이전 방식 · 기본 꺼짐)
            </summary>
            <div class="p-3 border-t border-gray-200 space-y-3">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                    제목은 <b>'제목 생성/수집' 모듈</b>이 맡습니다. 수집 모듈이 제목까지 만들면
                    중간 결과를 걸러낼 자리가 없습니다.
                </div>
                <label class="flex items-center gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.make_titles" class="rounded">
                    (이전 방식) 채택 키워드로 제목을 만들어 재고에 넣기
                </label>
                <div x-show="formData.keyword.make_titles" class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs text-gray-500 mb-1">키워드당 제목 수</label>
                        <input type="number" min="1" max="10" x-model.number="formData.keyword.titles_per_keyword"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    </div>
                    <label class="flex items-center gap-2 text-sm text-gray-700 pt-5">
                        <input type="checkbox" x-model="formData.keyword.dry_run" class="rounded">
                        검증 모드 (저장하지 않고 결과만)
                    </label>
                </div>
            </div>
        </details>

        <!-- 테스트 -->
        <div class="border-t border-gray-100 pt-4">
            <div class="flex flex-wrap items-center gap-3">
                <button type="button" @click="runKeywordTest()" :disabled="kwTest.busy"
                        class="px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium disabled:opacity-40">
                    <span x-text="kwTest.busy
                        ? '실행 중… ' + (kwTest.elapsed ? kwTest.elapsed + '초' : '')
                        : '▶ 이 설정으로 테스트 실행'"></span>
                </button>
                <span class="text-xs text-gray-500">
                    저장하지 않은 현재 값으로 한 회차를 돌려 결과를 아래에 보여 줍니다.
                </span>
            </div>

            <div x-show="kwTest.error" x-transition
                 class="mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                <span x-text="kwTest.error"></span>
            </div>

            <div x-show="kwTest.result" x-transition class="mt-3 space-y-3">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800"
                     x-text="kwTest.result?.message"></div>
                <div x-show="Object.keys(kwTest.result?.by_source || {}).length">
                    <div class="text-xs font-medium text-gray-500 mb-1">소스별 수집</div>
                    <div class="flex flex-wrap gap-1.5">
                        <template x-for="[code, n] in Object.entries(kwTest.result?.by_source || {})" :key="code">
                            <span class="px-2 py-0.5 bg-white border border-gray-200 rounded text-xs"
                                  x-text="code + ' ' + n"></span>
                        </template>
                    </div>
                </div>
                <div x-show="(kwTest.result?.samples || []).length">
                    <div class="text-xs font-medium text-gray-500 mb-1">수집된 키워드</div>
                    <div class="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                        <template x-for="k in (kwTest.result?.samples || [])" :key="k">
                            <span class="px-2 py-0.5 bg-amber-50 border border-amber-200 rounded text-xs" x-text="k"></span>
                        </template>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `;
};
