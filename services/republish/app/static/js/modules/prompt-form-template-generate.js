/** 프롬프트 모듈 - 내부링크 설정 + 치환 설정 섹션 템플릿 */

/** 내부링크 설정 섹션 */
function getPromptInternalLinksSection() {
    return `
                            <!-- 내부링크 설정 -->
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                        🔗 내부링크 설정
                                    </h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox"
                                               x-model="promptModule.internalLinks.enabled"
                                               class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>

                                <div x-show="promptModule.internalLinks.enabled" x-transition class="space-y-4 p-4 bg-teal-50 rounded-lg">
                                    <!-- 유사도 임계값 -->
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">
                                            유사도 임계값: <span class="text-teal-600" x-text="promptModule.internalLinks.similarityThreshold + '%'"></span>
                                        </label>
                                        <input type="range"
                                               x-model.number="promptModule.internalLinks.similarityThreshold"
                                               min="50" max="100" step="5"
                                               class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer">
                                        <div class="flex justify-between text-xs text-gray-500 mt-1">
                                            <span>느슨 (50%)</span>
                                            <span>엄격 (100%)</span>
                                        </div>
                                    </div>

                                    <!-- 서론 링크 설정 -->
                                    <div class="grid grid-cols-2 gap-4">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">서론 링크 개수</label>
                                            <input type="number"
                                                   x-model.number="promptModule.internalLinks.introCount"
                                                   min="1" max="5"
                                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                            <p class="mt-0.5 text-xs text-gray-400">1~5개</p>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">서론 링크 유형</label>
                                            <select x-model="promptModule.internalLinks.introLinkType"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                <option value="button">버튼형</option>
                                                <option value="normal">일반 링크</option>
                                            </select>
                                        </div>
                                    </div>

                                    <!-- 본론 링크 설정 -->
                                    <div class="grid grid-cols-2 gap-4">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                                본론 링크 개수
                                                <span class="text-xs text-gray-400">(0이면 비활성)</span>
                                            </label>
                                            <input type="number"
                                                   x-model.number="promptModule.internalLinks.bodyCount"
                                                   min="0" max="3"
                                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                            <p class="mt-0.5 text-xs text-gray-400">0~3개 (섹션당)</p>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">본론 링크 유형</label>
                                            <select x-model="promptModule.internalLinks.bodyLinkType"
                                                    :disabled="promptModule.internalLinks.bodyCount === 0"
                                                    :class="promptModule.internalLinks.bodyCount === 0 ? 'opacity-50' : ''"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                <option value="quote">인용형 (&gt; 관련 글)</option>
                                                <option value="normal">일반 링크</option>
                                            </select>
                                        </div>
                                    </div>

                                    <!-- 결론 링크 설정 -->
                                    <div class="grid grid-cols-2 gap-4">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">결론 링크 개수</label>
                                            <input type="number"
                                                   x-model.number="promptModule.internalLinks.conclusionCount"
                                                   min="1" max="10"
                                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                            <p class="mt-0.5 text-xs text-gray-400">1~10개</p>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">결론 리스트 스타일</label>
                                            <select x-model="promptModule.internalLinks.conclusionListStyle"
                                                    class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-sm">
                                                <option value="dash">대시 (-)</option>
                                                <option value="number">번호 (1.)</option>
                                                <option value="none">없음</option>
                                            </select>
                                        </div>
                                    </div>

                                    <!-- 안내 -->
                                    <div class="p-3 bg-teal-100 rounded-lg">
                                        <p class="text-xs text-teal-800">
                                            💡 내부링크는 같은 블로그의 기존 발행 글 중 유사한 제목의 글을 자동으로 찾아 삽입합니다.
                                            서론에는 관련 글 버튼/링크, 결론에는 추천 글 목록이 추가됩니다.
                                        </p>
                                    </div>
                                </div>
                            </div>`;
}

/** 텍스트 치환 설정 섹션 */
function getPromptSubstitutionSection() {
    return `
                            <!-- 치환 설정 -->
                            <div class="space-y-4">
                                <div class="flex items-center justify-between">
                                    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                        🔄 텍스트 치환
                                    </h3>
                                    <label class="flex items-center cursor-pointer">
                                        <input type="checkbox"
                                               x-model="promptModule.textReplaceEnabled"
                                               class="w-4 h-4 text-amber-600 rounded focus:ring-amber-500">
                                        <span class="ml-2 text-sm text-gray-600">활성화</span>
                                    </label>
                                </div>

                                <div x-show="promptModule.textReplaceEnabled" x-transition
                                     class="p-4 bg-amber-50 rounded-lg">
                                    <p class="text-sm text-amber-800">
                                        실제 치환 규칙(HTML 태그, CSS 클래스, 텍스트 대체)은
                                        <a href="/blogs" class="text-blue-600 hover:underline font-medium">블로그 설정</a>에서 관리됩니다.
                                    </p>
                                    <p class="text-xs text-amber-700 mt-2">
                                        이 옵션을 활성화하면 글 생성 후 블로그별 치환 규칙이 자동으로 적용됩니다.
                                    </p>
                                </div>
                            </div>`;
}

// 전역 노출
window.getPromptInternalLinksSection = getPromptInternalLinksSection;
window.getPromptSubstitutionSection = getPromptSubstitutionSection;
