/** 생성 모듈 폼 HTML 템플릿 - list.js의 getFullFormTemplate()에서 호출 */
function getGenerateModuleFormTemplate() {
    return `
                        <!-- 생성 모듈 설정: 내부링크 + 치환 -->
                        <div x-show="formData.type_code === 'generate'" class="space-y-6">
                            <!-- 내부링크 설정 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    내부링크 설정
                                </h3>

                                <div class="border border-green-200 rounded-lg overflow-hidden">
                                    <!-- 활성화 토글 -->
                                    <div class="flex items-center p-3 bg-green-50 border-b border-green-200 cursor-pointer"
                                         @click="formData.il_enabled = !formData.il_enabled">
                                        <input type="checkbox"
                                               :checked="formData.il_enabled"
                                               class="text-green-600 focus:ring-green-500 h-4 w-4 rounded pointer-events-none">
                                        <span class="ml-3 text-sm font-medium text-gray-700">내부링크 자동 삽입</span>
                                    </div>

                                    <!-- 상세 설정 (활성화 시) -->
                                    <div x-show="formData.il_enabled" x-transition class="p-4 space-y-4">
                                        <div class="p-3 bg-green-50 rounded-lg">
                                            <p class="text-sm text-green-800 font-medium mb-2">내부링크 삽입 프로세스:</p>
                                            <ol class="text-xs text-green-700 space-y-1 list-decimal list-inside">
                                                <li>대상 블로그의 기존 발행글 목록을 조회</li>
                                                <li>유사 제목 글을 서론 뒤에 삽입 (버튼/일반 선택)</li>
                                                <li>각 본론 섹션 제목과 유사한 글을 섹션 뒤에 삽입</li>
                                                <li>랜덤 글을 결론 뒤에 목록 형태로 삽입</li>
                                            </ol>
                                        </div>

                                        <!-- 유사도 임계값 -->
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">유사도 임계값</label>
                                            <div class="flex items-center gap-3">
                                                <input type="range"
                                                       x-model.number="formData.il_similarity_threshold"
                                                       min="50" max="100" step="5"
                                                       class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-green-600">
                                                <span class="w-14 text-center text-sm font-medium text-green-700 bg-green-50 rounded px-2 py-1"
                                                      x-text="formData.il_similarity_threshold + '%'"></span>
                                            </div>
                                            <p class="mt-1 text-xs text-gray-500">권장: 75%</p>
                                        </div>

                                        <!-- 서론 링크 -->
                                        <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                            <span class="text-sm font-medium text-gray-800">서론 뒤 링크</span>
                                            <div class="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 수</label>
                                                    <input type="number"
                                                           x-model.number="formData.il_intro_count"
                                                           min="1" max="5"
                                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                    <p class="mt-0.5 text-xs text-gray-400">1~5개</p>
                                                </div>
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 타입</label>
                                                    <select x-model="formData.il_intro_link_type"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                        <option value="button">버튼 링크</option>
                                                        <option value="normal">일반 링크</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        <!-- 본론 섹션 안내 -->
                                        <div class="border border-gray-200 rounded-lg p-3">
                                            <span class="text-sm font-medium text-gray-800">본론 섹션 링크</span>
                                            <p class="mt-1 text-xs text-gray-500">
                                                각 본문 섹션 제목과 유사한 기존 글이 있을 경우 자동 삽입 (섹션당 1개)
                                            </p>
                                        </div>

                                        <!-- 결론 링크 -->
                                        <div class="border border-gray-200 rounded-lg p-3 space-y-3">
                                            <span class="text-sm font-medium text-gray-800">결론 뒤 링크</span>
                                            <div class="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">링크 수</label>
                                                    <input type="number"
                                                           x-model.number="formData.il_conclusion_count"
                                                           min="1" max="10"
                                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                    <p class="mt-0.5 text-xs text-gray-400">1~10개</p>
                                                </div>
                                                <div>
                                                    <label class="block text-xs text-gray-500 mb-1">리스트 스타일</label>
                                                    <select x-model="formData.il_conclusion_list_style"
                                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent text-sm">
                                                        <option value="dash">기호 리스트 (- )</option>
                                                        <option value="number">번호 리스트 (1. )</option>
                                                        <option value="none">리스트 없음</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- 치환 설정 -->
                            <div class="space-y-4">
                                <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
                                    치환 설정
                                </h3>

                                <div class="border border-purple-200 rounded-lg overflow-hidden">
                                    <!-- 마크다운 → HTML 변환 (항상 적용) -->
                                    <div class="flex items-center p-3 border-b border-purple-100">
                                        <input type="checkbox" checked disabled
                                               class="text-purple-600 h-4 w-4 rounded opacity-60">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">마크다운 → HTML 변환</span>
                                            <span class="ml-2 text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">항상 적용</span>
                                        </div>
                                    </div>
                                    <div class="px-4 py-2 bg-gray-50 border-b border-purple-100">
                                        <p class="text-xs text-gray-500">
                                            생성된 마크다운 글을 HTML로 변환합니다. (헤딩, 볼드, 리스트, 링크 등)
                                        </p>
                                    </div>

                                    <!-- HTML 태그 치환 (항상 적용) -->
                                    <div class="flex items-center p-3 border-b border-purple-100">
                                        <input type="checkbox" checked disabled
                                               class="text-purple-600 h-4 w-4 rounded opacity-60">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">HTML 태그 치환</span>
                                            <span class="ml-2 text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">항상 적용</span>
                                        </div>
                                    </div>
                                    <div class="px-4 py-2 bg-gray-50 border-b border-purple-100">
                                        <p class="text-xs text-gray-500">
                                            블로그 카드 > 치환자 탭의 <strong>HTML 태그</strong> 설정에 따라 태그를 변환합니다.
                                        </p>
                                        <p class="text-xs text-gray-400 mt-1">
                                            예: h1 → h2, h2 → h3 (블로그별 개별 설정)
                                        </p>
                                    </div>

                                    <!-- CSS 클래스 치환 (항상 적용) -->
                                    <div class="flex items-center p-3 border-b border-purple-100">
                                        <input type="checkbox" checked disabled
                                               class="text-purple-600 h-4 w-4 rounded opacity-60">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">CSS 클래스 치환</span>
                                            <span class="ml-2 text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">항상 적용</span>
                                        </div>
                                    </div>
                                    <div class="px-4 py-2 bg-gray-50 border-b border-purple-100">
                                        <p class="text-xs text-gray-500">
                                            블로그 카드 > 치환자 탭의 <strong>CSS 클래스</strong> 설정에 따라 클래스를 추가합니다.
                                        </p>
                                        <p class="text-xs text-gray-400 mt-1">
                                            예: p 태그에 "content-text" 클래스 추가 (블로그별 개별 설정)
                                        </p>
                                    </div>

                                    <!-- 텍스트 치환 (토글 가능) -->
                                    <div class="flex items-center p-3 cursor-pointer"
                                         :class="formData.text_replace_enabled ? 'border-b border-purple-100' : ''"
                                         @click="formData.text_replace_enabled = !formData.text_replace_enabled">
                                        <input type="checkbox"
                                               :checked="formData.text_replace_enabled"
                                               class="text-purple-600 focus:ring-purple-500 h-4 w-4 rounded pointer-events-none">
                                        <div class="ml-3">
                                            <span class="text-sm font-medium text-gray-700">텍스트 치환</span>
                                            <span class="ml-2 text-xs"
                                                  :class="formData.text_replace_enabled ? 'text-green-600 bg-green-50' : 'text-gray-500 bg-gray-100'"
                                                  x-text="formData.text_replace_enabled ? '활성' : '비활성'"
                                                  class="px-1.5 py-0.5 rounded"></span>
                                        </div>
                                    </div>
                                    <div x-show="formData.text_replace_enabled" x-transition
                                         class="px-4 py-3 bg-gray-50">
                                        <p class="text-xs text-gray-500">
                                            블로그 카드 > 치환자 탭의 <strong>텍스트 치환</strong> 설정에 따라 텍스트를 치환합니다.
                                        </p>
                                        <p class="text-xs text-gray-400 mt-1">
                                            예: "예를 들어" → "예시로" (블로그별 개별 설정)
                                        </p>
                                        <div class="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-700 flex items-start gap-1.5">
                                            <svg class="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                                            </svg>
                                            <span>블로그 카드의 치환자 탭에서 텍스트 치환 값을 먼저 설정해야 합니다. 저장된 값이 없으면 치환이 적용되지 않습니다.</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
`;
}

// 전역 노출
window.getGenerateModuleFormTemplate = getGenerateModuleFormTemplate;
