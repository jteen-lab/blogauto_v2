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

        <!-- 검증 모드 -->
        <div class="p-3 border-2 rounded-lg"
             :class="formData.keyword.dry_run ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-white'">
            <label class="flex items-start gap-2 text-sm font-medium text-gray-800">
                <input type="checkbox" x-model="formData.keyword.dry_run" class="rounded mt-0.5">
                <span>
                    검증 모드 — 제목을 <b>데이터 관리에 저장하지 않고</b> 결과만 보기
                    <span class="block mt-1 font-normal text-xs text-gray-600">
                        수집·측정·제목 생성은 그대로 하고, 임시제목·정식제목에는 넣지 않습니다.
                        동작 로그에서 어떤 제목이 나왔고 무엇이 필터에 걸렸는지 확인한 뒤,
                        쓸 만해지면 이 체크를 풀어 실제 재고에 쌓으세요.
                    </span>
                </span>
            </label>
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

        <!-- 수집 소스 -->
        <div class="border-t border-gray-100 pt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">수집 소스</label>
            <div class="px-3 py-2 mb-3 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                한 소스만 쓰면 그 소스의 한계가 결과의 한계가 됩니다.
                <b>네이버 검색광고는 항상 켜집니다</b> — 검색량을 아는 유일한 소스라
                끄면 후보가 전부 미측정으로 남습니다.
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                <label class="flex items-start gap-2 text-sm text-gray-500">
                    <input type="checkbox" checked disabled class="rounded mt-0.5">
                    <span>네이버 검색광고 <span class="text-xs">(연관키워드 + 검색량 · 필수)</span></span>
                </label>
                <label class="flex items-start gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.src_naver_suggest" class="rounded mt-0.5">
                    <span>네이버 자동완성 <span class="text-xs text-gray-500">(최신성 강함 · 비공식 경로)</span></span>
                </label>
                <label class="flex items-start gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.src_google_suggest" class="rounded mt-0.5">
                    <span>구글 자동완성 <span class="text-xs text-gray-500">(롱테일·질문형 · 비공식 경로)</span></span>
                </label>
                <label class="flex items-start gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.src_gsc" class="rounded mt-0.5">
                    <span>서치콘솔 실측 쿼리 <span class="text-xs text-gray-500">(우리 글이 실제 노출된 검색어 · 속성 등록 필요)</span></span>
                </label>
                <label class="flex items-start gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.src_google_planner" class="rounded mt-0.5">
                    <span>구글 키워드플래너 <span class="text-xs text-gray-500">(검색량은 구간값 · 정렬용)</span></span>
                </label>
                <label class="flex items-start gap-2 text-sm text-gray-700">
                    <input type="checkbox" x-model="formData.keyword.src_google_trends" class="rounded mt-0.5">
                    <span>구글 트렌드 <span class="text-xs text-gray-500">(연관·급상승 · 절대 검색량 없음)</span></span>
                </label>
            </div>
            <div class="mt-3">
                <label class="block text-xs text-gray-500 mb-1">회차당 검색량 보강 수</label>
                <input type="number" min="0" max="500" x-model.number="formData.keyword.enrich_limit"
                       class="w-40 px-3 py-2 border border-gray-300 rounded-lg text-sm">
                <p class="mt-1 text-xs text-gray-500">
                    자동완성·트렌드·서치콘솔은 키워드만 줍니다. 검색광고로 검색량을 채웁니다.
                </p>
            </div>
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

        <!-- 클러스터 생산 -->
        <div class="border-t border-gray-100 pt-4 space-y-3">
            <label class="flex items-center gap-2 text-sm font-medium text-gray-700">
                <input type="checkbox" x-model="formData.keyword.cluster_enabled" class="rounded">
                비슷한 키워드를 묶어 <b>대표 글 1편 + 곁가지 글 N편</b>으로 만들기
            </label>
            <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
                키워드 1개 = 제목 1개는 대량 발행에 맞지 않습니다. 묶음 하나에서
                <b>서로 다른 질문</b>에 답하는 제목이 여러 개 나옵니다.
                묶이지 않은 키워드는 기존 방식으로 처리됩니다.
            </div>
            <div x-show="formData.keyword.cluster_enabled" class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음 최소 크기</label>
                    <input type="number" min="2" max="30" x-model.number="formData.keyword.cluster_min_size"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음 최대 크기</label>
                    <input type="number" min="2" max="50" x-model.number="formData.keyword.cluster_max_size"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶는 기준(0~1)</label>
                    <input type="number" step="0.02" min="0.05" max="1" x-model.number="formData.keyword.cluster_threshold"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음당 곁가지 수</label>
                    <input type="number" min="0" max="30" x-model.number="formData.keyword.titles_per_cluster"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <p class="mt-1 text-xs text-gray-400">0이면 묶음 크기만큼</p>
                </div>
            </div>
        </div>

        <!-- 제목 생성 AI -->
        <div class="border-t border-gray-100 pt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">제목 생성 AI</label>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <select x-model="formData.keyword.ai_provider"
                        @change="formData.keyword.ai_model = ''"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="">선택 안 함 (블로그 설정 사용)</option>
                    <template x-for="p in kwProviders()" :key="p">
                        <option :value="p" x-text="p"></option>
                    </template>
                </select>
                <select x-model="formData.keyword.ai_model"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="">기본 모델</option>
                    <template x-for="m in kwModels(formData.keyword.ai_provider)" :key="m">
                        <option :value="m" x-text="m"></option>
                    </template>
                </select>
            </div>
            <p class="mt-1 text-xs text-gray-500">
                블로그 없이 시드만으로 테스트할 때는 <b>여기서 골라야</b> 제목이 만들어집니다.
                비워 두면 블로그의 글쓰기 AI를 쓰고, 그것도 없으면 제목 생성이 전부 실패합니다.
            </p>
        </div>

        <!-- 테스트 실행 -->
        <div class="border-t border-gray-100 pt-4">
            <div class="flex flex-wrap items-center gap-3">
                <button type="button" @click="runKeywordTest()" :disabled="kwTest.busy"
                        class="px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium disabled:opacity-40">
                    <span x-text="kwTest.busy ? '실행 중… (수집→측정→제목)' : '▶ 이 설정으로 테스트 실행'"></span>
                </button>
                <span class="text-xs text-gray-500">
                    저장하지 않은 현재 화면 값 그대로 한 회차를 돌려 결과를 아래에 보여 줍니다.
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
                    <div class="text-xs font-medium text-gray-500 mb-1">
                        수집된 키워드 <span x-text="'(' + (kwTest.result?.samples || []).length + '개 표시)'"></span>
                    </div>
                    <div class="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                        <template x-for="k in (kwTest.result?.samples || [])" :key="k">
                            <span class="px-2 py-0.5 bg-amber-50 border border-amber-200 rounded text-xs" x-text="k"></span>
                        </template>
                    </div>
                </div>

                <div x-show="(kwTest.result?.preview || []).length">
                    <div class="text-xs font-medium text-gray-500 mb-1">생성된 제목 (검증 모드면 저장 안 됨)</div>
                    <div class="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-64 overflow-y-auto">
                        <template x-for="(t, i) in (kwTest.result?.preview || [])" :key="i">
                            <div class="flex items-start gap-2 px-3 py-1.5 text-sm">
                                <span class="text-xs px-1.5 py-0.5 rounded shrink-0"
                                      :class="t.state === 'ready' ? 'bg-green-100 text-green-700'
                                            : t.state === 'blocked' ? 'bg-red-100 text-red-700'
                                            : 'bg-gray-100 text-gray-600'"
                                      x-text="t.reason"></span>
                                <span class="text-gray-800" x-text="t.title"></span>
                            </div>
                        </template>
                    </div>
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
