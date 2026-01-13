# Phase 1-4: 플로우 1회 실행 UI

> **작업 유형**: UI 추가  
> **예상 시간**: 1-2시간  
> **우선순위**: P0 (Critical)  
> **선행 작업**: Phase 1-3 API 완료

---

## 📋 작업 개요

플로우 카드에 1회 실행 버튼을 추가하고, 실행 결과를 팝업으로 표시합니다.

### 목표
- 플로우 카드에 [▶] 실행 버튼 추가
- 클릭 시 API 호출 → 결과 팝업 표시
- 실행 중 로딩 표시

---

## 📁 수정할 파일

### 1. app/templates/flows/_card.html

플로우 카드에 실행 버튼 추가:

```html
<!-- 카드 헤더 부분에 실행 버튼 추가 -->
<div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
        <!-- 기존 내용 -->
    </div>
    
    <!-- 🆕 실행 버튼 -->
    <button 
        @click.stop="executeFlow({{ flow.id }})"
        class="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
        title="1회 실행 (테스트)"
        :disabled="executingFlowId === {{ flow.id }}"
    >
        <template x-if="executingFlowId === {{ flow.id }}">
            <!-- 로딩 스피너 -->
            <svg class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        </template>
        <template x-if="executingFlowId !== {{ flow.id }}">
            <!-- 재생 아이콘 -->
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
        </template>
    </button>
</div>
```

### 2. app/static/js/flows/list.js

실행 함수 및 결과 처리 추가:

```javascript
// Alpine.js 컴포넌트에 추가할 데이터 및 메서드

// 데이터 추가
executingFlowId: null,
executeResult: null,
showExecuteResult: false,

// 메서드 추가
async executeFlow(flowId) {
    if (this.executingFlowId) return;
    
    this.executingFlowId = flowId;
    this.executeResult = null;
    
    try {
        const response = await fetch(`/api/v1/flows/${flowId}/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        this.executeResult = result;
        this.showExecuteResult = true;
        
        // 성공/실패 토스트
        if (result.success) {
            this.showToast(`플로우 실행 완료 (${result.duration_ms}ms)`, 'success');
        } else {
            this.showToast(`플로우 실행 실패: ${result.error}`, 'error');
        }
        
    } catch (error) {
        console.error('플로우 실행 오류:', error);
        this.showToast(`실행 오류: ${error.message}`, 'error');
    } finally {
        this.executingFlowId = null;
    }
},

closeExecuteResult() {
    this.showExecuteResult = false;
    this.executeResult = null;
}
```

### 3. app/templates/flows/list.html

실행 결과 모달 추가:

```html
<!-- 플로우 실행 결과 모달 -->
<div 
    x-show="showExecuteResult" 
    x-cloak
    class="fixed inset-0 z-50 overflow-y-auto"
    @keydown.escape.window="closeExecuteResult()"
>
    <!-- 백드롭 -->
    <div 
        class="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        @click="closeExecuteResult()"
    ></div>
    
    <!-- 모달 컨텐츠 -->
    <div class="flex min-h-full items-center justify-center p-4">
        <div 
            class="relative bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden"
            @click.stop
        >
            <!-- 헤더 -->
            <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between"
                 :class="executeResult?.success ? 'bg-green-50' : 'bg-red-50'">
                <div class="flex items-center gap-3">
                    <template x-if="executeResult?.success">
                        <svg class="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    </template>
                    <template x-if="!executeResult?.success">
                        <svg class="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    </template>
                    <h3 class="text-lg font-semibold" 
                        :class="executeResult?.success ? 'text-green-800' : 'text-red-800'"
                        x-text="executeResult?.success ? '실행 완료' : '실행 실패'">
                    </h3>
                </div>
                <button @click="closeExecuteResult()" class="text-gray-400 hover:text-gray-600">
                    <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            
            <!-- 본문 -->
            <div class="px-6 py-4 overflow-y-auto max-h-[60vh]">
                <!-- 요약 정보 -->
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div class="bg-gray-50 rounded-lg p-3">
                        <div class="text-xs text-gray-500">플로우</div>
                        <div class="font-medium" x-text="executeResult?.flow_name"></div>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                        <div class="text-xs text-gray-500">실행 시간</div>
                        <div class="font-medium" x-text="(executeResult?.duration_ms || 0) + 'ms'"></div>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                        <div class="text-xs text-gray-500">처리된 아이템</div>
                        <div class="font-medium" x-text="executeResult?.total_items_processed || 0"></div>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-3">
                        <div class="text-xs text-gray-500">실행 ID</div>
                        <div class="font-medium text-xs truncate" x-text="executeResult?.execution_id"></div>
                    </div>
                </div>
                
                <!-- 에러 메시지 -->
                <template x-if="executeResult?.error">
                    <div class="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                        <div class="text-sm text-red-800" x-text="executeResult.error"></div>
                    </div>
                </template>
                
                <!-- 노드별 실행 결과 -->
                <div class="mt-4">
                    <h4 class="text-sm font-semibold text-gray-700 mb-2">노드별 실행 결과</h4>
                    <div class="space-y-2">
                        <template x-for="(node, index) in (executeResult?.node_results || [])" :key="index">
                            <div class="flex items-center justify-between bg-gray-50 rounded-lg p-3">
                                <div class="flex items-center gap-2">
                                    <span class="text-xs text-gray-400" x-text="index + 1"></span>
                                    <span class="font-medium text-sm" x-text="node.module_name"></span>
                                </div>
                                <div class="flex items-center gap-4 text-xs">
                                    <span class="text-gray-500">
                                        <span x-text="node.items_in"></span> → <span x-text="node.items_out"></span>
                                    </span>
                                    <span class="text-gray-500" x-text="node.execution_time_ms + 'ms'"></span>
                                    <span :class="node.success ? 'text-green-600' : 'text-red-600'"
                                          x-text="node.success ? '✓' : '✗'"></span>
                                </div>
                            </div>
                        </template>
                    </div>
                </div>
            </div>
            
            <!-- 푸터 -->
            <div class="px-6 py-4 border-t border-gray-200 bg-gray-50">
                <button 
                    @click="closeExecuteResult()"
                    class="w-full px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition-colors"
                >
                    닫기
                </button>
            </div>
        </div>
    </div>
</div>
```

---

## ✅ 완료 조건

### 필수
- [ ] 플로우 카드에 [▶] 버튼 표시
- [ ] 클릭 시 API 호출
- [ ] 실행 중 로딩 스피너 표시
- [ ] 실행 결과 모달 표시
- [ ] 성공/실패 상태 구분 표시
- [ ] 노드별 실행 결과 표시

### 검증
- [ ] 버튼 클릭 → API 호출 확인
- [ ] 결과 모달 정상 표시
- [ ] ESC 또는 배경 클릭으로 모달 닫기

---

## 🚨 주의사항

1. **기존 UI 유지**: 카드의 다른 기능 영향 없어야 함
2. **@click.stop**: 카드 클릭 이벤트와 분리
3. **토스트 함수**: 기존 showToast 함수 사용 (없으면 추가)

---

## 📝 커밋 메시지

```
feat(ui): 플로우 1회 실행 버튼 및 결과 모달

- 플로우 카드에 [▶] 실행 버튼 추가
- 실행 결과 모달 팝업
- 노드별 실행 상태 표시

관련: DCR-001
```
