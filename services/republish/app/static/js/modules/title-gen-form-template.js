/**
 * 제목 생성/수집 모듈 폼.
 *
 * **임시제목 탭의 '제목 작업대'와 같은 구성이다.** 화면에서 수작업으로
 * 검증한 설정을 모듈이 그대로 쓴다. 항목이 다르면 화면에서 되던 것이
 * 자동에서 안 되고, 원인을 찾기 어렵다.
 *
 * 섹션 밖에 놓인 설정은 그 섹션을 껐을 때도 적용된다. 그래서 제목 생성
 * AI·각도 참고·묶음 설정은 **모두 생성 섹션 안**에 둔다.
 *
 * 계획서: docs/plans/title_tab_workplan.md §1
 */
window.getTitleGenFormTemplate = function () {
    return `
    <div x-show="formData.type_code === 'title_gen'" class="space-y-5 border-t border-gray-200 pt-4">

        <div class="px-3 py-2 bg-sky-50 border border-sky-200 rounded-lg text-xs text-sky-800">
            임시제목 탭의 <b>제목 작업대와 같은 코드</b>로 돕니다.
            <b>체크한 섹션만</b> 실행됩니다 — 끈 섹션의 설정은 쓰이지 않습니다.
        </div>

        <!-- ── 수집 ─────────────────────────────────────────── -->
        <div class="border-2 rounded-lg"
             :class="formData.title.collect.enabled ? 'border-blue-300 bg-blue-50/40' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer">
                <input type="checkbox" x-model="formData.title.collect.enabled" class="rounded">
                <span class="text-sm font-medium text-gray-800">수집</span>
                <span class="text-xs text-gray-500">검색으로 제목을 모으고, 밀린 도메인에서 마저 추출합니다</span>
            </label>

            <div x-show="formData.title.collect.enabled" x-cloak class="px-3 pb-3 space-y-2">
                <!-- ① 제목 수집 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.collect.search_enabled" class="rounded">
                        ① 제목 수집 <span class="text-xs text-gray-500">채택 키워드로 검색 → 제목 + 도메인 등록</span>
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
                    <p x-show="formData.title.collect.search_enabled" x-cloak
                       class="mt-1 text-xs text-gray-400">
                        검색된 제목은 <b>바로 임시제목으로</b> 들어가고, 그 제목이 있던 도메인은
                        니치도메인에 등록됩니다. 여기서 도메인의 URL 을 캐지는 않습니다.
                    </p>
                </div>

                <!-- ② 도메인 추출 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.collect.extract_enabled" class="rounded">
                        ② 도메인 추출 <span class="text-xs text-gray-500">등록된 도메인의 사이트맵에서 제목 추출</span>
                    </label>
                    <div x-show="formData.title.collect.extract_enabled" x-cloak class="mt-2">
                        <label class="text-xs text-gray-500">1회 추출 URL 수
                            <input type="number" min="1" max="5000"
                                   x-model.number="formData.title.collect.extract_urls"
                                   class="mt-0.5 w-40 text-sm border-gray-300 rounded py-1">
                        </label>
                        <p class="mt-1 text-xs text-gray-400">
                            <b>회차 전체</b>의 예산입니다(도메인당이 아닙니다). 한 도메인에서 다
                            못 채우면 다음 도메인으로 넘어가고, 남으면 다음 회차에 이어 캡니다.
                        </p>
                    </div>
                </div>

                <!-- 니치 대조 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="text-sm text-gray-800">니치 대조</span>
                        <select x-model="formData.title.collect.niche_mode"
                                class="text-sm border-gray-300 rounded py-1">
                            <option value="mark">표시만 — 저장하되 '니치 무관' 표시</option>
                            <option value="block">차단 — 저장하지 않음</option>
                        </select>
                    </div>
                    <p class="mt-1 text-xs text-gray-400">
                        금지어 필터와 카테고리 분류는 <b>이미 걸려 있습니다.</b>
                        여기서 보는 것은 "그 주제를 쓰는 블로그가 있는가" 입니다.
                        분류표가 얇을 때 차단부터 켜면 살릴 수 있는 제목까지 막힙니다.
                    </p>
                </div>
            </div>
        </div>

        <!-- ── 생성 ─────────────────────────────────────────── -->
        <div class="border-2 rounded-lg"
             :class="formData.title.gen_enabled ? 'border-emerald-300 bg-emerald-50/40' : 'border-gray-200'">
            <label class="flex items-center gap-2 px-3 py-2 cursor-pointer">
                <input type="checkbox" x-model="formData.title.gen_enabled" class="rounded">
                <span class="text-sm font-medium text-gray-800">생성</span>
                <span class="text-xs text-gray-500">채택 키워드·뉴스로 제목을 만듭니다</span>
            </label>

            <div x-show="formData.title.gen_enabled" x-cloak class="px-3 pb-3 space-y-3">
                <!-- 검증 모드 -->
                <label class="flex items-start gap-2 text-sm text-gray-800 p-2 rounded"
                       :class="formData.title.dry_run ? 'bg-amber-50 border border-amber-200' : ''">
                    <input type="checkbox" x-model="formData.title.dry_run" class="rounded mt-0.5">
                    <span>
                        검증 모드 — 제목을 <b>데이터 관리에 저장하지 않고</b> 결과만 보기
                        <span class="block text-xs text-gray-500">
                            자동 실행에 쓰려면 꺼야 합니다. 켜 두면 재고가 늘지 않습니다.
                        </span>
                    </span>
                </label>

                <!-- 제목 생성 AI (생성 섹션 안에 둔다) -->
                <div class="grid grid-cols-2 gap-2">
                    <label class="text-xs text-gray-500">제목 생성 AI
                        <select x-model="formData.title.ai_provider"
                                @change="formData.title.ai_model = ''"
                                class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                            <option value="">블로그 설정 따름</option>
                            <template x-for="p in titleProviders()" :key="p">
                                <option :value="p" x-text="p"></option>
                            </template>
                        </select>
                    </label>
                    <label class="text-xs text-gray-500">모델 <span class="text-gray-400">(비우면 기본값)</span>
                        <select x-model="formData.title.ai_model"
                                :disabled="!formData.title.ai_provider"
                                class="mt-0.5 w-full text-sm border-gray-300 rounded py-1 disabled:bg-gray-50">
                            <option value="">기본값</option>
                            <template x-for="m in titleModelsFor(formData.title.ai_provider)" :key="m">
                                <option :value="m" x-text="m"></option>
                            </template>
                        </select>
                    </label>
                </div>
                <p class="text-xs text-gray-400">
                    비우면 <b>연결된 블로그의 제목 AI</b>를 씁니다. 블로그도 없으면 제목이
                    만들어지지 않습니다 — AI 서비스는 제공자를 지정하지 않으면 거부합니다.
                </p>

                <!-- L1 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.l1_enabled" class="rounded">
                        L1 키워드 기반 <span class="text-xs text-gray-500">채택 키워드 → 묶음 → AI</span>
                    </label>
                    <div x-show="formData.title.l1_enabled" x-cloak class="mt-2 space-y-2">
                        <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
                            <label class="text-xs text-gray-500">묶음 수
                                <input type="number" min="1" max="50"
                                       x-model.number="formData.title.cluster_limit"
                                       class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                            </label>
                            <label class="text-xs text-gray-500">단독 키워드 수
                                <input type="number" min="1" max="100"
                                       x-model.number="formData.title.keyword_limit"
                                       class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                            </label>
                            <label class="text-xs text-gray-500">키워드당 제목
                                <input type="number" min="1" max="10"
                                       x-model.number="formData.title.titles_per_keyword"
                                       class="mt-0.5 w-full text-sm border-gray-300 rounded py-1">
                            </label>
                        </div>
                        <div class="flex flex-wrap gap-4">
                            <label class="flex items-center gap-2 text-sm text-gray-700">
                                <input type="checkbox" x-model="formData.title.use_angles" class="rounded">
                                각도 참고 <span class="text-xs text-gray-500">이미 나온 제목과 겹치지 않게</span>
                            </label>
                            <label class="flex items-center gap-2 text-sm text-gray-700">
                                <input type="checkbox" x-model="formData.title.cluster_enabled" class="rounded">
                                비슷한 키워드 묶기 <span class="text-xs text-gray-500">대표 글 1편 + 곁가지 N편</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- L3 -->
                <div class="p-2 bg-white border border-gray-200 rounded">
                    <label class="flex items-center gap-2 text-sm text-gray-800">
                        <input type="checkbox" x-model="formData.title.l3_enabled" class="rounded">
                        L3 뉴스 시의성 <span class="text-xs text-gray-500">뉴스 요지 + 니치 키워드 결합</span>
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
                        만료된 제목은 재고 선택에서 빠집니다(삭제하지는 않습니다).
                    </p>
                </div>
            </div>
        </div>

        <!-- 테스트 실행 — 저장하지 않은 현재 값으로 한 회차 -->
        <div class="border border-sky-200 bg-sky-50/40 rounded-lg p-3">
            <div class="flex flex-wrap items-center gap-2">
                <button type="button" @click="runTitleTest()" :disabled="tgTest.busy"
                        class="px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium disabled:opacity-40">
                    <span x-text="tgTest.busy
                        ? '실행 중… ' + (tgTest.elapsed ? tgTest.elapsed + '초' : '')
                        : '▶ 이 설정으로 테스트 실행'"></span>
                </button>
                <span class="text-xs text-gray-500">
                    저장하지 않은 현재 값으로 한 회차를 돌려 결과를 아래에 보여 줍니다.
                    <b>켠 섹션만</b> 실행됩니다.
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
                            </div>
                        </template>
                    </div>
                </div>
                <div x-show="(tgTest.result?.samples || []).length">
                    <div class="text-xs font-medium text-gray-500 mb-1">수집된 제목</div>
                    <ul class="text-xs text-gray-600 list-disc list-inside space-y-0.5 max-h-40 overflow-y-auto">
                        <template x-for="(t, i) in (tgTest.result?.samples || [])" :key="i">
                            <li x-text="t"></li>
                        </template>
                    </ul>
                </div>
            </div>
        </div>

        <!-- 실행 스케줄 — 키워드 모듈과 같은 UI -->
        ${window.getTitleScheduleTemplate ? window.getTitleScheduleTemplate() : ''}
    </div>
    `;
};
