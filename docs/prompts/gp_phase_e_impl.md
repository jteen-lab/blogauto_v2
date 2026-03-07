# Growth Profile Phase E: UI 구현

> **Phase**: E (Growth Profile UI)
> **설계 문서**: growth_stage_strategy_plan.md v3.1 Section 9, 10
> **선행 Phase**: A (완료 - 30개 테스트), B (완료 - 27개 테스트), M (완료), C (완료 - 25개 테스트), D (완료 - 26개 테스트)
> **작성일**: 2026-02-22
> **상태**: 구현 대기

---

## 개요

### 목표

1. **Growth Profile 모듈 전용 설정 폼**: schedule_matrix 그리드, 구간 추가/삭제, 모듈별 체크박스 활성화, 독립 간격 설정, 워밍업 설정
2. **프리셋 선택 UI**: 기본 프로파일 3종(aggressive/balanced/conservative) 선택으로 빠르게 시작
3. **블로그별 스테이지 프리뷰**: Flow에 연결된 블로그의 현재 포스트 수 기반 스테이지 매핑 실시간 미리보기
4. **GP 카드/목록 정보 표시**: 모듈 목록에서 GP 설정 요약 (구간 수, 활성 모듈, 워밍업 상태)
5. **Flow 편집 UI 연동**: 성장 전략 배지 + 블로그별 스테이지/간격 표시

### 현재 상태 (Phase A~D 완료)

| 항목 | 상태 | 파일 |
|------|------|------|
| `growth_profile` ModuleType | ✅ 등록됨 | `module_type.py` (`display_order=0`) |
| 기본 프로파일 3종 정의 | ✅ 완료 | `growth_profile_defaults.py` (361줄) |
| GrowthProfileResolver | ✅ 완료 | `growth_profile_resolver.py` (246줄) |
| FlowExecutionContext/StageParams | ✅ 완료 | `flow_execution_context.py` (174줄) |
| Flow 실행 시 GP 디스패치 | ✅ 완료 | `flows_execute.py` |
| publish/republish/generate GP 연동 | ✅ 완료 | `flows_execute.py` |
| FES 블로그 레벨 추적 | ✅ 완료 | `flow_execution_state.py` |
| WarmupManager + Publisher | ✅ 완료 | `warmup_manager.py`, `publisher.py` |
| **GP 전용 설정 UI** | ❌ 미구현 | (현재: JSON 직접 입력 폴백) |
| **Flow UI에서 GP 정보 표시** | ❌ 미구현 | - |
| **대시보드 GP 위젯** | ❌ 미구현 | - |

> **현재 GP 모듈 생성/편집 시**: `_form.html`의 "기타 타입" 분기(1080줄)에 해당되어 **raw JSON 편집기**가 표시됨. 이를 전용 UI로 교체해야 함.

### 핵심 UI 컴포넌트

작업계획서 Section 9 기준 3개 영역:

| 영역 | 설명 | 우선순위 |
|------|------|---------|
| **E-1: GP 모듈 전용 폼** | 프리셋/스케줄/구간/워밍업/프리뷰 (파일 1~7) | 🔴 필수 |
| **E-2: Flow 편집 UI** | 성장 전략 배지 + 블로그별 스테이지 표시 (파일 8) | 🟡 권장 |
| **E-3: 대시보드 위젯** | 성장 단계 현황 + 재고 현황 (파일 9) | 🟢 선택 |

---

## 생성/수정 파일 목록

| # | 파일 경로 | 타입 | 예상 줄 수 | 설명 |
|---|----------|------|-----------|------|
| 1 | `app/templates/modules/_growth_profile_form.html` | 신규 | ~420줄 | GP 전용 폼 HTML (프리셋+스케줄+구간+워밍업+프리뷰) |
| 2 | `app/static/js/modules/growth-profile-form.js` | 신규 | ~450줄 | GP 폼 Alpine.js 로직 (상태관리+검증+계산) |
| 3 | `app/static/js/modules/growth-profile-form-template.js` | 신규 | ~100줄 | list.js 인라인 폼용 간소화 HTML 템플릿 |
| 4 | `app/api/growth_profile.py` | 신규 | ~100줄 | GP 프리셋 조회 + 스테이지 프리뷰 API |
| 5 | `app/templates/modules/_form.html` | 수정 | +5줄 | growth_profile include 추가 |
| 6 | `app/static/js/modules/form.js` | 수정 | +40줄 | GP state 초기화 + 저장 직렬화 |
| 7 | `app/templates/modules/_card.html` | 수정 | +30줄 | GP 카드 요약 표시 |
| 8 | Flow 편집 UI (E-2) | 수정 | +50줄 | 블로그별 스테이지 배지 + 간격 표시 |
| 9 | 대시보드 위젯 (E-3) | 신규 | ~150줄 | 성장 단계 현황 + 재고 차트 |
| 10 | `tests/integration/test_phase_e_gp_ui.py` | 신규 | ~200줄 | API 테스트 + 폼 검증 테스트 |

---

## Phase A~D 완성 파일 (참조용, 수정하지 않음)

| 파일 | import/참조 사항 |
|------|----------------|
| `app/services/generation/growth_profile_defaults.py` | `DEFAULT_PROFILES`, `get_default_profile()`, `get_available_profiles()` - 프리셋 3종 |
| `app/services/generation/growth_profile_resolver.py` | `GrowthProfileResolver.build_execution_context()` - 프리뷰 API에서 호출 |
| `app/services/generation/flow_execution_context.py` | `FlowExecutionContext`, `StageParams`, `ModuleIntervalParams` - 프리뷰 결과 구조 |
| `app/models/module_type.py` | `ModuleType.get_default_types()` - `growth_profile` 타입 (display_order=0) |
| `app/schemas/module.py` | `ModuleCreateRequest`, `ModuleUpdateRequest` - settings JSONB 저장 |
| `app/routers/modules.py` | `POST /modules`, `PUT /modules/{id}` - 기존 CRUD API 활용 |

---

## 파일 1: _growth_profile_form.html (신규)

### 경로: `app/templates/modules/_growth_profile_form.html` (~420줄)
### 설명: Growth Profile 전용 설정 폼 HTML

> **참고**: `_generate_form.html` (168줄)과 `_prompt_form.html` (777줄)의 패턴 따름.
> `_form.html`에서 `{% include "modules/_growth_profile_form.html" %}`로 포함됨.
> Alpine.js `formData` + `gpModule` 객체로 상태 관리.

### 1-1. 프리셋 선택 영역 (~50줄)

```html
<!-- 프리셋 선택 (생성 모드에서만 표시) -->
<div x-show="!isEdit" class="space-y-4 mb-6">
    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
        📋 기본 프로파일 선택
    </h3>
    <p class="text-sm text-gray-500">시작 프로파일을 선택하세요. 선택 후 세부 설정을 수정할 수 있습니다.</p>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <template x-for="preset in gpModule.presets" :key="preset.key">
            <div class="border-2 rounded-lg p-4 cursor-pointer transition-all"
                 :class="gpModule.selectedPreset === preset.key
                     ? 'border-blue-500 bg-blue-50'
                     : 'border-gray-200 hover:border-gray-300'"
                 @click="gpModule.loadPreset(preset.key)">
                <div class="font-medium text-gray-900" x-text="preset.name"></div>
                <p class="text-xs text-gray-500 mt-1" x-text="preset.description"></p>
                <div class="mt-2 flex flex-wrap gap-1">
                    <span class="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600"
                          x-text="preset.stageCount + '단계'"></span>
                    <span class="px-2 py-0.5 text-xs rounded-full"
                          :class="preset.warmupEnabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                          x-text="preset.warmupEnabled ? '워밍업 ON' : '워밍업 OFF'"></span>
                </div>
            </div>
        </template>
    </div>
</div>
```

**프리셋 데이터** (JS에서 정의):
```
presets: [
    { key: "aggressive", name: "공격적 성장", description: "빠른 콘텐츠 축적, 발행 빈도 극대화", stageCount: 3, warmupEnabled: true },
    { key: "balanced", name: "균형 성장", description: "균형 잡힌 생성/발행/재발행 설정", stageCount: 3, warmupEnabled: true },
    { key: "conservative", name: "보수적 운영", description: "안정적 운영, 느린 생성", stageCount: 3, warmupEnabled: false },
]
```

### 1-2. 활성 시간대 (schedule_matrix) (~80줄)

> **기존 코드 재사용**: `_generate_form.html` 74~152줄의 schedule_matrix 그리드를 그대로 차용.
> 차이점: `formData.schedule_matrix` 대신 `gpModule.schedule_matrix` 사용.

```html
<!-- 활성 시간대 스케줄 -->
<div class="space-y-4 mb-6">
    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
        📅 활성 시간대
    </h3>
    <div class="bg-gray-50 rounded-lg p-4">
        <!-- 빠른 설정 버튼 -->
        <div class="flex flex-wrap gap-2 mb-4">
            <button type="button" @click="gpModule.selectAllHours()"
                    class="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded-full hover:bg-blue-200">
                전체 선택
            </button>
            <button type="button" @click="gpModule.clearAllHours()"
                    class="px-3 py-1 text-xs bg-gray-100 text-gray-800 rounded-full hover:bg-gray-200">
                전체 해제
            </button>
            <button type="button" @click="gpModule.selectWeekdayHours()"
                    class="px-3 py-1 text-xs bg-green-100 text-green-800 rounded-full hover:bg-green-200">
                평일 6~21시
            </button>
            <button type="button" @click="gpModule.selectWeekendHours()"
                    class="px-3 py-1 text-xs bg-purple-100 text-purple-800 rounded-full hover:bg-purple-200">
                주말 7~20시
            </button>
        </div>

        <p class="text-xs text-gray-500 mb-3">파란색 = 활성, 회색 = 비활성 | 요일 헤더 클릭으로 전체 선택/해제</p>

        <!-- 7x24 스케줄 그리드 (기존 _generate_form.html 패턴 동일) -->
        <div class="overflow-x-auto">
            <table class="w-full text-xs border-collapse">
                <thead>
                    <tr>
                        <th class="border border-gray-300 bg-gray-100 p-2 text-center w-12">시간</th>
                        <template x-for="(day, dayIdx) in gpModule.days" :key="dayIdx">
                            <th class="border border-gray-300 bg-gray-100 p-2 text-center cursor-pointer hover:bg-gray-200 w-8"
                                @click="gpModule.toggleDay(dayIdx)"
                                x-text="day">
                            </th>
                        </template>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="hour in 24" :key="hour">
                        <tr>
                            <td class="border border-gray-300 bg-gray-50 p-1 text-center font-medium"
                                x-text="String(hour-1).padStart(2, '0') + '시'">
                            </td>
                            <template x-for="(day, dayIdx) in gpModule.days" :key="dayIdx + '-' + hour">
                                <td class="border border-gray-300 p-0">
                                    <button type="button"
                                            class="w-full h-7 border-none cursor-pointer transition-colors duration-150"
                                            :class="gpModule.schedule_matrix[dayIdx][hour-1] ? 'bg-blue-500 hover:bg-blue-600' : 'bg-gray-100 hover:bg-gray-200'"
                                            @click="gpModule.toggleHour(dayIdx, hour-1)">
                                    </button>
                                </td>
                            </template>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>

        <!-- 활성 시간 요약 -->
        <div class="mt-4 p-3 bg-blue-50 rounded-lg">
            <div class="flex items-center justify-between text-sm">
                <span class="text-blue-800 font-medium">
                    활성 시간: <span x-text="gpModule.activeHoursCount"></span>시간/주
                </span>
                <span class="text-blue-600" x-show="gpModule.todayActiveHours > 0">
                    오늘: <span x-text="gpModule.todayActiveHours"></span>시간
                </span>
            </div>
        </div>
    </div>
</div>
```

### 1-3. 지터(랜덤 변동) 설정 (~25줄)

```html
<!-- 지터(랜덤 변동) 설정 -->
<div class="space-y-4 mb-6">
    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
        🎲 간격 변동 (Jitter)
    </h3>
    <div class="p-4 bg-gray-50 rounded-lg">
        <label class="flex items-center cursor-pointer mb-3">
            <input type="checkbox"
                   x-model="gpModule.jitter.enabled"
                   class="rounded text-blue-600 focus:ring-blue-500 h-4 w-4">
            <span class="ml-2 text-sm text-gray-700">간격 변동 사용</span>
            <span class="ml-2 text-xs text-gray-400">(봇 탐지 회피를 위해 간격에 랜덤 변동 적용)</span>
        </label>
        <div x-show="gpModule.jitter.enabled" class="flex items-center gap-4 flex-wrap">
            <div class="flex items-center gap-2">
                <span class="text-sm text-gray-600">최소 변동:</span>
                <input type="number" x-model.number="gpModule.jitter.min_percent"
                       min="-50" max="0" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                <span class="text-sm text-gray-500">%</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-sm text-gray-600">최대 변동:</span>
                <input type="number" x-model.number="gpModule.jitter.max_percent"
                       min="0" max="100" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                <span class="text-sm text-gray-500">%</span>
            </div>
        </div>
        <p x-show="gpModule.jitter.enabled" class="mt-2 text-xs text-gray-500">
            예: 기본 간격 120분, -20%~+30% → 실제 간격 96~156분 사이 랜덤
        </p>
    </div>
</div>
```

### 1-4. 성장 구간 설정 (stages) (~180줄)

```html
<!-- 성장 구간 설정 -->
<div class="space-y-4 mb-6">
    <div class="flex items-center justify-between">
        <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
            📊 성장 구간 설정
        </h3>
        <button type="button" @click="gpModule.addStage()"
                class="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
            구간 추가
        </button>
    </div>

    <!-- 연속성 검증 경고 -->
    <div x-show="gpModule.validationError" class="p-3 bg-red-50 border border-red-200 rounded-lg">
        <p class="text-sm text-red-700" x-text="gpModule.validationError"></p>
    </div>

    <!-- 구간 반복 -->
    <template x-for="(stage, stageIdx) in gpModule.stages" :key="stageIdx">
        <div class="border border-gray-200 rounded-lg p-5 bg-white shadow-sm">
            <!-- 구간 헤더 -->
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                    <span class="text-lg font-bold text-blue-600" x-text="'구간 ' + (stageIdx + 1)"></span>
                    <input type="text" x-model="stage.label"
                           class="px-2 py-1 border border-gray-200 rounded text-sm w-32"
                           placeholder="라벨 (예: 급성장기)">
                </div>
                <button type="button" @click="gpModule.removeStage(stageIdx)"
                        x-show="gpModule.stages.length > 1"
                        class="text-red-400 hover:text-red-600 text-sm flex items-center gap-1">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                    </svg>
                    삭제
                </button>
            </div>

            <!-- 구간 이름 (내부 식별용) -->
            <div class="mb-3">
                <label class="text-xs text-gray-500">내부 이름 (영문)</label>
                <input type="text" x-model="stage.name"
                       class="px-2 py-1 border border-gray-200 rounded text-sm w-40"
                       placeholder="예: rapid_growth">
            </div>

            <!-- 적용 구간 (포스트 수) -->
            <div class="flex items-center gap-3 mb-4 p-3 bg-gray-50 rounded-lg">
                <span class="text-sm text-gray-600">적용 구간:</span>
                <input type="number" x-model.number="stage.post_count_min"
                       min="0" class="w-20 px-2 py-1 border border-gray-300 rounded text-sm"
                       :disabled="stageIdx > 0"
                       @input="gpModule.validateContinuity()">
                <span class="text-gray-400">~</span>
                <template x-if="stageIdx < gpModule.stages.length - 1">
                    <input type="number" x-model.number="stage.post_count_max"
                           min="1" class="w-20 px-2 py-1 border border-gray-300 rounded text-sm"
                           @input="gpModule.onMaxChanged(stageIdx)">
                </template>
                <template x-if="stageIdx === gpModule.stages.length - 1">
                    <span class="text-sm text-gray-500 font-medium">무제한</span>
                </template>
                <span class="text-sm text-gray-500">글</span>
            </div>

            <!-- 설명 -->
            <div class="mb-4">
                <input type="text" x-model="stage.description"
                       class="w-full px-2 py-1 border border-gray-200 rounded text-sm text-gray-500"
                       placeholder="구간 설명 (선택)">
            </div>

            <!-- === 모듈별 활성화 + 간격 설정 === -->
            <div class="space-y-3">

                <!-- 생성 (Generate) -->
                <div class="border border-gray-100 rounded-lg p-3"
                     :class="stage.generate.enabled ? 'bg-green-50 border-green-200' : 'bg-gray-50'">
                    <label class="flex items-center cursor-pointer mb-2">
                        <input type="checkbox" x-model="stage.generate.enabled"
                               class="rounded text-green-600 focus:ring-green-500 h-4 w-4">
                        <span class="ml-2 text-sm font-medium" :class="stage.generate.enabled ? 'text-green-800' : 'text-gray-500'">
                            🤖 생성 (Generate)
                        </span>
                    </label>
                    <div x-show="stage.generate.enabled" class="ml-6 space-y-2">
                        <!-- 최소 보유 수 -->
                        <div class="flex items-center gap-2">
                            <span class="text-xs text-gray-600">최소 재고:</span>
                            <input type="number" x-model.number="stage.generate.min_inventory"
                                   min="1" max="100" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                            <span class="text-xs text-gray-500">개 미만이면 생성 시작</span>
                        </div>
                        <!-- 간격 모드 (공통 컴포넌트) -->
                        <div x-html="gpModule.renderIntervalControls(stageIdx, 'generate')"></div>
                    </div>
                </div>

                <!-- 발행 (Publish) -->
                <div class="border border-gray-100 rounded-lg p-3"
                     :class="stage.publish.enabled ? 'bg-blue-50 border-blue-200' : 'bg-gray-50'">
                    <label class="flex items-center cursor-pointer mb-2">
                        <input type="checkbox" x-model="stage.publish.enabled"
                               class="rounded text-blue-600 focus:ring-blue-500 h-4 w-4">
                        <span class="ml-2 text-sm font-medium" :class="stage.publish.enabled ? 'text-blue-800' : 'text-gray-500'">
                            📤 발행 (Publish)
                        </span>
                    </label>
                    <div x-show="stage.publish.enabled" class="ml-6 space-y-2">
                        <div x-html="gpModule.renderIntervalControls(stageIdx, 'publish')"></div>
                    </div>
                </div>

                <!-- 재발행 (Republish) -->
                <div class="border border-gray-100 rounded-lg p-3"
                     :class="stage.republish.enabled ? 'bg-purple-50 border-purple-200' : 'bg-gray-50'">
                    <label class="flex items-center cursor-pointer mb-2">
                        <input type="checkbox" x-model="stage.republish.enabled"
                               class="rounded text-purple-600 focus:ring-purple-500 h-4 w-4">
                        <span class="ml-2 text-sm font-medium" :class="stage.republish.enabled ? 'text-purple-800' : 'text-gray-500'">
                            🔄 재발행 (Republish)
                        </span>
                    </label>
                    <div x-show="stage.republish.enabled" class="ml-6 space-y-2">
                        <div x-html="gpModule.renderIntervalControls(stageIdx, 'republish')"></div>
                    </div>
                </div>
            </div>
        </div>
    </template>
</div>
```

**간격 설정 공통 컴포넌트** (`renderIntervalControls` 메서드가 반환하는 HTML):

```html
<!-- interval_mode 라디오 -->
<div class="flex gap-4">
    <label class="flex items-center cursor-pointer">
        <input type="radio" :name="'interval_' + stageIdx + '_' + moduleKey"
               :checked="stage[moduleKey].interval_mode === 'manual'"
               @change="stage[moduleKey].interval_mode = 'manual'"
               class="text-blue-600 h-3 w-3">
        <span class="ml-1.5 text-xs text-gray-600">시간으로 설정</span>
    </label>
    <label class="flex items-center cursor-pointer">
        <input type="radio" :name="'interval_' + stageIdx + '_' + moduleKey"
               :checked="stage[moduleKey].interval_mode === 'auto'"
               @change="stage[moduleKey].interval_mode = 'auto'"
               class="text-blue-600 h-3 w-3">
        <span class="ml-1.5 text-xs text-gray-600">횟수로 설정</span>
    </label>
</div>
<!-- Manual: 분 입력 -->
<div x-show="stage[moduleKey].interval_mode === 'manual'" class="flex items-center gap-2">
    <input type="number" x-model.number="stage[moduleKey].interval_minutes"
           min="15" max="1440" class="w-20 px-2 py-1 border border-gray-300 rounded text-sm">
    <span class="text-xs text-gray-500">분 간격</span>
    <span class="text-xs text-blue-600">
        (하루 약 <span x-text="gpModule.calcDailyFromMinutes(stage[moduleKey].interval_minutes)"></span>회)
    </span>
</div>
<!-- Auto: 횟수 입력 -->
<div x-show="stage[moduleKey].interval_mode === 'auto'" class="flex items-center gap-2">
    <span class="text-xs text-gray-600">하루</span>
    <input type="number" x-model.number="stage[moduleKey].daily_count"
           min="1" max="100" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
    <span class="text-xs text-gray-500">회</span>
    <span class="text-xs text-blue-600">
        (약 <span x-text="gpModule.calcMinutesFromDaily(stage[moduleKey].daily_count)"></span>분 간격)
    </span>
</div>
```

> **`renderIntervalControls` 대안**: Alpine.js에서 `x-html`은 reactive가 아님. 대신 `<template>` + `x-if`로 직접 인라인 구현하거나, Alpine `x-data` 중첩으로 처리. 구현 시 가장 적합한 방식 선택.

### 1-5. 워밍업 설정 (~50줄)

```html
<!-- 워밍업 설정 -->
<div class="space-y-4 mb-6">
    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
        🔥 워밍업 설정
    </h3>
    <div class="p-4 bg-gray-50 rounded-lg">
        <label class="flex items-center cursor-pointer mb-3">
            <input type="checkbox" x-model="gpModule.warmup.enabled"
                   class="rounded text-orange-600 focus:ring-orange-500 h-4 w-4">
            <span class="ml-2 text-sm text-gray-700">워밍업 사용</span>
            <span class="ml-2 text-xs text-gray-400">(신규 블로그의 발행 수를 점진적으로 증가)</span>
        </label>
        <div x-show="gpModule.warmup.enabled" class="space-y-3 ml-6">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="text-xs text-gray-600">워밍업 기간</label>
                    <div class="flex items-center gap-2">
                        <input type="number" x-model.number="gpModule.warmup.warmup_days"
                               min="1" max="90" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                        <span class="text-xs text-gray-500">일</span>
                    </div>
                </div>
                <div>
                    <label class="text-xs text-gray-600">시작 일일 발행 수</label>
                    <div class="flex items-center gap-2">
                        <input type="number" x-model.number="gpModule.warmup.initial_daily_posts"
                               min="1" max="10" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                        <span class="text-xs text-gray-500">건</span>
                    </div>
                </div>
                <div>
                    <label class="text-xs text-gray-600">최대 일일 발행 수</label>
                    <div class="flex items-center gap-2">
                        <input type="number" x-model.number="gpModule.warmup.max_daily_posts"
                               min="1" max="20" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                        <span class="text-xs text-gray-500">건</span>
                    </div>
                </div>
                <div>
                    <label class="text-xs text-gray-600">증가율 (ramp_rate)</label>
                    <div class="flex items-center gap-2">
                        <input type="number" x-model.number="gpModule.warmup.ramp_rate"
                               min="0.1" max="5" step="0.1" class="w-16 px-2 py-1 border border-gray-300 rounded text-sm">
                        <span class="text-xs text-gray-500">/일</span>
                    </div>
                </div>
            </div>

            <!-- 워밍업 시뮬레이션 -->
            <div class="mt-3 p-3 bg-orange-50 rounded-lg">
                <p class="text-xs text-orange-700 font-medium mb-1">워밍업 시뮬레이션</p>
                <div class="text-xs text-orange-600 space-y-0.5">
                    <template x-for="sim in gpModule.warmupSimulation" :key="sim.day">
                        <div>
                            <span x-text="'Day ' + sim.day + ':'"></span>
                            <span class="font-medium" x-text="'일 ' + sim.daily + '건 발행'"></span>
                            <span class="text-orange-400" x-text="'(간격 약 ' + sim.interval + '분)'"></span>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <p class="mt-2 text-xs text-gray-500">
            워밍업은 <strong>발행(publish)</strong>에만 적용됩니다. 생성과 재발행은 영향 없습니다.
        </p>
    </div>
</div>
```

### 1-6. 프리뷰 (~40줄)

```html
<!-- 블로그별 적용 프리뷰 -->
<div class="space-y-4 mb-6">
    <h3 class="text-base font-semibold text-gray-900 flex items-center gap-2">
        👁️ 적용 프리뷰
    </h3>
    <div class="p-4 bg-gray-50 rounded-lg">
        <p class="text-xs text-gray-500 mb-3">
            이 모듈이 포함된 Flow의 블로그에 적용될 설정 미리보기
        </p>

        <!-- 프리뷰 로딩 -->
        <div x-show="gpModule.previewLoading" class="text-center py-4">
            <span class="text-sm text-gray-400">불러오는 중...</span>
        </div>

        <!-- 프리뷰 없음 -->
        <div x-show="!gpModule.previewLoading && gpModule.previewBlogs.length === 0"
             class="text-center py-4">
            <span class="text-sm text-gray-400">Flow에 연결된 블로그가 없습니다</span>
        </div>

        <!-- 프리뷰 결과 -->
        <div x-show="!gpModule.previewLoading && gpModule.previewBlogs.length > 0"
             class="space-y-2">
            <template x-for="blog in gpModule.previewBlogs" :key="blog.id">
                <div class="flex items-center justify-between p-2 bg-white rounded border border-gray-200">
                    <div class="flex items-center gap-2">
                        <span class="text-sm font-medium text-gray-900" x-text="blog.name"></span>
                        <span class="text-xs text-gray-500" x-text="'(' + blog.postCount + '글)'"></span>
                        <span class="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700"
                              x-text="blog.stageName"></span>
                    </div>
                    <div class="flex gap-2 text-xs">
                        <span :class="blog.generate ? 'text-green-600' : 'text-gray-400'"
                              x-text="blog.generate || '생성 OFF'"></span>
                        <span class="text-gray-300">|</span>
                        <span :class="blog.publish ? 'text-blue-600' : 'text-gray-400'"
                              x-text="blog.publish || '발행 OFF'"></span>
                        <span class="text-gray-300">|</span>
                        <span :class="blog.republish ? 'text-purple-600' : 'text-gray-400'"
                              x-text="blog.republish || '재발행 OFF'"></span>
                    </div>
                </div>
            </template>
        </div>

        <button type="button" @click="gpModule.loadPreview()"
                class="mt-3 px-3 py-1.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300">
            🔄 프리뷰 새로고침
        </button>
    </div>
</div>
```

---

## 파일 2: growth-profile-form.js (신규)

### 경로: `app/static/js/modules/growth-profile-form.js` (~450줄)
### 설명: GP 폼 Alpine.js 상태 관리 + 검증 + 계산 로직

### 2-1. 전체 구조

```javascript
/**
 * Growth Profile 모듈 폼 Alpine.js 상태 및 로직
 * _growth_profile_form.html과 함께 사용
 */
function createGrowthProfileState() {
    return {
        // --- 프리셋 ---
        selectedPreset: 'balanced',
        presets: [ /* 1-1에 정의된 3종 */ ],

        // --- 활성 시간대 ---
        schedule_matrix: /* 7x24 기본값 (balanced 프리셋 기준) */,
        days: ['월', '화', '수', '목', '금', '토', '일'],

        // --- 지터 ---
        jitter: { enabled: true, min_percent: -20, max_percent: 30 },

        // --- 성장 구간 ---
        stages: [ /* balanced 프리셋의 3단계 기본값 */ ],

        // --- 워밍업 ---
        warmup: { enabled: true, warmup_days: 14, initial_daily_posts: 1, max_daily_posts: 3, ramp_rate: 0.5 },

        // --- 프리뷰 ---
        previewBlogs: [],
        previewLoading: false,

        // --- 검증 ---
        validationError: null,

        // 계산된 값 (computed)
        get activeHoursCount() { /* 주간 활성 시간 합계 */ },
        get todayActiveHours() { /* 오늘 요일의 활성 시간 */ },
        get warmupSimulation() { /* Day 0, 2, 4, ... 시뮬레이션 배열 */ },

        // 메서드 (아래 상세)
    };
}
```

### 2-2. 메서드 목록

| 메서드 | 줄 수 | 설명 |
|--------|-------|------|
| `loadPreset(key)` | ~20줄 | 프리셋 로드: API 호출 또는 내장 데이터에서 schedule_matrix/jitter/stages/warmup 설정 |
| `initFromSettings(settings)` | ~25줄 | 기존 settings JSONB에서 gpModule 상태 초기화 (편집 모드) |
| `toSettings()` | ~30줄 | gpModule 상태 → settings JSONB 직렬화 (저장 시 호출) |
| `addStage()` | ~15줄 | 구간 추가: 이전 구간의 max+1을 min으로, max=null, 모듈 기본 활성 |
| `removeStage(idx)` | ~10줄 | 구간 삭제: 최소 1개 유지, 삭제 확인 |
| `onMaxChanged(idx)` | ~10줄 | post_count_max 변경 시 다음 구간의 min 자동 갱신 |
| `validateContinuity()` | ~25줄 | stages 연속성 검증 (빈 범위/겹침 없음, 첫 구간 min=0) |
| `toggleHour(dayIdx, hour)` | ~3줄 | 스케줄 셀 토글 |
| `toggleDay(dayIdx)` | ~5줄 | 요일 전체 토글 |
| `selectAllHours()` | ~5줄 | 전체 선택 |
| `clearAllHours()` | ~5줄 | 전체 해제 |
| `selectWeekdayHours()` | ~10줄 | 평일 6~21시 선택 |
| `selectWeekendHours()` | ~10줄 | 주말 7~20시 선택 |
| `calcDailyFromMinutes(min)` | ~5줄 | manual → 하루 예상 횟수 계산 |
| `calcMinutesFromDaily(count)` | ~5줄 | auto → 예상 간격(분) 계산 |
| `renderIntervalControls(idx, key)` | ~30줄 | 간격 설정 HTML 반환 (또는 인라인 대체) |
| `loadPreview()` | ~20줄 | 프리뷰 API 호출 (`/api/v1/growth-profile/preview`) |
| `validate()` | ~15줄 | 전체 폼 검증 (저장 전 호출) |

### 2-3. 핵심 메서드 상세

**`loadPreset(key)`**:
```javascript
async loadPreset(key) {
    this.selectedPreset = key;
    try {
        const resp = await fetch(`/api/v1/growth-profile/presets/${key}`);
        const data = await resp.json();
        this.schedule_matrix = data.schedule_matrix;
        this.jitter = data.jitter || { enabled: true, min_percent: -20, max_percent: 30 };
        this.stages = data.stages.map(s => ({
            name: s.name,
            label: s.label,
            post_count_min: s.post_count_min,
            post_count_max: s.post_count_max,
            description: s.description || '',
            generate: { ...s.generate },
            publish: { ...s.publish },
            republish: { ...s.republish },
        }));
        this.warmup = data.warmup || { enabled: false };
        this.validateContinuity();
    } catch (e) {
        console.error('[GP] 프리셋 로드 실패:', e);
    }
}
```

**`toSettings()`** (저장 시 호출):
```javascript
toSettings() {
    return {
        schedule_matrix: this.schedule_matrix,
        jitter: this.jitter,
        stages: this.stages.map(s => ({
            name: s.name,
            label: s.label,
            post_count_min: s.post_count_min,
            post_count_max: s.post_count_max,
            description: s.description,
            generate: {
                enabled: s.generate.enabled,
                min_inventory: s.generate.enabled ? s.generate.min_inventory : null,
                interval_mode: s.generate.enabled ? s.generate.interval_mode : null,
                interval_minutes: s.generate.interval_mode === 'manual' ? s.generate.interval_minutes : null,
                daily_count: s.generate.interval_mode === 'auto' ? s.generate.daily_count : null,
            },
            publish: {
                enabled: s.publish.enabled,
                interval_mode: s.publish.enabled ? s.publish.interval_mode : null,
                interval_minutes: s.publish.interval_mode === 'manual' ? s.publish.interval_minutes : null,
                daily_count: s.publish.interval_mode === 'auto' ? s.publish.daily_count : null,
            },
            republish: {
                enabled: s.republish.enabled,
                interval_mode: s.republish.enabled ? s.republish.interval_mode : null,
                interval_minutes: s.republish.interval_mode === 'manual' ? s.republish.interval_minutes : null,
                daily_count: s.republish.interval_mode === 'auto' ? s.republish.daily_count : null,
            },
        })),
        warmup: this.warmup.enabled ? this.warmup : { enabled: false },
    };
}
```

**`validateContinuity()`**:
```javascript
validateContinuity() {
    this.validationError = null;
    if (this.stages.length === 0) {
        this.validationError = '최소 1개 구간이 필요합니다';
        return false;
    }
    if (this.stages[0].post_count_min !== 0) {
        this.validationError = '첫 구간의 시작값은 0이어야 합니다';
        return false;
    }
    for (let i = 1; i < this.stages.length; i++) {
        const prev = this.stages[i - 1];
        const curr = this.stages[i];
        if (prev.post_count_max === null || prev.post_count_max === undefined) {
            this.validationError = `구간 ${i}의 종료값을 설정해주세요`;
            return false;
        }
        const expectedMin = prev.post_count_max + 1;
        if (curr.post_count_min !== expectedMin) {
            curr.post_count_min = expectedMin; // 자동 보정
        }
    }
    // 마지막 구간의 max는 null (무제한)
    this.stages[this.stages.length - 1].post_count_max = null;
    return true;
}
```

**`addStage()`**:
```javascript
addStage() {
    const last = this.stages[this.stages.length - 1];
    const newMin = (last.post_count_max || 0) + 1;
    // 기존 마지막 구간에 max 설정 (아직 null이면 newMin - 1)
    if (last.post_count_max === null) {
        last.post_count_max = newMin - 1;
    }
    this.stages.push({
        name: `stage_${this.stages.length + 1}`,
        label: '',
        post_count_min: newMin,
        post_count_max: null, // 새 마지막 구간 = 무제한
        description: '',
        generate: { enabled: true, min_inventory: 5, interval_mode: 'auto', interval_minutes: null, daily_count: 3 },
        publish: { enabled: true, interval_mode: 'auto', interval_minutes: null, daily_count: 2 },
        republish: { enabled: true, interval_mode: 'auto', interval_minutes: null, daily_count: 2 },
    });
    this.validateContinuity();
}
```

**`warmupSimulation` (computed getter)**:
```javascript
get warmupSimulation() {
    if (!this.warmup.enabled) return [];
    const { initial_daily_posts, max_daily_posts, ramp_rate, warmup_days } = this.warmup;
    const activeHours = this.todayActiveHours || 16;
    const sims = [];
    for (const day of [0, 2, 4, 7, 10, 14]) {
        if (day > warmup_days) break;
        const daily = Math.min(initial_daily_posts + Math.floor(day * ramp_rate), max_daily_posts);
        const interval = Math.floor((activeHours * 60) / daily);
        sims.push({ day, daily, interval });
    }
    return sims;
}
```

---

## 파일 3: growth-profile-form-template.js (신규)

### 경로: `app/static/js/modules/growth-profile-form-template.js` (~100줄)
### 설명: list.js 인라인 폼에서 사용하는 간소화 GP 템플릿

> **설계 결정**: GP 폼이 복잡하므로, 인라인 폼에서는 **프리셋 선택 + 기본 요약만** 표시. 상세 편집은 전용 폼 페이지로 유도.

```javascript
/** GP 모듈 인라인 폼 간소화 템플릿 - list.js에서 호출 */
function getGrowthProfileFormTemplate() {
    return `
        <div x-show="formData.type_code === 'growth_profile'" class="space-y-4">
            <!-- 프리셋 선택 카드 -->
            <h4 class="text-sm font-semibold text-gray-900">📋 기본 프로파일 선택</h4>
            <div class="grid grid-cols-3 gap-3">
                <div class="border-2 rounded-lg p-3 cursor-pointer text-center"
                     :class="formData.settings._preset === 'aggressive' ? 'border-red-400 bg-red-50' : 'border-gray-200'"
                     @click="formData.settings = {...window._gpPresets.aggressive, _preset: 'aggressive'}">
                    <div class="text-sm font-medium">🔥 공격적</div>
                    <div class="text-xs text-gray-500">빠른 성장</div>
                </div>
                <div class="border-2 rounded-lg p-3 cursor-pointer text-center"
                     :class="formData.settings._preset === 'balanced' ? 'border-blue-400 bg-blue-50' : 'border-gray-200'"
                     @click="formData.settings = {...window._gpPresets.balanced, _preset: 'balanced'}">
                    <div class="text-sm font-medium">⚖️ 균형</div>
                    <div class="text-xs text-gray-500">기본 추천</div>
                </div>
                <div class="border-2 rounded-lg p-3 cursor-pointer text-center"
                     :class="formData.settings._preset === 'conservative' ? 'border-green-400 bg-green-50' : 'border-gray-200'"
                     @click="formData.settings = {...window._gpPresets.conservative, _preset: 'conservative'}">
                    <div class="text-sm font-medium">🛡️ 보수적</div>
                    <div class="text-xs text-gray-500">안정 운영</div>
                </div>
            </div>
            <p class="text-xs text-gray-400">생성 후 상세 편집에서 구간/간격/스케줄을 세부 조정할 수 있습니다.</p>
        </div>
    `;
}
```

> **`window._gpPresets`**: list.js 초기화 시 `/api/v1/growth-profile/presets` 호출 결과를 캐싱하거나, `growth_profile_defaults.py`의 프리셋을 서버에서 렌더링하여 `<script>` 태그로 주입.

---

## 파일 4: growth_profile API (신규)

### 경로: `app/api/growth_profile.py` (~100줄)
### 설명: GP 프리셋 조회 + 스테이지 프리뷰 API

```python
"""
Growth Profile API 엔드포인트

프리셋 조회 및 스테이지 미리보기 제공
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db_session
from app.routers.auth import get_current_user
from app.models.flow import Flow
from app.models.flow_blog import FlowBlog
from app.models.blog import Blog
from app.services.generation.growth_profile_defaults import (
    DEFAULT_PROFILES,
    get_default_profile,
    get_available_profiles,
)
from app.services.generation.growth_profile_resolver import GrowthProfileResolver

router = APIRouter(prefix="/growth-profile", tags=["growth-profile"])
```

### 4-1. 프리셋 목록 API

```python
@router.get("/presets")
async def get_presets(user=Depends(get_current_user)):
    """기본 프로파일 목록 반환"""
    profiles = get_available_profiles()
    return {
        "profiles": [
            {
                "key": key,
                "name": meta["name"],
                "description": meta["description"],
                "stage_count": len(meta["stages"]),
                "warmup_enabled": meta.get("warmup", {}).get("enabled", False),
            }
            for key, meta in profiles.items()
        ]
    }
```

### 4-2. 프리셋 상세 API

```python
@router.get("/presets/{preset_key}")
async def get_preset_detail(
    preset_key: str,
    user=Depends(get_current_user),
):
    """특정 프리셋의 전체 settings 반환 (UI에서 프리셋 로드 시 호출)"""
    profile = get_default_profile(preset_key)
    if not profile:
        from fastapi import HTTPException
        raise HTTPException(404, f"프리셋 '{preset_key}'을 찾을 수 없습니다")
    return profile
```

### 4-3. 스테이지 프리뷰 API

```python
@router.post("/preview")
async def preview_stages(
    settings: dict,
    flow_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user),
):
    """
    GP settings 기반으로 블로그별 스테이지 매핑 미리보기

    Args:
        settings: Growth Profile settings JSONB
        flow_id: (선택) Flow ID - 지정 시 해당 Flow의 블로그만 조회

    Returns:
        blogs: [{id, name, postCount, stageName, generate, publish, republish}]
    """
    # 1. 블로그 조회
    if flow_id:
        result = await db.execute(
            select(Blog)
            .join(FlowBlog, FlowBlog.blog_id == Blog.id)
            .where(FlowBlog.flow_id == flow_id)
        )
        blogs = result.scalars().all()
    else:
        return {"blogs": []}

    if not blogs:
        return {"blogs": []}

    # 2. 블로그별 포스트 수 맵
    blog_post_counts = {b.id: b.total_post_count or 0 for b in blogs}

    # 3. GrowthProfileResolver로 스테이지 매핑
    try:
        ctx = GrowthProfileResolver.build_execution_context(
            flow_id=flow_id or 0,
            gp_settings=settings,
            blog_post_counts=blog_post_counts,
        )
    except Exception as e:
        return {"blogs": [], "error": str(e)}

    # 4. 결과 조합
    active_hours = GrowthProfileResolver.count_active_hours(
        settings.get("schedule_matrix")
    )
    preview_blogs = []
    for blog in blogs:
        stage = ctx.get_stage_for_blog(blog.id)
        if stage:
            preview_blogs.append({
                "id": blog.id,
                "name": blog.name,
                "postCount": blog.total_post_count or 0,
                "stageName": stage.stage_label,
                "generate": _format_module_info(stage.generate, "생성", active_hours),
                "publish": _format_module_info(stage.publish, "발행", active_hours),
                "republish": _format_module_info(stage.republish, "재발행", active_hours),
            })
        else:
            preview_blogs.append({
                "id": blog.id,
                "name": blog.name,
                "postCount": blog.total_post_count or 0,
                "stageName": "매핑 없음",
                "generate": None,
                "publish": None,
                "republish": None,
            })

    return {"blogs": preview_blogs}


def _format_module_info(params, label: str, active_hours: int) -> Optional[str]:
    """ModuleIntervalParams → 사람이 읽을 수 있는 문자열"""
    if not params.enabled:
        return None
    if params.interval_mode == "auto" and params.daily_count:
        return f"하루 {params.daily_count}회"
    elif params.interval_mode == "manual" and params.interval_minutes:
        return f"{params.interval_minutes}분 간격"
    return label
```

### 4-4. API 라우터 등록

**수정 파일**: `app/main.py` 또는 API 라우터 등록부

```python
from app.api.growth_profile import router as gp_router
app.include_router(gp_router, prefix="/api/v1")
```

---

## 파일 5: _form.html 수정

### 경로: `app/templates/modules/_form.html`
### 변경: growth_profile 타입 include 추가

**변경 전** (1069~1077줄):
```html
        <!-- 생성 모듈 설정 -->
        <div x-show="formData.type_code === 'generate'">
            {% include "modules/_generate_form.html" %}
        </div>

        <!-- 프롬프트 모듈 설정 -->
        <div x-show="formData.type_code === 'prompt'">
            {% include "modules/_prompt_form.html" %}
        </div>
```

**변경 후**:
```html
        <!-- 생성 모듈 설정 -->
        <div x-show="formData.type_code === 'generate'">
            {% include "modules/_generate_form.html" %}
        </div>

        <!-- 프롬프트 모듈 설정 -->
        <div x-show="formData.type_code === 'prompt'">
            {% include "modules/_prompt_form.html" %}
        </div>

        <!-- 성장 프로파일 설정 -->
        <div x-show="formData.type_code === 'growth_profile'">
            {% include "modules/_growth_profile_form.html" %}
        </div>
```

**추가**: "기타 타입" 분기(1080줄)의 조건에 `growth_profile` 제외 추가:
```html
<!-- 변경 전 -->
<div x-show="formData.type_code !== 'republish' && formData.type_code !== 'collect' && formData.type_code !== 'data' && formData.type_code !== 'generate' && formData.type_code !== 'prompt'">

<!-- 변경 후 -->
<div x-show="formData.type_code !== 'republish' && formData.type_code !== 'collect' && formData.type_code !== 'data' && formData.type_code !== 'generate' && formData.type_code !== 'prompt' && formData.type_code !== 'growth_profile'">
```

---

## 파일 6: form.js 수정

### 경로: `app/static/js/modules/form.js`
### 변경: GP state 초기화 + 저장 직렬화 (+40줄)

### 6-1. GP state 초기화

`moduleFormApp()` 함수 내 return 객체에 추가 (24줄 부근, `promptModule` 아래):

```javascript
// Growth Profile 모듈 상태
gpModule: window.createGrowthProfileState
    ? window.createGrowthProfileState()
    : {},
```

### 6-2. init() 메서드에 GP 편집 모드 초기화 추가

```javascript
// 기존 init() 내부, 편집 모드에서 settings 로딩 후:
if (this.formData.type_code === 'growth_profile' && this.module?.settings) {
    this.gpModule.initFromSettings(this.module.settings);
}
```

### 6-3. submitForm()에서 GP settings 직렬화

```javascript
// submitForm() 내부, API 호출 전 데이터 조합:
if (this.formData.type_code === 'growth_profile') {
    // GP 검증
    if (!this.gpModule.validate()) {
        this.showError(this.gpModule.validationError || 'Growth Profile 설정 오류');
        return;
    }
    formPayload.settings = this.gpModule.toSettings();
}
```

### 6-4. `<script>` 태그에 growth-profile-form.js 로드

`_form.html` 하단 또는 `list.html` 하단의 script 블록에 추가:

```html
<script src="{{ url_for('static', path='js/modules/growth-profile-form.js') }}"></script>
```

---

## 파일 7: _card.html 수정

### 경로: `app/templates/modules/_card.html`
### 변경: GP 카드 요약 정보 표시 (+30줄)

모듈 카드에서 `growth_profile` 타입일 때 추가 정보 표시:

```html
<!-- GP 모듈 카드 정보 -->
<template x-if="module.module_type?.code === 'growth_profile'">
    <div class="mt-2 space-y-1">
        <!-- 구간 수 -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
            <span>📊</span>
            <span x-text="(module.settings?.stages?.length || 0) + '단계 구간'"></span>
        </div>
        <!-- 활성 모듈 요약 -->
        <div class="flex flex-wrap gap-1">
            <template x-if="module.settings?.stages?.some(s => s.generate?.enabled)">
                <span class="px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-700">생성</span>
            </template>
            <template x-if="module.settings?.stages?.some(s => s.publish?.enabled)">
                <span class="px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-700">발행</span>
            </template>
            <template x-if="module.settings?.stages?.some(s => s.republish?.enabled)">
                <span class="px-1.5 py-0.5 text-xs rounded bg-purple-100 text-purple-700">재발행</span>
            </template>
        </div>
        <!-- 워밍업 상태 -->
        <template x-if="module.settings?.warmup?.enabled">
            <div class="flex items-center gap-1 text-xs text-orange-600">
                <span>🔥</span>
                <span x-text="'워밍업 ' + (module.settings.warmup.warmup_days || 14) + '일'"></span>
            </div>
        </template>
    </div>
</template>
```

---

## 파일 8: Flow 편집 UI 연동 (E-2, 권장)

### 대상: Flow 상세/편집 화면 (블로그 목록 영역)
### 변경: 블로그별 스테이지 배지 + 간격 표시

> **구현 방식**: Flow 편집 화면에서 GP 모듈이 포함된 경우, 블로그 목록 영역에 스테이지 정보를 표시.
> Flow 로드 시 `/api/v1/growth-profile/preview` API를 호출하여 블로그별 매핑 결과를 받아 표시.

### 8-1. 블로그별 스테이지 배지

```html
<!-- Flow 편집 화면의 블로그 목록 항목에 추가 -->
<template x-if="flowHasGP && blogStageMap[blog.id]">
    <div class="flex items-center gap-2 mt-1">
        <span class="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700"
              x-text="blogStageMap[blog.id].stageName"></span>
        <span class="text-xs text-gray-400" x-text="blogStageMap[blog.id].summary"></span>
    </div>
</template>
```

### 8-2. GP 배지 (Flow 상단)

```html
<!-- Flow 편집 화면 상단에 GP 정보 배지 -->
<template x-if="flowHasGP">
    <div class="px-3 py-1.5 bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg text-sm">
        <span class="font-medium text-blue-800">📈 성장 전략 적용됨</span>
        <span class="text-blue-600 ml-2" x-text="gpModuleName"></span>
    </div>
</template>
```

### 8-3. 데이터 로딩

```javascript
// Flow 편집 JS에서 GP 프리뷰 로드
async function loadGPPreview(flowId, gpSettings) {
    const resp = await fetch('/api/v1/growth-profile/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: gpSettings, flow_id: flowId }),
    });
    const data = await resp.json();
    // blogStageMap 업데이트
    data.blogs.forEach(b => {
        this.blogStageMap[b.id] = {
            stageName: b.stageName,
            summary: [b.generate, b.publish, b.republish].filter(Boolean).join(' / '),
        };
    });
}
```

---

## 파일 9: 대시보드 위젯 (E-3, 선택)

### 대상: 대시보드 페이지
### 설명: 성장 단계 현황 + 재고 현황 위젯

> 작업계획서 Section 9-3 기준. 별도 Phase로 분리 가능.

| 위젯 | 표시 내용 | API 필요 |
|------|---------|---------|
| **성장 단계 현황** | 단계별 블로그 수 집계 (급성장기: 45개, 성장기: 30개 ...) | `/api/v1/growth-profile/stats` |
| **스테이지 전환 임박** | "Blog A: 47/50글 → 곧 성장기 전환" 알림 | 위 API에 포함 |
| **재고 현황** | 블로그별 재고 vs min_inventory 바 차트 | `/api/v1/growth-profile/inventory` |
| **활성 시간대 현황** | 현재 활성/비활성 상태, 다음 활성까지 남은 시간 | 프론트엔드 계산 |

> **구현 시 참고**: 대시보드 위젯은 GP 모듈 폼 UI와 독립적이므로, E-1 완료 후 별도로 진행 가능.

---

## 파일 10: 테스트

### 경로: `tests/integration/test_phase_e_gp_ui.py` (~200줄)
### 설명: GP API 테스트 + 설정 검증

### 테스트 목록 (15개)

#### 클래스 1: TestPresetAPI (4개)

| ID | 메서드 | 시나리오 | 기대 |
|----|--------|---------|------|
| T01 | `test_get_presets_list` | GET /presets | 3종 반환 (aggressive/balanced/conservative) |
| T02 | `test_get_preset_detail_balanced` | GET /presets/balanced | schedule_matrix + stages + warmup 포함 |
| T03 | `test_get_preset_detail_invalid` | GET /presets/nonexistent | 404 에러 |
| T04 | `test_preset_stages_valid` | 각 프리셋의 stages 연속성 검증 | validateStages 통과 |

#### 클래스 2: TestPreviewAPI (4개)

| ID | 메서드 | 시나리오 | 기대 |
|----|--------|---------|------|
| T05 | `test_preview_with_blogs` | balanced + 3개 블로그 (30/100/200글) | 각각 올바른 스테이지 매핑 |
| T06 | `test_preview_no_flow_id` | flow_id 없이 호출 | 빈 배열 반환 |
| T07 | `test_preview_empty_flow` | 블로그 0개 Flow | 빈 배열 반환 |
| T08 | `test_preview_invalid_settings` | 잘못된 settings | error 포함 응답 |

#### 클래스 3: TestSettingsSerialization (4개)

| ID | 메서드 | 시나리오 | 기대 |
|----|--------|---------|------|
| T09 | `test_balanced_roundtrip` | balanced 프리셋 → toSettings() → initFromSettings() | 동일한 값 복원 |
| T10 | `test_disabled_module_clears_interval` | enabled=false → toSettings() | interval_mode=null |
| T11 | `test_stage_continuity_auto_fix` | max=50, 다음 min=55 (불일치) → validateContinuity() | min이 51로 자동 보정 |
| T12 | `test_last_stage_max_null` | 마지막 구간 max 강제 null | validateContinuity() 후 null 유지 |

#### 클래스 4: TestCardDisplay (3개)

| ID | 메서드 | 시나리오 | 기대 |
|----|--------|---------|------|
| T13 | `test_gp_card_shows_stage_count` | 3단계 GP 모듈 | "3단계 구간" 표시 |
| T14 | `test_gp_card_shows_active_modules` | generate+republish만 활성 | 생성/재발행 배지만 표시 |
| T15 | `test_gp_card_warmup_indicator` | warmup.enabled=true | 워밍업 배지 표시 |

---

## 구현 순서

```
1. growth_profile API (파일 4)         독립, 프리셋/프리뷰 엔드포인트
2. growth-profile-form.js (파일 2)     독립, Alpine.js 로직
3. _growth_profile_form.html (파일 1)  2에 의존, 폼 HTML
4. _form.html 수정 (파일 5)            1에 의존, include 추가
5. form.js 수정 (파일 6)               2에 의존, 초기화/저장 연동
6. growth-profile-form-template.js (파일 3)  2에 의존, 인라인 간소화
7. _card.html 수정 (파일 7)            독립, 카드 표시
8. 테스트 (파일 10)                     1~7 완료 후
9. Flow 편집 UI (파일 8)               4에 의존, 선택 구현
10. 대시보드 위젯 (파일 9)              별도 계획, 선택 구현
```

**병렬 가능:**
- 1, 2, 7은 독립적이므로 병렬 구현 가능
- 3, 5, 6은 2 완료 후 병렬 가능
- 8, 9는 E-1 완료 후 별도 진행 가능

---

## 완료 기준 체크리스트

### 작업계획서 Section 10 Phase E 기준

- [ ] 사용자가 UI에서 Growth Profile 모듈을 **생성**할 수 있는지 (프리셋 선택 → 저장)
- [ ] 사용자가 UI에서 Growth Profile 모듈을 **편집**할 수 있는지 (기존 settings 로드 → 수정 → 저장)
- [ ] **구간 추가/삭제**: 동적으로 성장 구간 추가/삭제 가능, 최소 1개 유지
- [ ] **구간 연속성 검증**: post_count_max + 1 = 다음 min 자동 검증 + 보정
- [ ] **모듈별 체크박스 활성화**: 각 구간에서 generate/publish/republish 개별 활성화/비활성화
- [ ] **비활성 모듈 그레이아웃**: 체크 해제 시 해당 모듈 간격 설정 영역 비활성화
- [ ] **독립 간격 설정**: 각 모듈별 interval_mode (시간/횟수) 독립 설정
- [ ] **활성 시간대 설정**: 7x24 schedule_matrix 그리드 (클릭 토글, 빠른 선택 버튼)
- [ ] **지터 설정**: 간격 변동 활성화/비활성화, min/max percent 설정
- [ ] **워밍업 설정**: 토글 + warmup_days/initial/max/ramp_rate 입력
- [ ] **워밍업 시뮬레이션**: 경과일별 일일 발행 수 미리보기
- [ ] **프리셋 선택**: 3종 (aggressive/balanced/conservative) 카드 선택 → 설정 자동 로드
- [ ] **블로그별 프리뷰**: Flow의 블로그 기반 스테이지 매핑 미리보기

### 작업계획서 Section 9 UI/UX 설계 기준

- [ ] **9-1 편집 UI**: 모듈 레벨(스케줄+지터) + 구간 설정(stages) + 워밍업 + 프리뷰
- [ ] **9-2 Flow 편집**: 성장 전략 배지 + 블로그별 스테이지 + 모듈별 간격 표시 (E-2)
- [ ] **9-3 대시보드**: 성장 단계 현황 + 재고 현황 위젯 (E-3)

### 코드 품질

- [ ] 각 파일 500줄 미만 확인
- [ ] 각 함수 50줄 미만 확인
- [ ] 기존 Alpine.js 패턴 준수 (formData + 타입별 state)
- [ ] 기존 Tailwind CSS 클래스 패턴 준수
- [ ] API 엔드포인트에 타입 힌트 + Docstring
- [ ] 테스트 15개 작성 및 전체 통과
- [ ] Phase A~D 테스트 108개 영향 없음 확인

### interval_mode 관련 크로스체크 (Section 5 기준)

- [ ] `enabled=false`이면 하위 필드(interval_mode, interval_minutes, daily_count, min_inventory) 무시
- [ ] `interval_mode="manual"` → interval_minutes 필수, daily_count null
- [ ] `interval_mode="auto"` → daily_count 필수, interval_minutes null
- [ ] auto 간격 계산: `활성 시간(분) / daily_count = 간격(분)`
- [ ] generate 전용: min_inventory 필드 (publish/republish에는 없음)

### warmup 관련 크로스체크 (Section 5, Q4 기준)

- [ ] warmup은 **발행(publish)에만** 적용 (generate/republish 비간섭)
- [ ] `warmup.enabled=false` 또는 미설정 → 워밍업 미적용
- [ ] ramp_rate 공식: `min(initial + floor(경과일 × ramp_rate), max_daily_posts)`
- [ ] 워밍업 interval: `(active_hours × 60) / daily_max`

### settings JSONB 구조 크로스체크 (Section 5-1 기준)

- [ ] 최상위: `schedule_matrix` (7x24 bool[][]), `jitter`, `stages` (배열), `warmup`
- [ ] stages[]: `name`, `label`, `post_count_min`, `post_count_max`, `description`, `generate`, `publish`, `republish`
- [ ] generate: `enabled`, `min_inventory`, `interval_mode`, `interval_minutes`, `daily_count`
- [ ] publish: `enabled`, `interval_mode`, `interval_minutes`, `daily_count`
- [ ] republish: `enabled`, `interval_mode`, `interval_minutes`, `daily_count`
- [ ] warmup: `enabled`, `warmup_days`, `initial_daily_posts`, `max_daily_posts`, `ramp_rate`
