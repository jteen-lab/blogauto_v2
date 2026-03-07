# BlogAuto v2 - 성장 단계별 전략 설계 계획서

> **버전**: v3.1
> **작성일**: 2026-02-20
> **상태**: 검토 중
> **관련 문서**: inventory_management_system_plan.md, generation_module_workplan.md

---

## 목차

1. [설계 배경 및 문제점](#1-설계-배경-및-문제점)
2. [벤치마킹 인사이트](#2-벤치마킹-인사이트)
3. [설계 원칙](#3-설계-원칙)
4. [Growth Profile 모듈 아키텍처](#4-growth-profile-모듈-아키텍처)
5. [모듈 설정 상세 (settings JSONB)](#5-모듈-설정-상세-settings-jsonb)
6. [실행 흐름](#6-실행-흐름)
7. [기존 시스템과의 호환성](#7-기존-시스템과의-호환성)
8. [데이터 모델](#8-데이터-모델)
9. [UI/UX 설계](#9-uiux-설계)
10. [구현 단계](#10-구현-단계)
11. [부록: 설계 결정 포인트](#11-부록-설계-결정-포인트)

---

## 1. 설계 배경 및 문제점

### 1-1. 현재 시스템의 3가지 핵심 문제

블로그 성장 단계별 전략이 **세 개의 모듈에 각각 분리**되어 관리되고 있다.

| 모듈 | 현재 성장 단계 설정 방식 | 위치 |
|------|------------------------|------|
| **재발행 (republish)** | `Module.post_range_start/end` 컬럼으로 블로그 필터링 | `models/module.py` |
| **생성 (prompt)** | `Module.settings.inventory` 또는 `BlogGrowthSetting`으로 재고 임계값 결정 | `inventory_trigger.py` |
| **발행 (publish)** | 미구현 | - |

세 모듈의 성장 단계 설정이 서로 연동되지 않아 일관된 전략 적용이 불가능하다.

또한, 각 모듈이 자체적으로 스케줄러와 간격 설정을 가지고 있어서 **모듈 간 실행 타이밍이 충돌**하거나, 같은 성장 구간에서도 모듈마다 다른 속도로 동작하는 문제가 있다.

### 1-2. 문제점 정리

```
문제 1: BlogGrowthSetting은 블로그별 1:1 관계
  - 블로그 100개 -> 100개의 개별 설정 필요
  - 전략 변경 시 블로그마다 수정 필요

문제 2: 재발행 모듈의 post_range와 생성 모듈의 inventory 임계값이 연동 안 됨
  - 재발행: Module.post_range_start=1, post_range_end=50 (급성장기 블로그 대상)
  - 생성: BlogGrowthSetting.rapid_growth_inventory=10 (재고 10개 이하 시 생성)
  - 두 설정 간 "급성장기"의 정의가 일치하는지 보장할 수 없음

문제 3: 사용자가 각 모듈마다 따로 성장 단계를 관리해야 함
  - 재발행 모듈에서 post_range 설정
  - 생성 모듈에서 inventory 임계값 설정
  - 발행 모듈은 아직 없어서 발행 속도 제어 불가
  - 세 모듈의 전략이 동기화되지 않음

문제 4: 스케줄러/간격이 각 모듈에 분산되어 있음
  - 재발행 모듈: interval_mode + interval_minutes
  - 생성 모듈: 자체 트리거 로직
  - 발행 모듈: 미구현
  - 각 모듈이 독립적으로 동작하여 통합 제어 불가
```

### 1-3. 사용자의 기존 해결 방식

사용자가 재발행 모듈에서 사용한 패턴:

```
재발행 모듈 "RV-1~50"   -> post_range_start=1, post_range_end=50
재발행 모듈 "RV-51~100"  -> post_range_start=51, post_range_end=100
재발행 모듈 "RV-101~150" -> post_range_start=101, post_range_end=150
... (10개 모듈 생성)
```

**장점**:
- 모듈 이름으로 전략을 직관적으로 확인 가능
- 모듈 설정을 수정하면 해당 범위의 모든 블로그에 즉시 적용
- Flow에 모듈을 포함/제외하여 전략 조합 유연

**한계**:
- 생성/발행 모듈에는 이 패턴을 적용할 수 없음
- 모듈 수가 증가하여 관리 복잡도 상승
- 재발행/생성/발행 간 전략 동기화 여전히 불가
- 스케줄러/간격 설정이 모듈마다 따로 관리됨

**결론**: 이 패턴의 핵심("한 곳 설정, 전체 적용")을 살리되, 생성/발행/재발행을 **하나의 모듈로 통합 관리**하고, **스케줄러까지 통합**하는 설계가 필요하다.

---

## 2. 벤치마킹 인사이트

| 프로그램 | 핵심 패턴 | BlogAuto 차용 포인트 |
|---------|---------|---------------------|
| **SocialBee** | 카테고리별 비율 프리셋 -> 다수 프로필 적용 | 비율 기반 조절, 프로파일 재사용 |
| **WP Robot** | 캠페인별 드립피드, 포스트 수 + 간격 독립 설정 | 워밍업 드립피드, 점진적 확대 |
| **HubSpot** | Lifecycle Stage 기반 자동 전환 + Historical Optimization | 성장 단계 자동 판별, 재발행 시기 |
| **RecurPost** | 라이브러리별 재순환, Bulk Update | 에버그린 재순환, 일괄 설정 변경 |
| **Buffer** | Content Pillar 비율 배분 + AI 최적 시간 | 콘텐츠 유형별 비율 |
| **MarketMuse** | Content Inventory 감사, 갭 탐지 | 인벤토리 상/하한 이중 게이트 |
| **CoSchedule** | ReQueue 지능형 큐 + Light/Heavy 스펙트럼 | 빈 슬롯 자동 채움 |

### 도출 원칙

1. **프로파일 한 곳에서 정의 -> 다수 적용** (SocialBee, WordPress Multisite)
2. **이중 임계값 게이트**: min(생성 트리거) / max(생성 중단) (Programmatic SEO)
3. **점진적 워밍업**: 신규 블로그 드립피드 (WP Robot)
4. **콘텐츠 유형별 비율 자동 조절** (SocialBee, Buffer)
5. **에버그린 재순환 주기 관리** (RecurPost, HubSpot)
6. **중앙 스케줄러에서 실행 타이밍 통합 제어** (CoSchedule, Buffer)

---

## 3. 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Single Source of Truth** | 성장 전략 설정은 Growth Profile 모듈 한 곳에서만 관리 |
| **완전 대체 (Clean Break)** | 개별 모듈(재발행/생성/발행)의 스케줄러, interval_mode, schedule_matrix 등 스케줄링 관련 설정을 **코드에서 완전 제거**. Growth Profile이 유일한 스케줄러가 됨 |
| **모듈별 선택적 활성화** | 각 성장 구간에서 생성/발행/재발행 모듈을 **체크박스로 개별 활성화/비활성화** 가능. 활성화된 모듈만 해당 구간에서 동작 |
| **Flow 기반 적용** | Growth Profile 모듈이 포함된 Flow의 모든 블로그에 자동 적용 |
| **블로그 개별 설정 불필요** | 블로그에는 성장 관련 설정을 두지 않음 (`BlogGrowthSetting` -> deprecated) |
| **기본 템플릿 제공** | 시스템이 가이드라인 기본값을 제공, 사용자가 수정 또는 새로 생성 가능. 구간을 1개(0~무제한)로 설정하면 단순 테스트 용도로도 사용 가능 |
| **간격 설정 통일** | 재발행 모듈의 `interval_mode` 체계를 발행/생성에도 동일하게 차용. 각 모듈이 독립된 간격 설정을 가짐 |

---

## 4. Growth Profile 모듈 아키텍처

### 4-1. 전체 구조

Growth Profile은 단순한 "설정 로더"가 아니라 **스케줄러 + 오케스트레이터** 역할을 한다.
다른 모듈(생성/발행/재발행)은 자체 스케줄러와 간격 옵션이 **코드에서 완전 제거**되고, Growth Profile이 보내는 **"동작 신호"**에 따라 실행된다.

```
Flow "메인 전략"
+-- Growth Profile 모듈 (growth_profile 타입)   <-- 유일한 스케줄러 + 오케스트레이터
|   +-- 활성 시간대 (schedule_matrix) - 모듈 레벨 (전체 공통)
|   +-- 지터(jitter) 설정 - 모듈 레벨 (전체 공통)
|   +-- 성장 구간별 설정 (stages)
|   |   +-- [V] 생성 (generate): 활성화 체크박스 + 최소 보유 수 + 독립 간격
|   |   +-- [V] 발행 (publish): 활성화 체크박스 + 독립 간격
|   |   +-- [V] 재발행 (republish): 활성화 체크박스 + 독립 간격
|   +-- 워밍업 설정 (warmup)
|
+-- Prompt 모듈 (prompt 타입)       <-- 스케줄러 완전 제거됨 (Growth Profile이 제어)
+-- Publish 모듈 (publish 타입)     <-- 스케줄러 완전 제거됨 (Growth Profile이 제어)
+-- Republish 모듈 (republish 타입) <-- 스케줄러 완전 제거됨 (Growth Profile이 제어)
|
+-- Blogs: [Blog A (30글), Blog B (100글), Blog C (200글)]
    +-- 각 블로그의 total_post_count 기준으로 해당 stage 자동 매핑
```

**핵심 변경 포인트:**
- Growth Profile이 **유일한 스케줄러**이다 (개별 모듈의 스케줄러, interval_mode 등은 코드에서 완전 제거)
- 각 구간에서 생성/발행/재발행을 **체크박스로 개별 활성화/비활성화** 가능
- 활성화된 각 모듈은 **독립된 간격 설정(interval_mode, interval_minutes, daily_count)**을 가짐
- `publish_ratio`, `republish_ratio`, `execution_order`는 **제거** (각 모듈이 독립 간격이므로 비율/순서 불필요)

**적용 결과:**

| 블로그 | 누적 글 수 | 매핑 스테이지 | 생성 | 발행 | 재발행 |
|--------|-----------|-------------|------|------|--------|
| Blog A | 30글 | rapid_growth (급성장기) | 활성, 하루5회, 재고10 | 활성, 120분간격 | 활성, 하루3회 |
| Blog B | 100글 | growth (성장기) | 활성, 하루3회, 재고5 | 활성, 하루2회 | 활성, 하루3회 |
| Blog C | 200글 | stable (안정기) | 활성, 하루1회, 재고3 | 비활성 | 활성, 하루2회 |

### 4-2. ModuleType 추가

`module_types` 테이블에 새 레코드 추가:

```python
{
    "code": "growth_profile",
    "name": "성장 프로파일",
    "icon": "📈",
    "display_order": 0  # 가장 먼저 표시
}
```

> 참고: 현재 `ModuleType.get_default_types()`에는 prompt, generate, publish, republish, collect, data 6종이 정의되어 있다. `growth_profile`을 `display_order=0`으로 추가하여 가장 상단에 배치한다.

### 4-3. Flow 실행 순서에서의 위치

```
기존:   collect -> data -> republish -> prompt
변경:   growth_profile -> collect -> data -> prompt -> publish -> republish
              |
    가장 먼저 실행:
    1) 활성 시간대(schedule_matrix) 체크 -> 비활성 시간이면 Flow 전체 스킵
    2) 각 블로그의 현재 스테이지 결정
    3) 스테이지별 각 모듈의 enabled 상태 + 독립 간격을 컨텍스트에 주입
    4) 이후 모듈들에게 "동작 신호" 전달 (enabled=true인 모듈만)
```

Growth Profile 모듈은 **"유일한 스케줄러 + 오케스트레이터"** 역할이다:

- **스케줄러**: `schedule_matrix`로 활성 시간대를 확인하고, 각 모듈의 `interval_mode`에 따라 실행 간격을 **독립적으로** 계산하여 "지금 실행할 시점인지" 판단한다
- **오케스트레이터**: 각 블로그의 `StageParams`를 `FlowExecutionContext`에 저장하여, 이후 모듈이 참조할 수 있도록 한다
- **동작 신호**: 각 모듈의 `enabled` 상태와 개별 간격을 기반으로, "실행하라"는 트리거를 독립적으로 보낸다

---

## 5. 모듈 설정 상세 (settings JSONB)

### 5-1. 기본 구조

`schedule_matrix`와 `jitter`는 **모듈 레벨** (전체 공통)이고, 성장 구간별 세부 설정은 `stages` 배열에 들어간다.

```json
{
  "schedule_matrix": [
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false],
    [false,false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false]
  ],
  "jitter": {
    "enabled": true,
    "min_percent": -20,
    "max_percent": 30
  },
  "stages": [
    {
      "name": "rapid_growth",
      "label": "급성장기",
      "post_count_min": 0,
      "post_count_max": 50,
      "generate": {
        "enabled": true,
        "min_inventory": 10,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 5
      },
      "publish": {
        "enabled": true,
        "interval_mode": "manual",
        "interval_minutes": 120,
        "daily_count": null
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 3
      },
      "description": "빠른 콘텐츠 축적, 검색 노출 기반 구축"
    },
    {
      "name": "growth",
      "label": "성장기",
      "post_count_min": 51,
      "post_count_max": 150,
      "generate": {
        "enabled": true,
        "min_inventory": 5,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 3
      },
      "publish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 2
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 3
      },
      "description": "안정적 성장, 기존 글 최적화 병행"
    },
    {
      "name": "stable",
      "label": "안정기",
      "post_count_min": 151,
      "post_count_max": null,
      "generate": {
        "enabled": true,
        "min_inventory": 3,
        "interval_mode": "manual",
        "interval_minutes": 360,
        "daily_count": null
      },
      "publish": {
        "enabled": false,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": null
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 2
      },
      "description": "유지보수, 기존 콘텐츠 가치 극대화"
    }
  ],
  "warmup": {
    "enabled": true,
    "warmup_days": 14,
    "initial_daily_posts": 1,
    "max_daily_posts": 3,
    "ramp_rate": 0.5,
    "description": "신규 블로그 등록 후 워밍업 기간"
  }
}
```

### 5-2. 각 필드 설명

#### 모듈 레벨 필드 (전체 공통)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `schedule_matrix` | bool[][] | O | 7x24 매트릭스. 요일(월~일) x 시간(0~23시). `true`인 슬롯에서만 동작 |
| `jitter.enabled` | bool | O | 지터(랜덤 변동) 사용 여부 |
| `jitter.min_percent` | int | O | 간격에 적용할 최소 변동률 (예: -20 = 최대 20% 빠르게) |
| `jitter.max_percent` | int | O | 간격에 적용할 최대 변동률 (예: 30 = 최대 30% 느리게) |

> `schedule_matrix` 설명:
> - 배열의 첫 번째 요소 = 월요일, 마지막 = 일요일
> - 각 배열의 24개 값 = 0시~23시
> - `true` = 이 시간대에 동작 허용, `false` = 이 시간대에 동작 정지
> - 예시: `[false,...,false,true,true,...,true,false,false]` = 06시~21시만 활성

#### `stages` 배열 - 공통 필드

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | O | 스테이지 고유 이름 (내부 식별용) |
| `label` | string | O | 사용자에게 표시되는 이름 |
| `post_count_min` | int | O | 설정 적용 구간 시작 (누적 포스트 수 기준, inclusive) |
| `post_count_max` | int? | O | 설정 적용 구간 종료 (inclusive, `null` = 무제한) |
| `description` | string | - | 스테이지 설명 (UI 표시용) |

#### `generate` 객체 (생성 모듈 설정)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `enabled` | bool | O | 이 구간에서 생성 모듈 활성화 여부 (체크박스) |
| `min_inventory` | int | 조건 | `enabled=true` 일 때 필수. 최소 보유 포스트 수. 저장된 글 수가 이 값 미만이면 생성 시작 |
| `interval_mode` | string | 조건 | `enabled=true` 일 때 필수. 간격 설정 방식: `"manual"` 또는 `"auto"` |
| `interval_minutes` | int? | 조건 | `interval_mode="manual"` 일 때 필수. 분 단위 생성 간격 |
| `daily_count` | int? | 조건 | `interval_mode="auto"` 일 때 필수. 하루 생성 목표 횟수 |

> **생성 모듈 동작 규칙**:
> 1. `enabled=false`이면 이 구간에서 생성하지 않음
> 2. `enabled=true`이면: 저장된 포스트 수 < `min_inventory` -> 생성 시작
> 3. `interval_mode`에 따라 설정된 간격으로 반복 생성
> 4. 저장된 포스트 수 >= `min_inventory` -> 생성 정지
> 5. 발행으로 재고가 감소하여 다시 `min_inventory` 미만이 되면 -> 생성 재시작

#### `publish` 객체 (발행 모듈 설정)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `enabled` | bool | O | 이 구간에서 발행 모듈 활성화 여부 (체크박스) |
| `interval_mode` | string | 조건 | `enabled=true` 일 때 필수. 간격 설정 방식: `"manual"` 또는 `"auto"` |
| `interval_minutes` | int? | 조건 | `interval_mode="manual"` 일 때 필수. 분 단위 발행 간격 |
| `daily_count` | int? | 조건 | `interval_mode="auto"` 일 때 필수. 하루 발행 목표 횟수 |

#### `republish` 객체 (재발행 모듈 설정)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `enabled` | bool | O | 이 구간에서 재발행 모듈 활성화 여부 (체크박스) |
| `interval_mode` | string | 조건 | `enabled=true` 일 때 필수. 간격 설정 방식: `"manual"` 또는 `"auto"` |
| `interval_minutes` | int? | 조건 | `interval_mode="manual"` 일 때 필수. 분 단위 재발행 간격 |
| `daily_count` | int? | 조건 | `interval_mode="auto"` 일 때 필수. 하루 재발행 목표 횟수 |

> **interval_mode 설명 (모든 모듈 공통)**:
> - `"manual"` (시간으로 설정): 사용자가 분 단위 간격을 직접 입력. 예) 120분 -> 2시간마다 한 번
> - `"auto"` (횟수로 설정): 하루 목표 횟수를 입력하면 시스템이 활성 시간대를 기준으로 간격을 자동 계산
>   - 예) daily_count=5, 활성 시간대 16시간 -> 약 192분(3.2시간) 간격
>   - 계산식: `활성 시간(분) / daily_count = 간격(분)`
>
> 각 모듈(generate, publish, republish)이 독립된 interval_mode와 간격을 가지므로, 모듈 간 비율(publish_ratio/republish_ratio)이나 실행 순서(execution_order)는 불필요하다.
>
> **`enabled=false` 처리 규칙**: `enabled=false`이면 해당 모듈의 하위 필드(`interval_mode`, `interval_minutes`, `daily_count`, `min_inventory`)는 실행 시 무시된다. JSON에 값이 저장되어 있어도 참조하지 않으며, UI에서는 해당 영역이 그레이아웃 처리된다.

#### `warmup` 객체

> **적용 범위**: warmup은 **발행(publish)에만** 적용된다. 블로그 플랫폼(구글 블로거)이나 검색엔진(네이버, 구글)이 신규 블로그의 기계적 발행을 감지하는 것을 방지하기 위한 장치이므로, 외부에 노출되는 "발행" 동작만 제한한다.
> - **생성(generate)**: 영향 없음. 글 생성은 시스템 내부 동작이며 플랫폼에 노출되지 않으므로 제한할 이유가 없다.
> - **재발행(republish)**: 대상 아님. 신규 블로그는 워밍업 기간에 재발행할 기존 콘텐츠가 없다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `enabled` | bool | O | 워밍업 사용 여부 |
| `warmup_days` | int | O | 워밍업 기간 (일) |
| `initial_daily_posts` | int | O | 워밍업 시작 일일 **발행** 수 |
| `max_daily_posts` | int | O | 워밍업 기간 중 최대 일일 **발행** 수 |
| `ramp_rate` | float | O | 일일 증가율 (일당 추가 **발행** 수) |
| `description` | string | - | 워밍업 설명 (UI 표시용) |

### 5-3. 사용자 커스텀 예시

사용자가 4단계로 세분화하고, 각 구간에 다른 간격/동작 순서를 적용한 경우:

```json
{
  "schedule_matrix": [
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false],
    [false,false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false,false],
    [false,false,false,false,false,false,false,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false,false]
  ],
  "jitter": {
    "enabled": true,
    "min_percent": -15,
    "max_percent": 25
  },
  "stages": [
    {
      "name": "seed",
      "label": "시드기",
      "post_count_min": 0,
      "post_count_max": 30,
      "generate": {
        "enabled": true,
        "min_inventory": 15,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 8
      },
      "publish": {
        "enabled": true,
        "interval_mode": "manual",
        "interval_minutes": 90,
        "daily_count": null
      },
      "republish": {
        "enabled": false,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": null
      },
      "description": "초기 콘텐츠 축적, 재발행할 글이 부족하므로 비활성"
    },
    {
      "name": "rapid_growth",
      "label": "급성장기",
      "post_count_min": 31,
      "post_count_max": 100,
      "generate": {
        "enabled": true,
        "min_inventory": 10,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 6
      },
      "publish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 5
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 2
      },
      "description": "빠른 성장, 발행 위주 + 재발행 시작"
    },
    {
      "name": "growth",
      "label": "성장기",
      "post_count_min": 101,
      "post_count_max": 300,
      "generate": {
        "enabled": true,
        "min_inventory": 5,
        "interval_mode": "manual",
        "interval_minutes": 240,
        "daily_count": null
      },
      "publish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 2
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 4
      },
      "description": "안정적 성장, 기존 글 최적화 비중 높임"
    },
    {
      "name": "mature",
      "label": "성숙기",
      "post_count_min": 301,
      "post_count_max": null,
      "generate": {
        "enabled": true,
        "min_inventory": 2,
        "interval_mode": "manual",
        "interval_minutes": 480,
        "daily_count": null
      },
      "publish": {
        "enabled": false,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": null
      },
      "republish": {
        "enabled": true,
        "interval_mode": "auto",
        "interval_minutes": null,
        "daily_count": 3
      },
      "description": "유지보수, 재발행 중심 운영"
    }
  ],
  "warmup": {
    "enabled": false
  }
}
```

> **참고**: `warmup`을 사용하지 않는 경우 `"enabled": false`로 설정. 생략 시 기본값 `{"enabled": false}`가 적용된다.

### 5-4. 시스템 기본 프로파일

시스템이 제공하는 기본 프로파일 3종:

| 프로파일 | 설명 | 급성장기 발행 간격 | 급성장기 재발행 간격 | 급성장기 생성 | 안정기 최소 재고 |
|---------|------|------------------|-------------------|-------------|---------------|
| **공격적 성장 (Aggressive)** | 급성장기에 발행 빈도 극대화, 재고 넉넉하게 유지 | 하루 8회 | 하루 3회 | 하루 8회, 재고15 | 5개 |
| **균형 성장 (Balanced)** | 위 5-1의 기본 구조 (기본값), 균형 잡힌 설정 | 120분 간격 | 하루 3회 | 하루 5회, 재고10 | 3개 |
| **보수적 운영 (Conservative)** | 안정적 운영 위주, 느린 생성 | 하루 2회 | 하루 2회 | 하루 2회, 재고5 | 2개 |

사용자는 기본 프로파일을 선택하여 시작하고, 필요에 따라 스테이지 추가/수정/삭제 및 각 모듈의 활성화/비활성화가 가능하다.

### 5-5. interval_mode 자동 간격 계산 상세

`interval_mode="auto"` 일 때 시스템이 간격을 자동 계산하는 방법. **각 모듈(generate, publish, republish)의 간격이 독립적으로 계산**된다.

```
예시: 급성장기 구간 (schedule_matrix의 오늘 활성 시간 = 06~21시 = 16시간 = 960분)

[발행 모듈] interval_mode="manual", interval_minutes=120
  -> 기본 간격 = 120분 (사용자 지정값 그대로)
  -> jitter 적용: 96분 ~ 156분 사이 랜덤값

[재발행 모듈] interval_mode="auto", daily_count=3
  -> 기본 간격 = 960 / 3 = 320분 (약 5.3시간)
  -> jitter 적용: 256분 ~ 416분 사이 랜덤값

[생성 모듈] interval_mode="auto", daily_count=5
  -> 기본 간격 = 960 / 5 = 192분 (약 3.2시간)
  -> jitter 적용: 153.6분 ~ 249.6분 사이 랜덤값
  -> 단, min_inventory 조건이 추가로 적용 (재고 충분하면 생성 정지)

jitter 계산 (enabled=true, min_percent=-20, max_percent=30):
  최소 간격 = 기본 간격 * (1 + (-20/100)) = 기본 간격 * 0.8
  최대 간격 = 기본 간격 * (1 + (30/100)) = 기본 간격 * 1.3
```

> 각 모듈이 독립된 간격을 가지므로, 발행과 재발행이 서로 다른 타이밍에 실행된다.
> 이는 비율(publish_ratio/republish_ratio)이나 실행 순서(execution_order) 없이도 자연스러운 활동 패턴을 만든다.

---

## 6. 실행 흐름

### 6-1. Growth Profile의 스케줄러 역할

Growth Profile이 Flow 실행의 **스케줄러 + 오케스트레이터**로 동작하는 전체 흐름:

```
_execute_flow_background() 시작
|
+-- Step 0: Growth Profile 스케줄러 (핵심 변경)
|   +-- Flow에 growth_profile 타입 모듈이 있는지 확인
|   +-- 있으면:
|   |   +-- (1) 활성 시간대 체크 (schedule_matrix)
|   |   |   +-- 현재 요일+시간이 schedule_matrix에서 true인지 확인
|   |   |   +-- false이면: "비활성 시간" -> Flow 실행 스킵 (다음 스케줄까지 대기)
|   |   |   +-- true이면: 계속 진행
|   |   |
|   |   +-- (2) 각 블로그의 성장 구간(stage) 결정
|   |   |   +-- blog.total_post_count 조회
|   |   |   +-- settings.stages에서 매칭되는 stage 찾기
|   |   |   +-- FlowExecutionContext에 {blog_id: StageParams} 저장
|   |   |
|   |   +-- (3) 각 모듈의 활성화 상태 + 간격 판단
|   |   |   +-- 각 블로그의 stage에서 generate.enabled / publish.enabled / republish.enabled 확인
|   |   |   +-- 활성화된 모듈만 개별 interval_mode 확인
|   |   |   +-- 마지막 실행 시각으로부터 해당 모듈의 간격이 경과했는지 체크
|   |   |   +-- jitter 적용하여 실제 간격 계산
|   |   |   +-- 간격 미경과: 해당 모듈 스킵
|   |   |   +-- 간격 경과: 실행 대상으로 포함
|   |   |
|   |   +-- (4) 생성 트리거 판단 (generate.enabled=true인 경우만)
|   |       +-- 각 블로그의 재고 확인
|   |       +-- 재고 < generate.min_inventory: 생성 트리거 ON
|   |       +-- 재고 >= generate.min_inventory: 생성 트리거 OFF
|   |       +-- generate.interval_mode에 따라 생성 간격 체크
|   |
|   +-- 없으면: Growth Profile 필수 (v3.0에서는 개별 모듈에 스케줄러가 없음)
|
+-- Step 1: collect 모듈 실행 (기존과 동일)
+-- Step 2: data 모듈 실행 (기존과 동일)
|
+-- Step 3: prompt(생성) 모듈 실행
|   +-- 각 블로그별:
|       +-- FlowExecutionContext에서 stage_params 조회
|       +-- generate.enabled=false이면 스킵
|       +-- 생성 트리거가 ON인 블로그만 실행
|       +-- generate.interval_mode에 따라 간격 체크
|       +-- 재고 >= generate.min_inventory이면 즉시 정지
|
+-- Step 4: publish(발행) 모듈 실행 (독립)
|   +-- 각 블로그별:
|       +-- stage_params에서 publish.enabled 확인
|       +-- publish.enabled=false이면 스킵
|       +-- publish.interval_mode에 따라 계산된 간격으로 동작
|
+-- Step 5: republish(재발행) 모듈 실행 (독립)
    +-- 각 블로그별:
        +-- stage_params에서 republish.enabled 확인
        +-- republish.enabled=false이면 스킵
        +-- republish.interval_mode에 따라 계산된 간격으로 동작
```

> **v2.0과의 차이**: 발행과 재발행이 `publish_ratio/execution_order` 기반으로 묶여 실행되던 것에서, 각각 독립된 스텝으로 분리되어 자체 간격에 따라 실행된다.

### 6-2. FlowExecutionContext 구조

```python
@dataclass
class ModuleIntervalParams:
    """개별 모듈(generate/publish/republish)의 간격 파라미터"""
    enabled: bool
    interval_mode: Optional[str]          # "manual" 또는 "auto"
    interval_minutes: Optional[int]       # manual 모드 시
    daily_count: Optional[int]            # auto 모드 시
    computed_interval: Optional[int]      # 최종 계산된 간격 (분). auto면 시스템 계산값
    min_inventory: Optional[int] = None   # generate 전용: 최소 보유 포스트 수


@dataclass
class StageParams:
    """블로그에 적용된 성장 단계 파라미터"""
    stage_name: str
    stage_label: str

    # 각 모듈별 독립 설정
    generate: ModuleIntervalParams
    publish: ModuleIntervalParams
    republish: ModuleIntervalParams


@dataclass
class FlowExecutionContext:
    """Flow 실행 시 공유되는 컨텍스트"""
    flow_id: int
    growth_profile: Optional[dict]       # Growth Profile 모듈 settings 원본
    schedule_matrix: Optional[list]      # 7x24 활성 시간대 매트릭스
    jitter: Optional[dict]               # 지터 설정
    blog_stages: Dict[int, StageParams]  # {blog_id: StageParams}

    def get_stage_for_blog(self, blog_id: int) -> Optional[StageParams]:
        """블로그 ID에 해당하는 스테이지 파라미터 반환"""
        return self.blog_stages.get(blog_id)

    def has_growth_profile(self) -> bool:
        """Growth Profile이 설정되어 있는지 확인"""
        return self.growth_profile is not None

    def is_active_time(self, weekday: int, hour: int) -> bool:
        """현재 시간이 활성 시간대인지 확인 (weekday: 0=월, 6=일)"""
        if self.schedule_matrix is None:
            return True  # schedule_matrix 미설정 시 항상 활성
        return self.schedule_matrix[weekday][hour]
```

> `FlowExecutionContext`는 메모리에서만 사용되는 임시 객체이다. DB에 저장하지 않는다. Flow 실행이 시작되면 생성되고, 실행이 끝나면 폐기된다.

### 6-3. 모듈별 독립 실행 로직 (핵심 로직)

v3.0에서는 발행과 재발행이 **독립된 간격**으로 각각 실행된다. `publish_ratio`, `republish_ratio`, `execution_order`는 제거되었다.

```
각 모듈이 자체 간격에 따라 독립적으로 실행:

[발행 모듈]
  publish.enabled = true
  publish.interval_mode = "manual"
  publish.interval_minutes = 120
  -> 마지막 발행 시각 + 120분(+jitter) 경과 시 발행 1건 실행
  -> 재고(저장된 포스트)가 있을 때만 발행

[재발행 모듈]
  republish.enabled = true
  republish.interval_mode = "auto"
  republish.daily_count = 3
  -> 활성 시간 960분 / 3 = 320분 간격(+jitter)으로 재발행 1건 실행
  -> 재발행 대상 글이 있을 때만 재발행

[생성 모듈]
  generate.enabled = true
  generate.min_inventory = 10
  generate.interval_mode = "auto"
  generate.daily_count = 5
  -> 재고 < 10일 때만 생성 트리거
  -> 192분 간격(+jitter)으로 생성 1건 실행
  -> 재고 >= 10이면 생성 정지
```

**독립 실행의 장점:**

```
1. 단순성: 비율 계산이나 실행 큐 관리가 불필요
2. 유연성: 각 모듈을 구간별로 개별 활성화/비활성화 가능
   예) 안정기에 발행을 끄고 재발행만 동작
3. 자연스러운 패턴: 발행과 재발행이 서로 다른 타이밍에 실행되어 봇 탐지 회피
4. 직관적 설정: "발행은 하루 3회, 재발행은 하루 5회"처럼 명확한 의도 표현
```

**재고 부족 시 동작:**

```
발행 간격이 도래했으나 재고가 0이면?
  -> 발행 스킵 (다음 간격까지 대기)
  -> generate.enabled=true이면 생성 모듈이 자동으로 재고 보충
  -> 재고가 확보되면 다음 발행 간격에서 정상 발행
```

### 6-4. 생성 모듈 동작 메커니즘

생성 모듈은 발행/재발행과 다른 동작 규칙을 가진다. 핵심은 **"최소 보유 수(min_inventory) 기반 트리거"**이다.

```
+-- 블로그별 생성 동작 판단
|
+-- 현재 저장 포스트 수 조회 (inventory_count)
|
+-- inventory_count < min_inventory ?
|   |
|   +-- YES: 생성 필요
|   |   +-- generate.interval_mode 확인
|   |   +-- "manual": generate.interval_minutes 간격으로 생성
|   |   +-- "auto": generate.daily_count 기반 자동 간격으로 생성
|   |   +-- 마지막 생성 시각 + 간격 <= 현재 시각 이면 생성 실행
|   |   +-- 생성 1건 완료
|   |   +-- 다시 재고 체크: 여전히 부족하면 다음 간격에 또 생성
|   |
|   +-- NO: 생성 불필요
|       +-- 생성 정지 (다음 스케줄까지 대기)
|       +-- 발행으로 재고가 감소하면 다시 체크
```

**예시 시나리오:**

```
설정: min_inventory=20, generate.interval_mode="auto", generate.daily_count=5

시점 1: 재고 25개 -> 25 >= 20 -> 생성 정지
시점 2: 발행 7건 실행 -> 재고 18개 -> 18 < 20 -> 생성 시작
시점 3: 생성 간격(약 3시간)마다 1건씩 생성
시점 4: 재고 20개 도달 -> 생성 정지
시점 5: 발행 3건 실행 -> 재고 17개 -> 다시 생성 시작
... (반복)
```

이 구조 덕분에 항상 `min_inventory` 이상의 재고를 유지하면서, 과도한 생성을 방지한다.

---

## 7. 기존 시스템과의 호환성

### 7-1. 완전 대체 (Clean Break)

v3.0에서는 개별 모듈의 스케줄러가 **코드에서 완전 제거**된다. Growth Profile이 유일한 스케줄러이며, 하위 호환 모드는 없다.

| 기존 시스템 | v3.0 처리 방식 |
|-----------|--------------|
| `Module.post_range_start/end` | Growth Profile의 `post_count_min/max`로 완전 대체. 기존 컬럼은 제거 대상 |
| `BlogGrowthSetting` | deprecated. Growth Profile로 완전 대체 |
| `Module.settings.inventory` | Growth Profile의 `generate.min_inventory`로 완전 대체 |
| 재발행 모듈의 `interval_mode` | 코드에서 제거. Growth Profile의 `republish.interval_mode`가 유일한 설정 |
| 생성 모듈의 자체 트리거 로직 | 코드에서 제거. Growth Profile의 `generate` 설정이 유일한 설정 |
| 각 모듈의 개별 스케줄러 | 코드에서 완전 제거. Growth Profile이 유일한 스케줄러 |

> 핵심: Growth Profile을 구간 1개(post_count_min=0, post_count_max=null)로 설정하면, 모든 블로그에 동일한 설정이 적용되어 기존의 단순한 동작과 동일한 효과를 얻을 수 있다. 별도의 하위 호환 모드가 불필요한 이유이다.

### 7-2. BlogGrowthSetting 마이그레이션 경로

```
단계 1 (마이그레이션):
  - 마이그레이션 스크립트로 기존 BlogGrowthSetting -> Growth Profile 자동 변환
  - 기존 블로그별 설정을 분석하여 적절한 stages 배열 생성
  - 변환 완료 후 BlogGrowthSetting deprecated 처리

단계 2 (제거):
  - InventoryTrigger의 BlogGrowthSetting 폴백 로직 제거
  - Growth Profile만 참조하도록 코드 정리
  - BlogGrowthSetting 테이블 제거 (Alembic 마이그레이션)

※ 주의: 여기서의 "단계 1/2"는 Section 10의 "Phase A~E"와 무관한 마이그레이션 순서임
```

### 7-3. 기존 post_range의 마이그레이션

v3.0에서는 Growth Profile이 필수이며, 개별 모듈의 `post_range`는 제거된다.

```
마이그레이션 전략:

기존 설정:
  재발행 모듈 "RV-1~50"   -> post_range_start=1, post_range_end=50
  재발행 모듈 "RV-51~100"  -> post_range_start=51, post_range_end=100

변환 후:
  Growth Profile 1개로 통합:
  stages[0]: post_count_min=1,  post_count_max=50   (급성장기)
  stages[1]: post_count_min=51, post_count_max=100   (성장기)
  -> 각 구간별로 republish.enabled, publish.enabled 등을 설정
  -> 기존 10개 모듈 -> Growth Profile 1개로 단순화

자동 변환 스크립트:
  - 기존 post_range 기반 모듈들을 분석
  - Growth Profile의 stages 배열로 자동 변환
  - 변환 후 기존 모듈의 post_range 컬럼 제거
```

### 7-4. 개별 모듈 스케줄러 제거 명세

v3.0에서 개별 모듈의 스케줄링 관련 설정을 **코드에서 완전 제거**한다. 구체적인 제거 대상:

```
재발행 모듈 (republish):
  제거 대상:
    - Module.settings의 interval_mode, interval_minutes, daily_count
    - Module.settings의 schedule_matrix (자체 활성 시간대)
    - 모듈 편집 UI의 간격/스케줄 설정 영역
  코드 파일:
    - app/routers/flows_execute.py: republish 자체 간격 계산 로직 제거
    - app/static/js/modules/: republish 간격 설정 UI 제거

생성 모듈 (prompt):
  제거 대상:
    - Module.settings의 inventory 관련 설정
    - InventoryTrigger의 자체 임계값 판단 로직
    - 모듈 편집 UI의 재고/간격 설정 영역
  코드 파일:
    - app/services/generation/inventory_trigger.py: 자체 임계값 로직 -> Growth Profile 참조로 변경
    - app/services/generation/flow_generate_executor.py: 자체 트리거 -> Growth Profile 참조로 변경

발행 모듈 (publish):
  - 신규 구현 시 자체 스케줄러 없이 설계
  - Growth Profile의 publish.enabled + publish.interval_mode만 참조

DB 마이그레이션:
  - Module.post_range_start, Module.post_range_end 컬럼 제거
  - BlogGrowthSetting 테이블 deprecated 처리 (향후 제거)
  - 기존 개별 모듈의 스케줄링 settings -> Growth Profile 자동 변환 스크립트 제공
```

---

## 8. 데이터 모델

### 8-1. ModuleType 추가

```sql
INSERT INTO module_types (code, name, icon, display_order)
VALUES ('growth_profile', '성장 프로파일', '📈', 0);
```

`ModuleType.get_default_types()`에도 추가:

```python
{
    "code": "growth_profile",
    "name": "성장 프로파일",
    "icon": "📈",
    "display_order": 0
}
```

### 8-2. Module.settings 구조

기존 `Module` 모델 변경 없음. `settings` JSONB 컬럼에 [5-1. 기본 구조](#5-1-기본-구조)의 JSON을 저장한다.

```python
# 기존 Module 모델 (변경 없음)
class Module(Base):
    __tablename__ = "modules"
    ...
    settings = Column(JSONB, default=dict, comment="타입별 추가 설정")
    ...
```

`growth_profile` 타입 모듈의 `settings`에 schedule_matrix/jitter/stages/warmup 구조가 저장되는 방식이므로, 기존 Module 테이블에 컬럼 추가나 마이그레이션이 필요 없다.

### 8-3. FlowExecutionContext (메모리 전용, DB 저장 없음)

실행 시에만 사용되는 임시 컨텍스트이다. DB에 별도 테이블이나 컬럼을 추가하지 않는다.

```python
# app/services/generation/flow_execution_context.py (~120줄)
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class ModuleIntervalParams:
    """개별 모듈(generate/publish/republish)의 간격 파라미터"""
    enabled: bool
    interval_mode: Optional[str] = None          # "manual" 또는 "auto"
    interval_minutes: Optional[int] = None       # manual 모드 시
    daily_count: Optional[int] = None            # auto 모드 시
    computed_interval: Optional[int] = None      # 최종 계산된 간격 (분)
    min_inventory: Optional[int] = None          # generate 전용


@dataclass
class StageParams:
    """블로그에 적용된 성장 단계 파라미터"""
    stage_name: str
    stage_label: str

    # 각 모듈별 독립 설정
    generate: ModuleIntervalParams
    publish: ModuleIntervalParams
    republish: ModuleIntervalParams


@dataclass
class FlowExecutionContext:
    """Flow 실행 시 공유되는 컨텍스트"""
    flow_id: int
    growth_profile: Optional[dict] = None
    schedule_matrix: Optional[list] = None
    jitter: Optional[dict] = None
    blog_stages: Dict[int, StageParams] = field(default_factory=dict)

    def get_stage_for_blog(self, blog_id: int) -> Optional[StageParams]:
        return self.blog_stages.get(blog_id)

    def has_growth_profile(self) -> bool:
        return self.growth_profile is not None

    def is_active_time(self, weekday: int, hour: int) -> bool:
        if self.schedule_matrix is None:
            return True
        return self.schedule_matrix[weekday][hour]
```

### 8-4. 시스템 기본 프로파일 저장

**방안 비교:**

| 방안 | 장점 | 단점 |
|------|------|------|
| A: seed_data로 Module 레코드 삽입 | DB에서 직접 조회 가능 | 설치 시 마이그레이션 필요, user_id 필요 |
| **B: 코드에 DEFAULT_PROFILES 딕셔너리** | DB 의존 없음, 코드로 관리 | 변경 시 배포 필요 |

**결정: 방안 B 채택**

설치 시 DB 마이그레이션이 불필요하고, 코드에서 직접 관리하여 버전 관리가 용이하다.

```python
# 파일 위치: app/services/generation/growth_profile_defaults.py

DEFAULT_PROFILES = {
    "aggressive": { ... },   # 공격적 성장
    "balanced": { ... },     # 균형 성장 (기본값)
    "conservative": { ... }, # 보수적 운영
}
```

---

## 9. UI/UX 설계

### 9-1. Growth Profile 모듈 생성/편집 UI

**모듈 생성 흐름:**

```
모듈 타입 선택
  +-- "성장 프로파일" 선택
      +-- 기본 프로파일 3종 중 선택하여 시작
          +-- 공격적 성장 (Aggressive)
          +-- 균형 성장 (Balanced) <-- 기본 선택
          +-- 보수적 운영 (Conservative)
              +-- 성장 프로파일 편집 UI로 이동
```

**편집 UI 전체 레이아웃:**

```
+-- 성장 프로파일 설정
|
|   [모듈 레벨 설정]
|   +-- 활성 시간대 스케줄러 (7x24 매트릭스 그리드)
|   |   +------+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+
|   |   |      |00|01|02|03|04|05|06|07|08|09|10|11|12|13|14|15|16|17|18|19|20|21|22|23|
|   |   +------+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+
|   |   | 월   |  |  |  |  |  |  |OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|  |  |
|   |   | 화   |  |  |  |  |  |  |OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|OO|  |  |
|   |   | ...  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|   |   +------+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+
|   |   (클릭으로 셀 토글, 드래그로 범위 선택)
|   |   [전체 선택] [전체 해제] [평일 선택] [주말 선택]
|   |
|   +-- 지터(랜덤 변동) 설정
|       [V] 지터 사용
|       최소 변동: [-20]%  최대 변동: [30]%
|
|   [성장 구간 설정]
|   +-- 구간 1: 급성장기
|   |   +-- 설정 적용 구간: [0] ~ [50] (누적 포스트 수)
|   |   +-- 활성 모듈:
|   |   |   [V] 생성 (Generate)
|   |   |       최소 보유 포스트 수: [10]
|   |   |       생성 간격:
|   |   |       ( ) 시간으로 설정 (manual)  [___]분
|   |   |       (O) 횟수로 설정 (auto)     하루 [5]회
|   |   |
|   |   |   [V] 발행 (Publish)
|   |   |       발행 간격:
|   |   |       (O) 시간으로 설정 (manual)  [120]분
|   |   |       ( ) 횟수로 설정 (auto)     하루 [__]회
|   |   |
|   |   |   [V] 재발행 (Republish)
|   |   |       재발행 간격:
|   |   |       ( ) 시간으로 설정 (manual)  [___]분
|   |   |       (O) 횟수로 설정 (auto)     하루 [3]회
|   |   |
|   |   [삭제]
|   |
|   +-- 구간 2: 성장기
|   |   +-- 설정 적용 구간: [51] ~ [150] (누적 포스트 수)
|   |   +-- 활성 모듈:
|   |   |   [V] 생성 (Generate)  ... (독립 간격 설정)
|   |   |   [V] 발행 (Publish)   ... (독립 간격 설정)
|   |   |   [V] 재발행 (Republish) ... (독립 간격 설정)
|   |   [삭제]
|   |
|   +-- 구간 3: 안정기
|   |   +-- 설정 적용 구간: [151] ~ [무제한] (누적 포스트 수)
|   |   +-- 활성 모듈:
|   |   |   [V] 생성 (Generate)  ... (독립 간격 설정)
|   |   |   [ ] 발행 (Publish)   -- 비활성 (체크 해제)
|   |   |   [V] 재발행 (Republish) ... (독립 간격 설정)
|   |   [삭제]
|   |
|   +-- [+ 구간 추가] 버튼
|       클릭 시 새 구간이 아래에 추가됨
|       이전 구간의 post_count_max + 1이 자동으로 post_count_min에 입력됨
|
|   [워밍업 설정]
|   +-- [V] 워밍업 사용
|       워밍업 기간: [14]일
|       시작 일일 발행 수: [1]건
|       최대 일일 발행 수: [3]건
|       증가율: [0.5] (일당 추가)
|
|   [프리뷰]
|   +-- "Blog A (30글) -> 급성장기: 생성(하루5회,재고10) / 발행(120분) / 재발행(하루3회)"
|   +-- "Blog B (100글) -> 성장기: 생성(하루3회,재고5) / 발행(하루2회) / 재발행(하루3회)"
|   +-- "Blog C (200글) -> 안정기: 생성(360분,재고3) / 발행(비활성) / 재발행(하루2회)"
```

**스테이지 편집 UI 기능 요약:**

| 기능 | 설명 |
|------|------|
| 구간 추가 (+) | [+ 구간 추가] 버튼으로 새 성장 구간 삽입. 이전 구간의 종료값+1이 시작값에 자동 입력 |
| 구간 삭제 | 최소 1개는 유지. 삭제 시 확인 다이얼로그 표시 |
| 구간 수정 | 인라인 편집, 각 필드 수정 가능 |
| 모듈 활성화 체크박스 | 각 구간에서 생성/발행/재발행 모듈을 개별 활성화/비활성화. 체크 해제 시 해당 모듈의 간격 설정 영역이 비활성화(그레이아웃)됨 |
| 간격 모드 전환 | 각 모듈별로 라디오 버튼으로 "시간으로 설정" / "횟수로 설정" 전환. 비활성 모드의 입력은 자동 비활성화 |
| 범위 연속성 검증 | 이전 스테이지의 `post_count_max + 1 = 다음 스테이지의 post_count_min` 자동 검증 |
| 활성 시간대 매트릭스 | 7일 x 24시간 그리드. 클릭/드래그로 셀 토글. 빠른 선택 버튼 제공 |
| 생성 설정 | 체크박스 활성화 시 최소 보유 수 입력 + 생성 간격 (시간/횟수 라디오) |
| 프리뷰 | Flow에 연결된 블로그별 적용 결과 실시간 미리보기 (각 모듈의 활성/비활성 + 간격 표시) |
| 워밍업 토글 | 워밍업 설정 활성화/비활성화 |

### 9-2. Flow 편집 UI에서의 표시

```
Flow "메인 전략" 편집 화면
+------------------------------------------------------+
|  [성장 전략 적용됨: 균형 성장]  (배지)                 |
+------------------------------------------------------+
|  모듈 목록:                                           |
|  1. 성장 프로파일 - 균형 성장 (3단계)                 |
|     활성시간: 06~21시(평일), 07~20시(주말)            |
|  2. 수집 - 네이버 블로그                              |
|  3. 프롬프트 - GPT-4 생성                             |
|     (스케줄: Growth Profile에 의해 관리됨)            |
|  4. 재발행 - 기본 설정                                |
|     (스케줄: Growth Profile에 의해 관리됨)            |
+------------------------------------------------------+
|  블로그 목록:                                         |
|  - Blog A (30글)  [급성장기]                          |
|    생성:하루5회 / 발행:120분 / 재발행:하루3회          |
|  - Blog B (100글) [성장기]                            |
|    생성:하루3회 / 발행:하루2회 / 재발행:하루3회        |
|  - Blog C (200글) [안정기]                            |
|    생성:360분 / 발행:비활성 / 재발행:하루2회           |
+------------------------------------------------------+
```

### 9-3. 대시보드 통합

| 위젯 | 표시 내용 |
|------|---------|
| **성장 단계 현황** | 각 단계별 블로그 수 집계 (급성장기: 45개, 성장기: 30개, 안정기: 25개) |
| **스테이지 전환 임박** | "Blog A: 47/50글 -> 곧 성장기 전환" 알림 |
| **블로그별 현재 단계** | 블로그 목록에 현재 성장 단계 배지 + 적용 간격 표시 |
| **활성 시간대 현황** | 현재 활성/비활성 상태, 다음 활성 시간까지 남은 시간 |
| **재고 현황** | 각 블로그의 재고 vs min_inventory 비교 바 차트 |

---

## 10. 구현 단계

### Phase A: 기반 구조 (코어)

| 파일 | 작업 내용 | 예상 줄 수 |
|------|---------|-----------|
| `module_types` seed data | `growth_profile` 타입 추가 | SQL 1줄 |
| `app/services/generation/growth_profile_defaults.py` | 기본 프로파일 3종 정의 (schedule_matrix, jitter, stages, warmup 포함) | ~120줄 |
| `app/services/generation/growth_profile_resolver.py` | 블로그 → 스테이지 매핑, 간격 계산, 활성 시간 체크 로직 | ~180줄 |
| `app/services/generation/flow_execution_context.py` | `FlowExecutionContext`, `StageParams`, `ModuleIntervalParams` 데이터클래스 | ~120줄 |

**기존 코드 재사용 참조:**
- `FlowExecutionState` 모델에 이미 `last_executed_at`, `next_execution_at` 컬럼 존재 → 마지막 실행 시각을 별도 저장할 필요 없음
- `FlowExecutionState.calculate_next_execution()`: jitter 적용 로직 이미 구현 (`random.uniform()` 사용)
- `FlowExecutionState.is_in_active_window()`: schedule_matrix 활성 시간 체크 이미 구현
- `FlowExecutionState._adjust_to_active_window()`: 비활성 시간대 → 다음 활성 슬롯으로 보정 이미 구현
- **GrowthProfileResolver는 위 기존 로직을 호출하는 상위 조율자로 구현** (중복 구현 금지)
- `Module.calculated_interval_minutes`의 auto 계산 버그 수정 필요: 현재 `1440 / daily_count` (24시간 고정) → `active_hours * 60 / daily_count` (활성 시간 기반)로 수정

**Phase A 완료 기준:**
- 단위 테스트로 `GrowthProfileResolver`가 블로그 포스트 수에 따라 올바른 스테이지를 반환하는지 검증 통과
- `interval_mode`에 따른 간격 계산이 올바른지 검증 통과 (auto 모드: 활성 시간 기반 검증)
- `schedule_matrix` 활성 시간 체크 로직 검증 통과
- **경계값 테스트 필수**: `post_count_max` inclusive 규칙 검증 (50글 = 해당 스테이지, 51글 = 다음 스테이지)
- stages 배열의 **연속성 검증**: 구간 간 빈 범위나 겹침이 없는지 validation 로직 + 테스트

### Phase B: Flow 실행 연동 (스케줄러 통합)

| 파일 | 작업 내용 | 변경량 |
|------|---------|--------|
| `app/routers/flows_execute.py` | Growth Profile 스케줄러 로드 + 활성 시간 체크 + 컨텍스트 주입 (Step 0 추가) | +60줄 |
| `app/services/generation/inventory_trigger.py` | `FlowExecutionContext`에서 `generate.min_inventory` + `generate.interval_mode` 읽기. 자체 임계값 폴백 로직 제거 | 변경 |
| `app/services/generation/flow_generate_executor.py` | 컨텍스트 기반 생성 트리거 + 간격 전달. `generate.enabled` 체크 추가 | +20줄 |
| `app/api/flows.py` 또는 `flows_execute.py` | **GP 1-per-flow 제한 검증**: Flow에 growth_profile 모듈 추가 시 중복 체크 | +15줄 |
| `app/routers/flows_execute.py` | **GP 미설정 Flow 거부**: Growth Profile 없는 Flow 실행 시 즉시 중단 + 에러 로그 | +10줄 |

**GP 미설정 Flow 처리 (사용자 결정 W4):**
```
Flow 실행 시작 → Growth Profile 모듈 존재 여부 확인
  → 없음: 실행 즉시 중단 + "이 Flow에 Growth Profile이 설정되지 않았습니다" 에러 반환
  → 있음: 정상 실행 계속
```

**FlowExecutionState 블로그 레벨 추적 검토:**
- 현재 FlowExecutionState는 `(flow_id, module_id)` 단위로 추적
- Growth Profile은 블로그별로 다른 스테이지/간격이 적용되므로, 블로그별 마지막 실행 시각 추적이 필요할 수 있음
- Phase B 구현 시 `(flow_id, module_id, blog_id)` 확장 필요 여부를 판단하고, 필요시 Alembic 마이그레이션 추가

**flows_execute.py 파일 크기 참고 (사용자 결정 W6, W10):**
- 현재 1162줄로 500줄 제한 초과 상태
- Growth Profile 코드 추가 시 1200줄+ 예상 → 리팩토링 별도 문서에서 계획
- 단, 1000줄 이상이 되면 리팩토링 우선 실행

**Phase B 완료 기준:**
- Growth Profile이 있는 Flow에서 schedule_matrix 기반 활성/비활성 판단이 올바른지 검증
- `generate.enabled=true`인 경우만 생성 모듈이 실행되는지 검증
- prompt 모듈 실행 시 `generate.min_inventory` + `generate.interval_mode`가 올바르게 전달되는지 검증
- **Growth Profile 없는 Flow 실행 시 즉시 중단되는지 검증**
- **Flow당 growth_profile 모듈이 2개 이상 추가되지 않는지 검증**

### Phase C: 재발행 연동 (독립 간격 + 개별 모듈 스케줄러 제거 + 레거시 컬럼 정리)

| 파일 | 작업 내용 | 변경량 |
|------|---------|--------|
| `app/routers/flows_execute.py` | republish 실행부에서 Growth Profile의 `republish.enabled` + `republish.interval_mode` 참조 | +40줄 |
| 재발행 서비스 | 자체 interval_mode/schedule 로직 제거, Growth Profile 간격만 참조 | 변경 |
| Alembic 마이그레이션 | `Module.post_range_start`, `Module.post_range_end` 컬럼 제거 | 마이그레이션 |
| `app/models/module.py` | `post_range_start`, `post_range_end` 컬럼 정의 + 관련 프로퍼티 제거 | 변경 |

**post_range 컬럼 제거 절차:**
```
1. Growth Profile로 기존 post_range 데이터 마이그레이션 완료 확인 (Phase M 참조)
2. 코드에서 post_range_start/post_range_end 참조 제거
3. Alembic 마이그레이션으로 DB 컬럼 제거
```

**Phase C 완료 기준:**
- Growth Profile의 `republish.interval_mode`에 따라 간격이 올바르게 계산되는지 검증
- `republish.enabled=false`인 구간에서 재발행이 실행되지 않는지 검증
- 기존 재발행 모듈의 자체 스케줄러 관련 코드가 제거되었는지 확인
- **`post_range_start`/`post_range_end` 컬럼이 코드 및 DB에서 제거되었는지 확인**

### Phase D: 발행 모듈 연동 + 워밍업 로직 (publish 구현 시)

| 파일 | 작업 내용 | 변경량 |
|------|---------|--------|
| `publisher.py` (신규) | Growth Profile의 `publish.enabled` + `publish.interval_mode` 기반 발행 로직 | +30줄 |
| `app/routers/flows_execute.py` | publish 모듈 타입 디스패치 + Growth Profile 연동 | +40줄 |
| `app/services/generation/warmup_manager.py` (신규) | 워밍업 판단 + ramp_rate 기반 일일 허용 발행 수 계산 | ~100줄 |

**워밍업 로직 구현 상세:**

```
워밍업 판단 기준 (사용자 결정 W7):
  - 워밍업 대상 = BlogAuto에 등록된 블로그 중 발행된 글이 0건인 블로그
  - Blog.created_at 기준이 아닌, 실제 발행 이력 기반 판단
  - 첫 발행일로부터 warmup_days 경과 여부로 워밍업 종료 판단

워밍업 ramp_rate 계산 (CRITICAL):
  워밍업 기간 중 일일 허용 발행 수 = min(initial + (경과일 × ramp_rate), max_daily_posts)

  예) initial=1, max=3, ramp_rate=0.5:
    Day 0: min(1 + 0×0.5, 3) = 1건
    Day 2: min(1 + 2×0.5, 3) = 2건
    Day 4: min(1 + 4×0.5, 3) = 3건 (max 도달)
    Day 5~14: 3건 유지

워밍업 기간 중 publish 간격 계산:
  daily_max = ramp_rate로 계산된 당일 허용 수
  active_hours = schedule_matrix에서 활성 시간 수
  publish_interval = (active_hours × 60) / daily_max

  이 간격은 스테이지의 publish.interval_minutes를 완전히 대체함
```

**Phase D 완료 기준:**
- publish 모듈이 Growth Profile의 `publish.enabled`, `publish.interval_mode`를 올바르게 참조하여 발행을 제어하는지 검증
- **워밍업 대상 판단**: 발행 이력 0건인 블로그가 올바르게 워밍업 대상으로 식별되는지 검증
- **ramp_rate 계산**: 경과일에 따라 일일 허용 발행 수가 올바르게 증가하는지 검증
- **워밍업 기간 중 publish 간격**: 워밍업 daily_max 기반 간격이 스테이지 설정을 올바르게 대체하는지 검증
- **워밍업 종료 시점**: warmup_days 경과 후 스테이지 설정으로 자연 전환되는지 검증
- **generate 비간섭**: 워밍업 기간 중에도 generate가 스테이지 설정대로 정상 동작하는지 검증

### Phase E: UI

| 파일 | 작업 내용 | 변경량 |
|------|---------|--------|
| 모듈 폼 UI | `growth_profile` 타입 전용 설정 폼 (schedule_matrix 그리드, 구간 추가/삭제, 모듈별 체크박스 활성화, 독립 간격 설정, 프리뷰) | 신규 템플릿 |
| Flow 편집 UI | 성장 전략 배지 + 블로그별 스테이지 + 모듈별 활성/비활성 + 간격 표시 | +50줄 |
| 대시보드 위젯 | 성장 단계 현황 + 재고 현황 + 활성 시간대 현황 위젯 | 신규 컴포넌트 |

**Phase E 완료 기준:** 사용자가 UI에서 Growth Profile 모듈을 생성/편집하고(구간 추가, 모듈별 체크박스 활성화, 독립 간격 설정, 활성 시간대 설정), Flow에 추가하여 블로그별 스테이지 미리보기를 확인할 수 있는지 검증

### Phase M: 데이터 마이그레이션 (Phase C 전에 실행)

> Phase C에서 레거시 컬럼/테이블을 제거하기 전에, 기존 데이터를 Growth Profile로 안전하게 이전해야 한다.

| 파일 | 작업 내용 | 변경량 |
|------|---------|--------|
| `scripts/migrate_bgs_to_gp.py` | BlogGrowthSetting → Growth Profile 자동 변환 스크립트 | ~100줄 |
| `scripts/migrate_post_range_to_gp.py` | 기존 post_range 기반 모듈 → Growth Profile stages 변환 스크립트 | ~120줄 |
| Alembic 마이그레이션 | BlogGrowthSetting 테이블 deprecated 마킹 → 이후 제거 | 마이그레이션 |

**마이그레이션 순서:**
```
1. BGS 마이그레이션 스크립트 실행: BlogGrowthSetting 데이터 → Growth Profile settings.stages로 변환
2. post_range 마이그레이션 스크립트 실행: 기존 post_range 기반 모듈 분석 → Growth Profile stages 배열로 통합
3. 데이터 검증: 변환된 Growth Profile의 stages 연속성 + 정합성 확인
4. Phase C에서 레거시 컬럼/테이블 제거
```

**Phase M 완료 기준:**
- BlogGrowthSetting의 모든 데이터가 Growth Profile로 변환되었는지 검증
- post_range 기반 모듈이 Growth Profile stages 배열로 올바르게 통합되었는지 검증
- 변환된 Growth Profile에서 stages 연속성 (빈 범위/겹침 없음) 검증 통과
- BlogGrowthSetting 테이블에 deprecated 마킹 완료

### 별도 계획: flows_execute.py 리팩토링 (사용자 결정 W10)

> 현재 `flows_execute.py`는 1162줄로 500줄 제한을 크게 초과한 상태.
> Growth Profile 코드 추가 시 1200줄+ 예상되므로, **별도 리팩토링 계획 문서**를 작성하여 진행.
> 리팩토링 시점: Phase B 구현 전 또는 병행 진행.

### 전체 일정 요약

```
Phase A (기반 구조)              -- 예상: 1.5일
Phase B (스케줄러 + Flow 연동)   -- 예상: 2일 (GP 검증 + FES 확장 포함)
Phase M (데이터 마이그레이션)     -- 예상: 1일 (Phase C 전에 실행)
Phase C (재발행 연동 + 레거시 제거) -- 예상: 1일
Phase D (발행 + 워밍업)          -- 예상: 1.5일 (warmup 로직 포함)
Phase E (UI)                     -- 예상: 2~3일
                                 ----------------
                                 총 예상: 9~10일
```

**실행 순서:** A → B → M → C → D → E (M은 C 전에 반드시 완료)

---

## 11. 부록: 설계 결정 포인트

### Q1: 왜 새 DB 모델이 아닌 Module.settings로?

기존 Module 시스템을 재사용하면:
- 새 테이블 불필요 (DB 마이그레이션 최소화)
- Flow/Module/Blog 관계를 그대로 활용
- 모듈 생성/편집 UI를 재사용
- `post_range`처럼 Module 레벨에서 관리하는 기존 패턴과 일관성 유지
- `Module.get_setting()` / `Module.set_setting()` 메서드 그대로 사용 가능

### Q2: Flow 하나에 Growth Profile 모듈이 여러 개면?

```
제약: Flow당 growth_profile 타입 모듈은 최대 1개
검증: Flow에 모듈 추가 시 growth_profile 중복 체크
에러: "이 Flow에는 이미 성장 프로파일이 설정되어 있습니다"
```

검증 위치:
- API: Flow에 모듈 연결 시 (`POST /api/v1/flows/{id}/modules`)
- UI: 모듈 추가 드롭다운에서 이미 growth_profile이 있으면 비활성화

### Q3: 블로그가 스테이지 경계에 걸리면? (예: 50글)

```
규칙: post_count_max는 inclusive (포함)
예시:
  post_count_max=50이면 50글까지 해당 스테이지에 속함
  51글부터 다음 스테이지로 전환

기존 재발행 모듈과 동일:
  post_range_start <= post_count <= post_range_end
```

### Q4: 워밍업과 스테이지가 충돌하면?

```
■ 절대 원칙: 워밍업 > 스테이지의 모든 발행 관련 변수

■ 적용 범위: 발행(publish)에만 적용
  - 생성(generate): 워밍업 영향 없음 (내부 동작, 플랫폼 미노출)
  - 발행(publish): 워밍업 적용 대상 (플랫폼에 노출되는 유일한 동작)
  - 재발행(republish): 대상 아님 (신규 블로그에 재발행할 콘텐츠 없음)

■ 동작 규칙:
  블로그 등록 후 warmup_days 이내면:
    1. publish의 일일 발행 수 = 워밍업 설정으로 제한 (ramp_rate에 따라 점진 증가)
    2. publish의 interval_mode, interval_minutes = 워밍업 기간 중 무시됨
       → 워밍업의 daily_max에서 역산한 간격이 적용됨
    3. generate의 daily_count, min_inventory = 스테이지 설정 그대로 적용 (워밍업 무관)
    4. 각 모듈의 enabled 상태 = 스테이지 설정 적용

■ 예시 (warmup_days=14, initial=1, max=3, ramp_rate=0.5):

  스테이지 설정: generate.daily_count=5, publish.daily_count=5

  Day 1:  publish 일일 허용 = 1건 | generate = 스테이지대로 5건
  Day 3:  publish 일일 허용 = 2건 | generate = 스테이지대로 5건
  Day 5:  publish 일일 허용 = 3건 | generate = 스테이지대로 5건
  Day 6~14: publish 일일 허용 = 3건 (max_daily_posts 제한)
  Day 15: 워밍업 종료 → publish도 스테이지의 interval_mode/daily_count(5건) 적용

■ 워밍업 기간 중 publish 간격 계산:
  워밍업 daily_max=1, 활성 시간대=16시간이면:
    → 960분 / 1회 = 960분 간격 (하루 1회)
  워밍업 daily_max=3이면:
    → 960분 / 3회 = 320분 간격 (약 5시간 20분)
  이 간격은 스테이지의 publish.interval_minutes를 완전히 대체함
```

### Q5: BlogGrowthSetting은 어떻게 되나?

```
v3.0에서의 처리:
  BlogGrowthSetting은 즉시 deprecated 처리
  - Growth Profile이 유일한 스케줄러이므로, BlogGrowthSetting은 더 이상 참조되지 않음
  - 기존 BlogGrowthSetting의 데이터는 마이그레이션 스크립트로 Growth Profile로 자동 변환
  - InventoryTrigger._get_threshold()의 폴백 체인 제거 -> Growth Profile 직접 참조

DB 정리:
  - BlogGrowthSetting 테이블은 마이그레이션 완료 후 제거
  - 마이그레이션 스크립트 제공 (BlogGrowthSetting -> Growth Profile 자동 변환)
```

### Q6: schedule_matrix는 왜 stage별이 아닌 모듈 레벨인가?

```
이유:
  - 활성 시간대는 "블로그를 운영하는 시간"이므로, 성장 구간과 무관하게 일정함
  - 급성장기든 안정기든 같은 시간대에 동작해야 자연스러움
  - 구간별 차이는 "간격"과 "횟수"로 충분히 표현됨
  - UI 복잡도를 낮추기 위해 활성 시간대는 한 번만 설정

예외 케이스:
  - 만약 "안정기에는 주말 제외" 같은 요구가 생기면?
  -> 별도 Flow를 만들어 해당 블로그만 분리 (Flow 기반 관리의 유연성 활용)
```

### Q7: 왜 모듈별 체크박스인가?

```
이유:
  - 성장 단계에 따라 특정 모듈을 끄거나 켤 필요가 있음
    예) 시드기(0~30글): 재발행할 글이 부족하므로 재발행 비활성
    예) 성숙기(300글+): 새 글 발행보다 기존 글 재발행이 중요하므로 발행 비활성
  - 비율(publish_ratio/republish_ratio)보다 직관적
    비율: "발행 20%, 재발행 80%" -> 비율 계산 필요, 합계 100% 검증 필요
    체크박스: "발행 끄기, 재발행 하루 3회" -> 명확한 의도 표현
  - 각 모듈이 독립 간격을 가지므로 비율이나 실행 순서가 불필요
  - UI가 단순해짐: 슬라이더/비율 검증/실행 순서 라디오 제거
```

### Q8: 왜 publish_ratio/execution_order를 제거했는가?

```
제거 이유:
  1. 각 모듈이 독립 간격을 가지면 비율이 불필요:
     - 발행: 하루 3회 (자체 간격)
     - 재발행: 하루 5회 (자체 간격)
     -> 비율을 별도로 계산할 필요 없음 (각자 자기 간격대로 실행)

  2. execution_order도 불필요:
     - 각 모듈이 독립된 타이밍에 실행되므로 "누가 먼저"라는 개념이 없음
     - 발행과 재발행이 자연스럽게 서로 다른 시간에 실행됨
     - 오히려 자연스러운 활동 패턴을 만들어 봇 탐지 회피에 유리

  3. UI 단순화:
     - 비율 슬라이더 제거 (합계 100% 검증 불필요)
     - 동작 순서 라디오 버튼 제거
     - "발행 하루 몇 회, 재발행 하루 몇 회"만 설정하면 끝

  4. 체크박스와의 시너지:
     - 구간별로 모듈을 끄면 비율 0%와 같은 효과
     - 더 직관적이고 유연한 제어 가능
```

---

## 서비스 파일 구조

```
app/services/generation/
+-- growth_profile_defaults.py    (신규 ~120줄) - 기본 프로파일 3종 (schedule_matrix, jitter, stages, warmup)
+-- growth_profile_resolver.py    (신규 ~180줄) - 블로그->스테이지 매핑, 모듈별 독립 간격 계산, 활성 시간 체크
+-- flow_execution_context.py     (신규 ~120줄) - FlowExecutionContext, StageParams, ModuleIntervalParams
+-- flow_generate_executor.py     (기존 변경) - generate.enabled 체크 + 컨텍스트 기반 생성 트리거
+-- generator.py                  (기존 변경 없음)
+-- internal_linker.py            (기존 변경 없음)
+-- inventory_trigger.py          (기존 변경) - 자체 임계값 폴백 제거, Growth Profile generate 설정 참조
+-- reference_collector.py        (기존 변경 없음)
+-- substitution_processor.py     (기존 변경 없음)
+-- title_recombiner.py           (기존 변경 없음)
+-- inventory_manager.py          (기존 변경 없음)
```

---

> **변경 이력**
>
> | 버전 | 날짜 | 내용 |
> |------|------|------|
> | v1.0 | 2026-02-18 | 초안 작성 |
> | v2.0 | 2026-02-19 | 사용자 요구사항 반영: 스케줄러 통합(schedule_matrix 모듈 레벨 이동), 간격 설정 차용(interval_mode), 동작 순서(execution_order), 생성 모듈 분리(min_inventory + 생성 전용 간격), 구간 추가 UI(+ 버튼) |
> | v3.0 | 2026-02-20 | 개별 모듈 스케줄러 완전 제거(Clean Break), 구간별 모듈 체크박스 활성화(generate/publish/republish 독립 enabled), 각 모듈 독립 간격 설정, publish_ratio/republish_ratio/execution_order 제거, JSON 구조 재설계(모듈별 서브 객체), StageParams를 ModuleIntervalParams 기반으로 재구성 |
> | v3.1 | 2026-02-20 | Section 10 Phase A~E 크로스체크 반영: Phase A(경계값 테스트, 연속성 검증, 기존 코드 재사용 참조, auto 계산 버그 수정), Phase B(GP 1-per-flow 제한, GP 미설정 Flow 거부, FES 블로그 레벨 확장 검토, flows_execute.py 파일 크기 참조), Phase C(post_range 컬럼 제거), Phase D(warmup 로직 + ramp_rate 계산 + 워밍업 대상 기준), Phase M 신규(BGS/post_range 마이그레이션), Section 7-2 네이밍 혼동 수정 |
