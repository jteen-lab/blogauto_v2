/**
 * 제목 생성/수집 모듈 폼 — list.js getFullFormTemplate() 에서 삽입.
 *
 * 계획서: docs/plans/keyword_pipeline_restructure_review.md §5-2
 */
window.getTitleGenFormTemplate = function () {
    return `
    <div x-show="formData.type_code === 'title_gen'" class="space-y-5 border-t border-gray-200 pt-4">

        <div class="px-3 py-2 bg-sky-50 border border-sky-200 rounded-lg text-xs text-sky-800">
            임시제목 탭의 <b>제목 작업대와 같은 코드</b>로 돕니다. 화면에서 되는 것은
            자동에서도 됩니다. 켠 섹션만 실행됩니다.
        </div>

        <!-- ── 수집 ─────────────────────────────────────────── -->
        <div class="border-2 rounded-lg"
             :class="formData.title.collect.enabled ? 'border-blue-300 bg-blue-50/40' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer">
                <input type="checkbox" x-model="formData.title.collect.enabled" class="rounded">
                <span class="text-sm font-medium text-gray-800">수집</span>
                <span class="text-xs text-gray-500">검색으로 제목을 모으고, 도메인에서 마저 캡니다</span>
            </label>

            <div x-show="formData.title.collect.enabled" x-cloak class="px-3 pb-3 space-y-2">
                <!-- ① 제목 수집 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.collect.search_enabled" class="rounded">
                        ① 제목 수집 <span class="text-xs text-gray-500">채택 키워드로 검색</span>
                    </label>
                    <div x-show="formData.title.collect.search_enabled" x-cloak
                         class="mt-2 grid grid-cols-2 gap-2">
                        <label class="text-xs text-gray-500">시드 키워드 수
                            <input type="number" min="1" max="100"
                                   x-model.number="formData.title.collect.seed_limit"
                                   class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                        </label>
                        <label class="text-xs text-gray-500">키워드당 수집 제목 수
                            <input type="number" min="1" max="100"
                                   x-model.number="formData.title.collect.titles_per_keyword"
                                   class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                        </label>
                    </div>
                </div>

                <!-- ② 도메인 추출 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.collect.extract_enabled" class="rounded">
                        ② 도메인 추출 <span class="text-xs text-gray-500">사이트맵에서 제목 추출</span>
                    </label>
                    <div x-show="formData.title.collect.extract_enabled" x-cloak class="mt-2">
                        <label class="text-xs text-gray-500">1회 추출 URL 수
                            <input type="number" min="1" max="5000"
                                   x-model.number="formData.title.collect.extract_urls"
                                   class="mt-0.5 w-40 text-sm border-gray-300 rounded py-1">
                        </label>
                        <p class="mt-1 text-xs text-gray-400">
                            회차 <b>전체</b>의 예산입니다. 한 도메인에서 다 못 채우면 다음
                            도메인으로 넘어가고, 남으면 다음 회차에 이어 캡니다.
                        </p>
                    </div>
                </div>

                <!-- 니치 대조 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="text-xs text-gray-500">니치 대조
                        <select x-model="formData.title.collect.niche_mode"
                                class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                            <option value="mark">표시만 — 저장하되 '니치 무관' 표시</option>
                            <option value="block">차단 — 저장하지 않음</option>
                        </select>
                    </label>
                    <p class="mt-1 text-xs text-gray-400">
                        분류표가 얇을 때 차단부터 켜면 살릴 수 있는 제목까지 막힙니다.
                    </p>
                </div>
            </div>
        </div>

        <!-- ── 생성 켜기 ───────────────────────────────────── -->
        <div class="border-2 rounded-lg"
             :class="formData.title.gen_enabled ? 'border-emerald-300 bg-emerald-50/40' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer">
                <input type="checkbox" x-model="formData.title.gen_enabled" class="rounded">
                <span class="text-sm font-medium text-gray-800">생성</span>
                <span class="text-xs text-gray-500">채택 키워드·뉴스로 제목을 만듭니다</span>
            </label>
            <div x-show="formData.title.gen_enabled" x-cloak class="px-3 pb-3 space-y-2">
                <label class="flex items-center gap-2 text-sm text-gray-800">
                    <input type="checkbox" x-model="formData.title.l1_enabled" class="rounded">
                    L1 키워드 기반 <span class="text-xs text-gray-500">아래 설정을 씁니다</span>
                </label>
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.l3_enabled" class="rounded">
                        L3 뉴스 시의성 <span class="text-xs text-gray-500">뉴스 요지 + 니치 결합</span>
                    </label>
                    <div x-show="formData.title.l3_enabled" x-cloak class="mt-2 grid grid-cols-3 gap-2">
                        <label class="text-xs text-gray-500">조회 기간(일)
                            <input type="number" min="1" max="30" x-model.number="formData.title.news_days"
                                   class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                        </label>
                        <label class="text-xs text-gray-500">제목 수
                            <input type="number" min="1" max="50" x-model.number="formData.title.news_limit"
                                   class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                        </label>
                        <label class="text-xs text-gray-500">만료(일)
                            <input type="number" min="1" max="90" x-model.number="formData.title.expires_days"
                                   class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                        </label>
                    </div>
                    <p x-show="formData.title.l3_enabled" x-cloak class="mt-1 text-xs text-gray-400">
                        뉴스 <b>원문 제목은 재고에 넣지 않습니다.</b> 요지만 뽑아 니치와 엮습니다.
                    </p>
                </div>
            </div>
        </div>

        <!-- 검증 모드 -->
        <div class="p-3 border-2 rounded-lg"
             :class="formData.title.dry_run ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-white'">
            <label class="flex items-start gap-2 text-sm font-medium text-gray-800">
                <input type="checkbox" x-model="formData.title.dry_run" class="rounded mt-0.5">
                <span>
                    검증 모드 — 제목을 <b>데이터 관리에 저장하지 않고</b> 결과만 보기
                    <span class="block mt-1 font-normal text-xs text-gray-600">
                        생성은 그대로 하고 임시제목·정식제목에는 넣지 않습니다.
                        품질을 확인한 뒤 체크를 풀어 실제 재고에 쌓으세요.
                    </span>
                </span>
            </label>
        </div>

        <!-- AI -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">제목 생성 AI</label>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <select x-model="formData.title.ai_provider" @change="formData.title.ai_model = ''"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="">선택 안 함 (블로그 설정 사용)</option>
                    <template x-for="p in tgProviders()" :key="p">
                        <option :value="p" x-text="p"></option>
                    </template>
                </select>
                <select x-model="formData.title.ai_model"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="">기본 모델</option>
                    <template x-for="m in tgModels(formData.title.ai_provider)" :key="m">
                        <option :value="m" x-text="m"></option>
                    </template>
                </select>
            </div>
            <p class="mt-1 text-xs text-gray-500">
                블로그 없이 테스트할 때는 <b>여기서 골라야</b> 제목이 만들어집니다.
            </p>
        </div>

        <!-- 경쟁 제목 각도 -->
        <div class="border-t border-gray-100 pt-4 space-y-3">
            <label class="flex items-start gap-2 text-sm text-gray-700">
                <input type="checkbox" x-model="formData.title.use_angles" class="rounded mt-0.5">
                <span>
                    이미 나와 있는 제목의 <b>각도</b>를 참고 (겹치지 않게 쓰기)
                    <span class="block mt-1 text-xs text-gray-500">
                        수집한 제목을 재고로 쓰지 않습니다. "이 각도는 이미 있으니 다른 질문에 답하라"는
                        신호로만 씁니다. 키워드당 검색 API 1회가 듭니다.
                    </span>
                </span>
            </label>
            <div x-show="formData.title.use_angles">
                <label class="block text-xs text-gray-500 mb-1">참고할 제목 수</label>
                <input type="number" min="1" max="30" x-model.number="formData.title.angle_sample"
                       class="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
        </div>

        <!-- 클러스터 -->
        <div class="border-t border-gray-100 pt-4 space-y-3">
            <label class="flex items-center gap-2 text-sm font-medium text-gray-700">
                <input type="checkbox" x-model="formData.title.cluster_enabled" class="rounded">
                비슷한 키워드를 묶어 대표 글 + 곁가지로 만들기
            </label>
            <div x-show="formData.title.cluster_enabled" class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음 최소 크기</label>
                    <input type="number" min="2" max="30" x-model.number="formData.title.cluster_min_size"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음 최대 크기</label>
                    <input type="number" min="2" max="50" x-model.number="formData.title.cluster_max_size"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶는 기준(0~1)</label>
                    <input type="number" step="0.02" min="0.05" max="1" x-model.number="formData.title.cluster_threshold"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                </div>
                <div>
                    <label class="block text-xs text-gray-500 mb-1">묶음당 곁가지 수</label>
                    <input type="number" min="0" max="30" x-model.number="formData.title.titles_per_cluster"
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <p class="mt-1 text-xs text-gray-400">0이면 묶음 크기만큼</p>
                </div>
            </div>
        </div>

        <!-- 회차 한도 -->
        <div class="border-t border-gray-100 pt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
                <label class="block text-xs text-gray-500 mb-1">회차당 묶음 수</label>
                <input type="number" min="1" max="50" x-model.number="formData.title.cluster_limit"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">회차당 단독 키워드 수</label>
                <input type="number" min="1" max="200" x-model.number="formData.title.keyword_limit"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">단독 키워드당 제목 수</label>
                <input type="number" min="1" max="10" x-model.number="formData.title.titles_per_keyword"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-1">재고 하한</label>
                <input type="number" min="0" x-model.number="formData.title.min_inventory"
                       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
            </div>
        </div>

        <!-- 테스트 -->
        <div class="border-t border-gray-100 pt-4">
            <div class="flex flex-wrap items-center gap-3">
                <button type="button" @click="runTitleTest()" :disabled="tgTest.busy"
                        class="px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium disabled:opacity-40">
                    <span x-text="tgTest.busy
                        ? '실행 중… (묶음→제목) ' + (tgTest.elapsed ? tgTest.elapsed + '초' : '')
                        : '▶ 이 설정으로 테스트 실행'"></span>
                </button>
                <span class="text-xs text-gray-500">
                    저장하지 않은 현재 값으로 한 회차를 돌려 결과를 아래에 보여 줍니다.
                </span>
            </div>

            <div x-show="tgTest.error" x-transition
                 class="mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                <span x-text="tgTest.error"></span>
            </div>

            <div x-show="tgTest.result" x-transition class="mt-3 space-y-3">
                <div class="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-800"
                     x-text="tgTest.result?.message"></div>
                <div x-show="(tgTest.result?.preview || []).length">
                    <div class="text-xs font-medium text-gray-500 mb-1">생성된 제목</div>
                    <div class="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-64 overflow-y-auto">
                        <template x-for="(t, i) in (tgTest.result?.preview || [])" :key="i">
                            <div class="flex items-start gap-2 px-3 py-1.5 text-sm">
                                <span class="text-xs px-1.5 py-0.5 rounded shrink-0"
                                      :class="t.state === 'ready' ? 'bg-green-100 text-green-700'
                                            : t.state === 'blocked' ? 'bg-red-100 text-red-700'
                                            : 'bg-gray-100 text-gray-600'"
                                      x-text="t.reason"></span>
                                <span class="text-gray-800" x-text="t.title"></span>
                                <span x-show="t.cluster" class="ml-auto text-xs text-gray-400" x-text="t.cluster"></span>
                            </div>
                        </template>
                    </div>
                </div>
            </div>
        </div>

        <!-- 주기 -->
        <div class="border-t border-gray-100 pt-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">실행 간격 (분)</label>
            <input type="number" min="30" x-model.number="formData.title.interval_minutes"
                   class="w-40 px-3 py-2 border border-gray-300 rounded-lg text-sm">
        </div>
    </div>
    `;
};
