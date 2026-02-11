/** 생성 모듈 폼 HTML 템플릿 - list.js의 getFullFormTemplate()에서 호출 */
function getGenerateModuleFormTemplate() {
    return `
                        <!-- 생성 모듈 설정: 참조자료 수집 -->
                        <div x-show="formData.type_code === 'generate'" class="space-y-6">
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    참조자료 수집 설정
                                </h3>

                                <div class="border border-orange-200 rounded-lg p-4 space-y-5">
                                    <!-- 프로세스 설명 -->
                                    <div class="p-3 bg-orange-50 rounded-lg">
                                        <p class="text-sm text-orange-800 font-medium mb-2">참조자료 수집 프로세스:</p>
                                        <ol class="text-xs text-orange-700 space-y-1 list-decimal list-inside">
                                            <li>제목으로 네이버 웹문서 검색</li>
                                            <li>검색 결과 페이지 크롤링 (실패 도메인 자동 제외)</li>
                                            <li>AI 또는 알고리즘으로 핵심 내용 요약</li>
                                            <li>요약된 참조자료를 글 생성에 활용</li>
                                        </ol>
                                    </div>

                                    <!-- 1. 수량 설정 (3열 그리드) -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-3">수집 수량</label>
                                        <div class="grid grid-cols-3 gap-3">
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">최대 검색 수</label>
                                                <input type="number"
                                                       x-model.number="formData.ref_max_search"
                                                       min="10" max="100"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">10~100</p>
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">크롤링 목표</label>
                                                <input type="number"
                                                       x-model.number="formData.ref_crawl_target"
                                                       min="3" max="30"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">3~30</p>
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">요약 선택 수</label>
                                                <input type="number"
                                                       x-model.number="formData.ref_summary_count"
                                                       min="1" max="10"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">1~10</p>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- 비용 경고 (인라인) -->
                                    <div x-show="formData.ref_summary_count > 5" x-transition
                                         class="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                        <p class="text-sm text-amber-800">
                                            <span class="font-medium">&#9888;&#65039; 비용 주의:</span>
                                            요약 개수가 많으면 AI API 토큰 사용량이 증가하여 비용이 높아질 수 있습니다.
                                            비용을 절감하려면 '텍스트 알고리즘' 요약 방법을 선택하세요.
                                        </p>
                                    </div>

                                    <!-- 2. 요약 방법 선택 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-3">요약 방법</label>
                                        <div class="grid grid-cols-2 gap-3">
                                            <label class="flex items-center p-3 border-2 rounded-lg cursor-pointer transition-colors"
                                                   :class="formData.ref_summary_method === 'ai'
                                                       ? 'bg-purple-50 border-purple-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                <input type="radio" value="ai"
                                                       x-model="formData.ref_summary_method"
                                                       class="w-4 h-4 text-purple-600 focus:ring-purple-500">
                                                <div class="ml-3">
                                                    <span class="text-sm font-medium">&#129302; AI 요약</span>
                                                    <p class="text-xs text-gray-500">고품질, API 비용 발생</p>
                                                </div>
                                            </label>
                                            <label class="flex items-center p-3 border-2 rounded-lg cursor-pointer transition-colors"
                                                   :class="formData.ref_summary_method === 'algorithm'
                                                       ? 'bg-green-50 border-green-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                <input type="radio" value="algorithm"
                                                       x-model="formData.ref_summary_method"
                                                       class="w-4 h-4 text-green-600 focus:ring-green-500">
                                                <div class="ml-3">
                                                    <span class="text-sm font-medium">&#9889; 텍스트 알고리즘</span>
                                                    <p class="text-xs text-gray-500">빠르고 비용 없음</p>
                                                </div>
                                            </label>
                                        </div>
                                    </div>

                                    <!-- 3. AI 요약 상세 설정 -->
                                    <div x-show="formData.ref_summary_method === 'ai'" x-transition class="space-y-4 pl-1">
                                        <!-- AI 서비스 선택 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">AI 서비스</label>
                                            <div class="grid grid-cols-3 gap-2">
                                                <label class="flex items-center p-2.5 border rounded-lg cursor-pointer transition-colors text-center"
                                                       :class="formData.ref_ai_provider === 'openai'
                                                           ? 'bg-blue-50 border-blue-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                    <input type="radio" value="openai"
                                                           x-model="formData.ref_ai_provider"
                                                           class="w-3.5 h-3.5 text-blue-600 focus:ring-blue-500">
                                                    <span class="ml-2 text-sm font-medium">ChatGPT</span>
                                                </label>
                                                <label class="flex items-center p-2.5 border rounded-lg cursor-pointer transition-colors text-center"
                                                       :class="formData.ref_ai_provider === 'anthropic'
                                                           ? 'bg-orange-50 border-orange-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                    <input type="radio" value="anthropic"
                                                           x-model="formData.ref_ai_provider"
                                                           class="w-3.5 h-3.5 text-orange-600 focus:ring-orange-500">
                                                    <span class="ml-2 text-sm font-medium">Claude</span>
                                                </label>
                                                <label class="flex items-center p-2.5 border rounded-lg cursor-pointer transition-colors text-center"
                                                       :class="formData.ref_ai_provider === 'google'
                                                           ? 'bg-emerald-50 border-emerald-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                    <input type="radio" value="google"
                                                           x-model="formData.ref_ai_provider"
                                                           class="w-3.5 h-3.5 text-emerald-600 focus:ring-emerald-500">
                                                    <span class="ml-2 text-sm font-medium">Gemini</span>
                                                </label>
                                            </div>
                                        </div>

                                        <!-- AI 모델 선택 (서비스별 동적) -->
                                        <div x-effect="
                                            const defaults = {openai:'gpt-4.1-mini', anthropic:'claude-haiku-4-5-20251001', google:'gemini-2.5-flash'};
                                            const valid = {
                                                openai: ['gpt-4.1-nano','gpt-4.1-mini','gpt-4.1','gpt-4o-mini','gpt-4o','gpt-5-nano','gpt-5-mini','gpt-5','gpt-5.2'],
                                                anthropic: ['claude-3-haiku-20240307','claude-haiku-4-5-20251001','claude-sonnet-4-20250514','claude-sonnet-4-5-20250929','claude-opus-4-5-20251101','claude-opus-4-6'],
                                                google: ['gemini-2.5-flash-lite','gemini-2.5-flash','gemini-2.5-pro','gemini-3-flash-preview','gemini-3-pro-preview']
                                            };
                                            if (!(valid[formData.ref_ai_provider]||[]).includes(formData.ref_ai_model)) {
                                                formData.ref_ai_model = defaults[formData.ref_ai_provider] || 'gpt-4.1-mini';
                                            }
                                        ">
                                            <label class="block text-sm font-medium text-gray-700 mb-2">AI 모델</label>
                                            <!-- OpenAI 모델 -->
                                            <select x-show="formData.ref_ai_provider === 'openai'"
                                                    x-model="formData.ref_ai_model"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm">
                                                <optgroup label="GPT-4.1 (비추론)">
                                                    <option value="gpt-4.1-nano">GPT-4.1 Nano (최저비용)</option>
                                                    <option value="gpt-4.1-mini">GPT-4.1 Mini (추천)</option>
                                                    <option value="gpt-4.1">GPT-4.1 (고품질)</option>
                                                </optgroup>
                                                <optgroup label="GPT-4o (레거시)">
                                                    <option value="gpt-4o-mini">GPT-4o Mini</option>
                                                    <option value="gpt-4o">GPT-4o</option>
                                                </optgroup>
                                                <optgroup label="GPT-5 (추론)">
                                                    <option value="gpt-5-nano">GPT-5 Nano (최저비용)</option>
                                                    <option value="gpt-5-mini">GPT-5 Mini</option>
                                                    <option value="gpt-5">GPT-5</option>
                                                    <option value="gpt-5.2">GPT-5.2 (플래그십)</option>
                                                </optgroup>
                                            </select>
                                            <!-- Anthropic 모델 -->
                                            <select x-show="formData.ref_ai_provider === 'anthropic'"
                                                    x-model="formData.ref_ai_model"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm">
                                                <optgroup label="Claude 4.5~4.6 (최신)">
                                                    <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5 (추천, 저비용)</option>
                                                    <option value="claude-sonnet-4-5-20250929">Claude Sonnet 4.5</option>
                                                    <option value="claude-opus-4-5-20251101">Claude Opus 4.5</option>
                                                    <option value="claude-opus-4-6">Claude Opus 4.6 (플래그십)</option>
                                                </optgroup>
                                                <optgroup label="Claude 4 (레거시)">
                                                    <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                                                </optgroup>
                                                <optgroup label="Claude 3 (레거시)">
                                                    <option value="claude-3-haiku-20240307">Claude 3 Haiku (최저비용)</option>
                                                </optgroup>
                                            </select>
                                            <!-- Google 모델 -->
                                            <select x-show="formData.ref_ai_provider === 'google'"
                                                    x-model="formData.ref_ai_model"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm">
                                                <optgroup label="Gemini 3 (최신)">
                                                    <option value="gemini-3-flash-preview">Gemini 3 Flash Preview</option>
                                                    <option value="gemini-3-pro-preview">Gemini 3 Pro Preview (고품질)</option>
                                                </optgroup>
                                                <optgroup label="Gemini 2.5 (안정)">
                                                    <option value="gemini-2.5-flash-lite">Gemini 2.5 Flash Lite (최저비용)</option>
                                                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (추천)</option>
                                                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (고품질)</option>
                                                </optgroup>
                                            </select>
                                        </div>

                                        <!-- 요약 스타일 선택 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">요약 스타일</label>
                                            <select x-model="formData.ref_summary_style"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-sm">
                                                <option value="concise">간결형 - 핵심만 압축</option>
                                                <option value="narrative">서술형 - 자연스러운 글 형태</option>
                                                <option value="report">보고서형 - 주제/내용/결론 구조</option>
                                                <option value="bullet">핵심 요점형 - 불릿 포인트 목록</option>
                                            </select>
                                        </div>

                                        <!-- 스타일 미리보기 -->
                                        <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
                                            <p class="text-xs font-medium text-gray-600 mb-1.5">미리보기:</p>
                                            <p class="text-xs text-gray-500 whitespace-pre-line"
                                               x-text="getSummaryStylePreview(formData.ref_summary_style)"></p>
                                        </div>
                                    </div>

                                    <!-- 4. 알고리즘 요약 상세 설정 -->
                                    <div x-show="formData.ref_summary_method === 'algorithm'" x-transition class="space-y-4 pl-1">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">알고리즘 유형</label>
                                            <select x-model="formData.ref_algorithm_type"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                <option value="textrank">TextRank - 핵심 문장 추출 (추천)</option>
                                                <option value="frequency">빈도 기반 - 키워드 빈도가 높은 문장</option>
                                                <option value="position">위치 기반 - 도입부 + 결론부 추출</option>
                                            </select>
                                            <p class="mt-1 text-xs text-gray-400">알고리즘 요약은 AI 비용이 발생하지 않습니다</p>
                                        </div>
                                    </div>

                                    <!-- 5. 요약 최대 글자수 (AI/알고리즘 공통) -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">요약 최대 글자수</label>
                                        <div class="flex items-center gap-3">
                                            <input type="number"
                                                   x-model.number="formData.ref_max_length"
                                                   min="200" max="2000" step="100"
                                                   class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent text-sm">
                                            <span class="text-sm text-gray-500">자</span>
                                            <p class="text-xs text-gray-400">200~2000</p>
                                        </div>
                                    </div>

                                    <!-- 참조자료 삽입 형식 안내 -->
                                    <div class="p-3 bg-blue-50 rounded-lg">
                                        <p class="text-xs text-blue-700">
                                            &#128161; 수집된 참조자료는 글 생성 시 자동으로 프롬프트에 삽입됩니다:<br>
                                            <code class="bg-blue-100 px-1 rounded">---[참조자료] 참조1: 요약내용... ---</code>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
`;
}

/** 요약 스타일 미리보기 텍스트 반환 */
function getSummaryStylePreview(style) {
    const previews = {
        concise: '예시: "이 문서는 블로그 SEO 전략에 대해 다룹니다. 핵심 키워드 배치, 메타 태그 최적화, 내부 링크 구조화가 주요 내용이며 지속적인 콘텐츠 업데이트가 검색 순위 향상의 핵심입니다."',
        narrative: '예시: "블로그 SEO 전략은 검색엔진 최적화의 핵심입니다. 먼저 키워드 리서치를 통해 타겟 키워드를 선정하고, 이를 자연스럽게 콘텐츠에 배치합니다. 메타 태그를 최적화하고 내부 링크를 구조화하면 검색 엔진이 콘텐츠를 더 잘 이해할 수 있습니다..."',
        report: '예시:\n1) 핵심 주제: 블로그 SEO 전략과 검색엔진 최적화\n2) 주요 내용: 키워드 배치, 메타 태그 최적화, 내부 링크 구조화\n3) 시사점: 지속적인 콘텐츠 업데이트와 기술적 SEO가 검색 순위 향상의 핵심',
        bullet: '예시:\n- 핵심 키워드를 제목과 첫 문단에 자연스럽게 배치\n- 메타 디스크립션을 150자 내외로 명확하게 작성\n- 내부 링크를 3-5개 포함하여 사이트 구조 강화\n- 이미지에 적절한 alt 텍스트 추가\n- 모바일 최적화 및 페이지 로딩 속도 개선'
    };
    return previews[style] || previews['concise'];
}

// 전역 노출
window.getGenerateModuleFormTemplate = getGenerateModuleFormTemplate;
window.getSummaryStylePreview = getSummaryStylePreview;
