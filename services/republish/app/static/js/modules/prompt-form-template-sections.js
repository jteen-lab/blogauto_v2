/** 프롬프트 모듈 폼 섹션 템플릿 - 참조자료 수집 + 글 생성 프롬프트 */

/** 참조자료 수집 설정 섹션 */
function getPromptReferenceSection() {
    return `
                            <!-- 3. 참조자료 수집 설정 -->
                            <div class="space-y-4">
                                <div>
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                        🔍 참조자료 수집 설정
                                    </h3>
                                </div>

                                <div class="space-y-5 p-4 bg-orange-50 rounded-lg">
                                    <!-- 프로세스 설명 -->
                                    <div class="p-3 bg-orange-100 rounded-lg">
                                        <p class="text-sm text-orange-800 font-medium mb-2">참조자료 수집 프로세스:</p>
                                        <ol class="text-xs text-orange-700 space-y-1 list-decimal list-inside">
                                            <li>제목으로 네이버 웹문서 검색</li>
                                            <li>검색 결과 페이지 크롤링 (실패 도메인 자동 제외)</li>
                                            <li>AI 또는 알고리즘으로 핵심 내용 요약</li>
                                            <li>요약된 참조자료를 글 생성에 활용</li>
                                        </ol>
                                    </div>

                                    <!-- 수량 설정 (3열 그리드) -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-3">수집 수량</label>
                                        <div class="grid grid-cols-3 gap-3">
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">최대 검색 수</label>
                                                <input type="number"
                                                       x-model.number="promptModule.reference.maxSearch"
                                                       min="10" max="100"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">10~100</p>
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">크롤링 목표</label>
                                                <input type="number"
                                                       x-model.number="promptModule.reference.crawlTarget"
                                                       min="3" max="30"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">3~30</p>
                                            </div>
                                            <div>
                                                <label class="block text-xs text-gray-500 mb-1">요약 선택 수</label>
                                                <input type="number"
                                                       x-model.number="promptModule.reference.summaryCount"
                                                       min="1" max="10"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-sm">
                                                <p class="mt-0.5 text-xs text-gray-400">1~10</p>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- 비용 경고 -->
                                    <div x-show="promptModule.reference.summaryCount > 5" x-transition
                                         class="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                        <p class="text-sm text-amber-800">
                                            ⚠️ <span class="font-medium">비용 주의:</span>
                                            요약 개수가 많으면 AI API 토큰 사용량이 증가합니다.
                                            비용 절감을 위해 '텍스트 알고리즘' 요약 방법을 선택하세요.
                                        </p>
                                    </div>

                                    <!-- 요약 방법 선택 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-3">요약 방법</label>
                                        <div class="grid grid-cols-2 gap-3">
                                            <label class="flex items-center p-3 border-2 rounded-lg cursor-pointer transition-colors"
                                                   :class="promptModule.reference.summaryMethod === 'ai'
                                                       ? 'bg-purple-50 border-purple-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                <input type="radio" value="ai"
                                                       x-model="promptModule.reference.summaryMethod"
                                                       class="w-4 h-4 text-purple-600 focus:ring-purple-500">
                                                <div class="ml-3">
                                                    <span class="text-sm font-medium">🤖 AI 요약</span>
                                                    <p class="text-xs text-gray-500">고품질, API 비용 발생</p>
                                                </div>
                                            </label>
                                            <label class="flex items-center p-3 border-2 rounded-lg cursor-pointer transition-colors"
                                                   :class="promptModule.reference.summaryMethod === 'algorithm'
                                                       ? 'bg-green-50 border-green-400' : 'bg-white border-gray-200 hover:border-gray-300'">
                                                <input type="radio" value="algorithm"
                                                       x-model="promptModule.reference.summaryMethod"
                                                       class="w-4 h-4 text-green-600 focus:ring-green-500">
                                                <div class="ml-3">
                                                    <span class="text-sm font-medium">⚡ 텍스트 알고리즘</span>
                                                    <p class="text-xs text-gray-500">빠르고 비용 없음</p>
                                                </div>
                                            </label>
                                        </div>
                                    </div>

                                    <!-- AI 요약 상세 설정 -->
                                    <div x-show="promptModule.reference.summaryMethod === 'ai'" x-transition class="space-y-4 pl-1">
                                        <p class="text-xs text-gray-400">AI 서비스 및 모델은 블로그 설정 > AI 탭에서 설정합니다.</p>

                                        <!-- 요약 스타일 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">요약 스타일</label>
                                            <select x-model="promptModule.reference.summaryStyle"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm">
                                                <option value="concise">간결형 - 핵심만 압축</option>
                                                <option value="narrative">서술형 - 자연스러운 글 형태</option>
                                                <option value="report">보고서형 - 주제/내용/결론 구조</option>
                                                <option value="bullet">핵심 요점형 - 불릿 포인트 목록</option>
                                            </select>
                                        </div>
                                    </div>

                                    <!-- 알고리즘 요약 상세 설정 -->
                                    <div x-show="promptModule.reference.summaryMethod === 'algorithm'" x-transition class="space-y-4 pl-1">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">알고리즘 유형</label>
                                            <select x-model="promptModule.reference.algorithmType"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 text-sm">
                                                <option value="textrank">TextRank - 핵심 문장 추출 (추천)</option>
                                                <option value="frequency">빈도 기반 - 키워드 빈도가 높은 문장</option>
                                                <option value="position">위치 기반 - 도입부 + 결론부 추출</option>
                                            </select>
                                            <p class="mt-1 text-xs text-gray-400">알고리즘 요약은 AI 비용이 발생하지 않습니다</p>
                                        </div>
                                    </div>

                                    <!-- 요약 최대 글자수 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">요약 최대 글자수</label>
                                        <div class="flex items-center gap-3">
                                            <input type="number"
                                                   x-model.number="promptModule.reference.maxLength"
                                                   min="200" max="2000" step="100"
                                                   class="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 text-sm">
                                            <span class="text-sm text-gray-500">자</span>
                                            <p class="text-xs text-gray-400">200~2000</p>
                                        </div>
                                    </div>

                                    <!-- 참조자료 삽입 안내 -->
                                    <div class="p-3 bg-blue-50 rounded-lg">
                                        <p class="text-xs text-blue-700">
                                            💡 수집된 참조자료는 글 생성 시 자동으로 프롬프트에 삽입됩니다:<br>
                                            <code class="bg-blue-100 px-1 rounded">---[참조자료] 참조1: 요약내용... ---</code>
                                        </p>
                                    </div>
                                </div>
                            </div>`;
}

/** 글 생성 프롬프트 섹션 */
function getPromptContentGenSection() {
    return `
                            <!-- 4. 글 생성 프롬프트 섹션 -->
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                        ✨ 글 생성 프롬프트
                                    </h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox"
                                               x-model="promptModule.contentGeneration.enabled"
                                               class="w-4 h-4 text-purple-600 rounded focus:ring-purple-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>

                                <div x-show="promptModule.contentGeneration.enabled" x-transition class="space-y-4 p-4 bg-purple-50 rounded-lg">
                                    <!-- AI 모델 안내 -->
                                    <p class="text-xs text-gray-400">AI 서비스 및 모델은 블로그 설정 > AI 탭에서 설정합니다.</p>

                                    <!-- Temperature 슬라이더 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">
                                            창의성 (Temperature): <span class="text-purple-600" x-text="promptModule.contentGeneration.temperature"></span>
                                        </label>
                                        <input type="range"
                                               x-model.number="promptModule.contentGeneration.temperature"
                                               min="0" max="2" step="0.1"
                                               class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer">
                                        <div class="flex justify-between text-xs text-gray-500 mt-1">
                                            <span>정확한 (0)</span>
                                            <span>창의적 (2)</span>
                                        </div>
                                    </div>

                                    <!-- Max Tokens -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">최대 토큰</label>
                                        <input type="number"
                                               x-model.number="promptModule.contentGeneration.maxTokens"
                                               min="100" max="128000"
                                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                    </div>

                                    <!-- 시스템 프롬프트 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">시스템 프롬프트</label>
                                        <textarea x-model="promptModule.contentGeneration.systemPrompt"
                                                  rows="3"
                                                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm font-mono"
                                                  placeholder="당신은 전문 블로그 작성자입니다..."></textarea>
                                    </div>

                                    <!-- 사용자 프롬프트 템플릿 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">
                                            사용자 프롬프트 템플릿
                                            <span class="text-xs text-gray-500">(변수: {title}, {keywords}, {category}, {reference_materials})</span>
                                        </label>
                                        <textarea x-model="promptModule.contentGeneration.userPromptTemplate"
                                                  rows="4"
                                                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm font-mono"
                                                  placeholder="제목: {title}

위 제목으로 블로그 글을 작성해주세요.
카테고리: {category}
키워드: {keywords}"></textarea>
                                    </div>

                                    <!-- 재발행 리뉴얼 프롬프트 -->
                                    <div class="border-t border-purple-200 pt-4">
                                        <label class="block text-sm font-medium text-gray-700 mb-2">재발행 리뉴얼 프롬프트</label>
                                        <select x-model="promptModule.contentGeneration.renewalMode"
                                                class="w-full sm:w-80 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm">
                                            <option value="inherit">생성 프롬프트 승계 (그대로 사용)</option>
                                            <option value="new">새 프롬프트 (리뉴얼 전용으로 교체)</option>
                                            <option value="additional">추가 프롬프트 (생성 프롬프트 + 지침 결합)</option>
                                        </select>
                                        <p class="text-xs text-gray-500 mt-1">재발행 리뉴얼 시 글 생성에 사용할 프롬프트 방식입니다.</p>
                                        <div x-show="promptModule.contentGeneration.renewalMode !== 'inherit'" x-transition class="mt-3">
                                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                                <span x-text="promptModule.contentGeneration.renewalMode === 'new' ? '리뉴얼 전용 프롬프트' : '추가 지침'"></span>
                                                <span class="text-xs text-gray-500">(변수: {title}, {category}, {keywords}, {existing_content})</span>
                                            </label>
                                            <textarea x-model="promptModule.contentGeneration.renewalText"
                                                      rows="4"
                                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 text-sm font-mono"
                                                      placeholder="예) 기존 글의 정보를 보존하면서 최신 정보나 변경된 내용을 추가해 더 풍부하게 확장해 주세요."></textarea>
                                            <p class="text-xs text-gray-400 mt-1">추가 프롬프트: 기존 글 본문이 자동 첨부되어 "보존 + 확장" 작성이 됩니다. 새 프롬프트: {existing_content} 변수로 기존 글을 넣을 수 있습니다.</p>
                                        </div>
                                    </div>

                                    ${typeof window !== 'undefined' && window.getPromptBuilderEmbeddedHTML ? window.getPromptBuilderEmbeddedHTML() : ''}

                                    <!-- 고급 설정 (접기/펼치기) -->
                                    <div class="border-t border-purple-200 pt-4">
                                        <button type="button"
                                                @click="promptModule.contentGeneration.showAdvanced = !promptModule.contentGeneration.showAdvanced"
                                                class="flex items-center gap-2 text-sm text-purple-600 hover:text-purple-800">
                                            <svg class="w-4 h-4 transition-transform"
                                                 :class="promptModule.contentGeneration.showAdvanced ? 'rotate-90' : ''"
                                                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                                            </svg>
                                            고급 설정
                                        </button>

                                        <div x-show="promptModule.contentGeneration.showAdvanced" x-transition class="mt-4 grid grid-cols-2 gap-4">
                                            <!-- Top P (다양성 조절) -->
                                            <div>
                                                <label class="block text-sm font-medium text-gray-700 mb-2">다양성 조절 (Top P)</label>
                                                <input type="number"
                                                       x-model.number="promptModule.contentGeneration.topP"
                                                       min="0" max="1" step="0.05"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                <div class="flex justify-between text-xs text-gray-500 mt-1">
                                                    <span>일관적 (0)</span>
                                                    <span>다양함 (1)</span>
                                                </div>
                                            </div>

                                            <!-- Frequency Penalty (OpenAI) -->
                                            <div x-show="promptModule.contentGeneration.provider === 'openai'">
                                                <label class="block text-sm font-medium text-gray-700 mb-2">단어 반복 방지 (Frequency)</label>
                                                <input type="number"
                                                       x-model.number="promptModule.contentGeneration.frequencyPenalty"
                                                       min="-2" max="2" step="0.1"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                <div class="flex justify-between text-xs text-gray-500 mt-1">
                                                    <span>반복 허용 (-2)</span>
                                                    <span>반복 방지 (2)</span>
                                                </div>
                                            </div>

                                            <!-- Presence Penalty (OpenAI) -->
                                            <div x-show="promptModule.contentGeneration.provider === 'openai'">
                                                <label class="block text-sm font-medium text-gray-700 mb-2">주제 반복 방지 (Presence)</label>
                                                <input type="number"
                                                       x-model.number="promptModule.contentGeneration.presencePenalty"
                                                       min="-2" max="2" step="0.1"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                <div class="flex justify-between text-xs text-gray-500 mt-1">
                                                    <span>반복 허용 (-2)</span>
                                                    <span>새 주제 유도 (2)</span>
                                                </div>
                                            </div>

                                            <!-- Top K (Claude/Gemini) -->
                                            <div x-show="promptModule.contentGeneration.provider !== 'openai'">
                                                <label class="block text-sm font-medium text-gray-700 mb-2">후보 단어 수 (Top K)</label>
                                                <input type="number"
                                                       x-model.number="promptModule.contentGeneration.topK"
                                                       min="1" max="100"
                                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500">
                                                <div class="flex justify-between text-xs text-gray-500 mt-1">
                                                    <span>결정적 (1)</span>
                                                    <span>다양함 (100)</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>`;
}

// 전역 노출
window.getPromptReferenceSection = getPromptReferenceSection;
window.getPromptContentGenSection = getPromptContentGenSection;
