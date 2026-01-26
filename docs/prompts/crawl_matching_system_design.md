# 크롤링 포스트 매칭 시스템 설계 문서

> **버전**: v2.0.0
> **작성일**: 2025-01-25
> **최종 수정**: 2025-01-25
> **상태**: 설계 검토 중

---

## 1. 개요

### 1.1 목적

블로그에 발행된 제목(크롤링 포스트)과 정식 제목(메인타이틀) 간의 유사도 매칭을 자동화하여, AI 글 생성 대상인 **독립포스트**를 식별하는 시스템을 구현합니다.

### 1.2 지원 블로그 플랫폼

| 플랫폼 | 우선순위 | 크롤링 방식 | 비고 |
|--------|----------|-------------|------|
| **WordPress** | ✅ 필수 | RSS Feed / REST API | 자체 호스팅 블로그 |
| **Google Blogger** | ✅ 필수 | Blogger API v3 / RSS | 구글 블로거 |
| 티스토리 | 🔜 추후 | Open API | 국내 서비스 |
| 네이버 블로그 | 🔜 추후 | 크롤링 | 국내 서비스 |

> **Note**: 기본적으로 **WordPress**와 **Google Blogger** 두 플랫폼을 우선 지원합니다.
> 각 플랫폼별 크롤링 로직이 구현되어야 합니다.

### 1.3 핵심 개념 정의

| 용어 | 정의 |
|------|------|
| **크롤링 포스트** | 블로그에서 크롤링한 실제 발행된 제목 데이터 |
| **메인타이틀** | 정식 제목으로 등록된 제목 (임시제목에서 이동) |
| **활성 그룹** | 유사한 메인타이틀들의 그룹 (대표 제목 존재) |
| **독립포스트** | 메인타이틀 중 크롤링 포스트와 매칭되지 않은 제목 → **AI 글 생성 대상** |
| **미매칭** | 크롤링 포스트 중 메인타이틀과 매칭되지 않은 제목 (기존 운영 블로그의 독자 발행 글) |

### 1.4 전체 워크플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                    생성 직전 자동화 파이프라인                      │
└─────────────────────────────────────────────────────────────────┘

1. Flow에 블로그 + 생성 모듈 + 프롬프트 모듈 추가됨
   ↓
2. [자동] 블로그 크롤링 (WordPress / Blogger)
   → CrawledPost 데이터 생성
   ↓
3. [자동] 유사도 매칭
   → MainTitle ↔ CrawledPost 매칭
   ↓
4. [자동] 분류
   ├── 매칭 (score ≥ 75%): CrawledPost와 MainTitle 연결
   ├── 대기 (65% ≤ score < 75%): 검토 필요
   ├── 미매칭 (score < 65%): 기존 운영 블로그의 독자 발행
   └── 독립포스트: MainTitle 중 매칭 안 된 것 → 생성 대상
   ↓
5. [자동] 생성 모듈 실행 (스케줄 기반)
   → 독립포스트 대상으로 AI 글/이미지 생성 → 저장 → 발행
```

---

## 2. 시스템 아키텍처

### 2.1 권장 아키텍처: 생성 모듈 기반 자동화

```
┌─────────────────────────────────────────────────────────────────┐
│                     Flow 실행 파이프라인                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [필수 구성 요소] - 3가지 조건 충족 필요                          │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  1. 블로그 (WordPress / Blogger)                        │   │
│   │  2. 생성 모듈 (Generate Module)                         │   │
│   │  3. 프롬프트 모듈 (Prompt Module)                       │   │
│   │     └─ 프롬프트에 연결된 블로그가 Flow에 포함되어야 함    │   │
│   └─────────────────────────────────────────────────────────┘   │
│                          ↓                                      │
│   [Pre-Execution Stage]                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  1. CrawlSyncService                                    │   │
│   │     - 블로그별 크롤링 (WordPress RSS / Blogger API)      │   │
│   │     - CrawledPost 데이터 생성/업데이트                   │   │
│   │                                                         │   │
│   │  2. HybridMatchingService                               │   │
│   │     - 유사도 매칭 실행 (생성 모듈 임계값 사용)            │   │
│   │     - 매칭/대기/미매칭 분류                              │   │
│   │     - 독립포스트 식별                                    │   │
│   └─────────────────────────────────────────────────────────┘   │
│                          ↓                                      │
│   [Module Execution Stage]                                      │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Module: generate (생성 모듈)                           │   │
│   │     - 스케줄 기반 실행 (활성 시간대, 생성 간격)           │   │
│   │     - 독립포스트 기반 AI 글/이미지 생성                  │   │
│   │     - 블로그별 누적 포스트 수 기반 생성 구간 적용         │   │
│   │                                                         │   │
│   │  Module: prompt (프롬프트 모듈)                         │   │
│   │     - 블로그별 프롬프트 매핑                             │   │
│   │     - 글 생성 프롬프트 + 이미지 생성 프롬프트            │   │
│   │     - AI 벤더별 설정 (OpenAI, Claude, Gemini)           │   │
│   │                                                         │   │
│   │  Module: republish (재발행 모듈) - 기존 유지             │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 자동화 vs 수동 테스트 비교

| 기능 | 자동화 (생성 모듈 실행 시) | 수동 (블로그 선택 시) |
|------|--------------------------|---------------------|
| **트리거** | 스케줄 기반 자동 실행 | 사용자가 드랍다운에서 블로그 선택 |
| **크롤링** | 필요시 자동 실행 | 블로그 선택 → 없으면 자동 크롤링 |
| **매칭 임계값** | 생성 모듈에서 설정한 값 사용 | 생성 모듈 없으면 경고 메시지 |
| **결과 확인** | 로그에 기록 | 테이블 UI 실시간 표시 |
| **매칭 확정** | 자동 확정 (≥75%) | 대기 상태 수동 확정/거부 |
| **미매칭 처리** | - | [1:1 매칭] / [독립포스트 추가] |
| **글 생성** | 자동 생성 후 저장 | 독립포스트 배지 클릭 → 수동 생성 |

---

## 3. 임계값 시스템

### 3.1 두 가지 유사도 매칭의 차이

| 구분 | 제목 이동 매칭 (데이터 이동 모듈) | 블로그 선택 매칭 (생성 모듈) |
|------|-------------------------------|---------------------------|
| **목적** | 유사 제목 그룹화 | 1:1 매칭 특화 |
| **범위** | 넓은 임계값 범위 | 좁은 임계값 범위 |
| **판정** | 그룹으로 묶느냐/안 묶느냐 | 동일/비슷(대기)/미매칭 |
| **설정 위치** | 데이터 이동 모듈 | 생성 모듈 |
| **폴백** | 하드코딩 값 | 하드코딩 값 (생성 모듈 없을 시) |

### 3.2 블로그 선택 매칭 임계값 (생성 모듈)

```python
class GenerateModuleSettings:
    """생성 모듈 임계값 설정"""

    # 매칭 임계값 (동일에 가깝다고 판정)
    match_threshold_min: float = 75.0   # 기본값 75%
    match_threshold_max: float = 100.0  # 최대 100%

    # 대기 임계값 (비슷한 제목이라고 판정)
    waiting_threshold_min: float = 65.0  # 기본값 65%
    waiting_threshold_max: float = 74.9  # 매칭 최소값 - 0.1%

    # 미매칭: < 65%
```

> **기본값 설정 근거**:
> - 제목 이동 시 임계값 기준을 보았을 때 65%까지도 매칭 가능
> - 이전 버전 테스트에서 매칭 여부 경계가 모호했던 점 고려
> - 사용자가 테스트 후 조정 가능하도록 양쪽 값을 설정

### 3.3 동일 타이틀/그룹에 복수 매칭 처리

> **새로운 고려사항**: 블로그에 비슷한 제목으로 포스트를 발행하는 경우 존재

```
┌─────────────────────────────────────────────────────────────────┐
│                 복수 매칭 시나리오                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   메인타이틀: "서울 맛집 추천"                                    │
│       ↓                                                         │
│   크롤링 포스트 매칭 결과:                                        │
│   ├── "서울 맛집 추천 베스트 10" (87%)                           │
│   ├── "서울 맛집 추천 2025" (82%)                                │
│   └── "서울 맛집 추천 완전정복" (79%)                             │
│                                                                 │
│   → 동일 메인타이틀에 유사한 크롤링 포스트 3개 매칭               │
│   → 가장 높은 점수의 포스트와 1차 매칭                            │
│   → 나머지는 "추가 매칭" 상태로 표시                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 생성 모듈 없이 수동 매칭 시도 시

```
┌─────────────────────────────────────────────────────────────────┐
│                    ⚠️ 경고 메시지                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   생성 모듈이 설정되지 않았습니다.                                │
│                                                                 │
│   블로그 선택 후 유사도 매칭을 진행하려면                          │
│   먼저 생성 모듈을 생성해주세요.                                  │
│                                                                 │
│   생성 모듈에서 다음 설정이 필요합니다:                           │
│   • 매칭 임계값 (기본: 75%~100%)                                 │
│   • 대기 임계값 (기본: 65%~74%)                                  │
│   • 스케줄 설정 (자동화 시)                                       │
│                                                                 │
│   [생성 모듈 만들기] [취소]                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 생성 모듈 상세 설계

### 4.1 생성 모듈 필수 조건

```
┌─────────────────────────────────────────────────────────────────┐
│               생성 모듈 동작 조건 검증                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [조건 1] Flow에 생성 모듈 포함                                  │
│      └─ ✅ / ❌                                                  │
│                                                                 │
│   [조건 2] Flow에 프롬프트 모듈 포함                              │
│      └─ ✅ / ❌                                                  │
│                                                                 │
│   [조건 3] Flow에 블로그 포함                                     │
│      └─ ✅ / ❌                                                  │
│                                                                 │
│   [조건 4] 프롬프트 모듈에 연결된 블로그가 Flow에 포함             │
│      └─ ✅ / ❌                                                  │
│      └─ 불충족 시: "프롬프트 모듈 교체" 또는 "블로그 추가" 유도    │
│                                                                 │
│   ⚠️ 4가지 조건 모두 충족해야 생성 모듈 동작                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 스케줄 설정 (재발행 모듈 차용)

> **재발행 모듈의 스케줄러 옵션을 그대로 차용**

```python
class GenerateModuleScheduleSettings:
    """생성 모듈 스케줄 설정 - 재발행 모듈과 동일 구조"""

    # 활성 시간대 설정
    active_time_ranges: List[TimeRange] = [
        TimeRange(start="09:00", end="12:00"),
        TimeRange(start="14:00", end="18:00"),
        TimeRange(start="20:00", end="23:00"),
    ]

    # 생성 간격 (분)
    generation_interval_minutes: int = 30

    # 블로그 누적 포스트 수 기반 생성 구간
    post_count_ranges: List[PostCountRange] = [
        PostCountRange(min=0, max=50, priority="high"),      # 신규 블로그 집중
        PostCountRange(min=51, max=200, priority="medium"),
        PostCountRange(min=201, max=None, priority="low"),   # 성숙 블로그
    ]
```

### 4.3 전략적 글 생성 운영

```
┌─────────────────────────────────────────────────────────────────┐
│               전략적 글 생성 시나리오                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [시나리오 1] 신규 블로그 집중 육성                              │
│   ├─ 누적 포스트 0~50개: 높은 우선순위                           │
│   ├─ 생성 간격: 20분                                            │
│   └─ 활성 시간대: 09:00~23:00 (종일)                            │
│                                                                 │
│   [시나리오 2] 특정 시간대 집중                                   │
│   ├─ 활성 시간대: 08:00~10:00, 20:00~22:00 (피크 타임)          │
│   ├─ 생성 간격: 15분                                            │
│   └─ 모든 블로그 균등 적용                                       │
│                                                                 │
│   [시나리오 3] 성숙 블로그 유지 관리                              │
│   ├─ 누적 포스트 200개 이상: 낮은 우선순위                       │
│   ├─ 생성 간격: 60분                                            │
│   └─ 활성 시간대: 10:00~18:00 (업무 시간)                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 생성 모듈 자동화 파이프라인

```
┌─────────────────────────────────────────────────────────────────┐
│           생성 모듈 자동화 파이프라인 (스케줄 기반)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [Step 1] 스케줄러 트리거                                       │
│   └─ 활성 시간대 & 생성 간격 확인                                │
│                                                                 │
│   [Step 2] 대상 블로그 선정                                      │
│   ├─ Flow에 포함된 블로그 목록 조회                              │
│   ├─ 누적 포스트 수 기준 우선순위 적용                           │
│   └─ 생성 구간 설정에 따라 대상 선정                             │
│                                                                 │
│   [Step 3] 블로그별 크롤링 (WordPress / Blogger)                 │
│   ├─ 크롤링 데이터 존재 확인                                     │
│   ├─ 없으면 크롤링 실행                                          │
│   └─ CrawledPost 데이터 저장                                    │
│                                                                 │
│   [Step 4] 유사도 매칭                                           │
│   ├─ 생성 모듈 임계값 적용                                       │
│   ├─ 매칭 / 대기 / 미매칭 분류                                   │
│   └─ 독립포스트 식별                                             │
│                                                                 │
│   [Step 5] AI 글/이미지 생성                                     │
│   ├─ 프롬프트 모듈에서 해당 블로그 프롬프트 조회                  │
│   ├─ 독립포스트 제목 기반 AI 글 생성                             │
│   ├─ 설정에 따라 이미지 생성 (AI 또는 템플릿)                    │
│   └─ 생성 결과 저장                                              │
│                                                                 │
│   [Step 6] 결과 저장                                             │
│   ├─ 글/이미지 → 크롤링 포스트 ID에 연결 저장                    │
│   ├─ 독립포스트 상태 → "발행대기"로 변경                         │
│   └─ 로그 기록                                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 프롬프트 모듈 상세 설계

### 5.1 프롬프트 모듈 필수 조건

> **생성 모듈과 반드시 동일 Flow에 포함되어야 함**

```
┌─────────────────────────────────────────────────────────────────┐
│               프롬프트 모듈 설계 원칙                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [분리 이유]                                                    │
│   • 생성 모듈에 포함 시 모듈 크기가 너무 커지는 문제              │
│   • 프롬프트는 여러 스타일로 구축 → 블로그별 다른 프롬프트 적용   │
│   • 프롬프트 관리의 유연성 확보                                   │
│                                                                 │
│   [필수 구성]                                                    │
│   • 글 생성 프롬프트 (AI 벤더별)                                 │
│   • 이미지 생성 프롬프트                                         │
│   • 제목 재조합 및 줄바꿈 설정 프롬프트                           │
│   • 블로그 연결 설정                                             │
│                                                                 │
│   [차후 계획]                                                    │
│   • 하나의 블로그에서 여러 프롬프트 적용                          │
│   • 글에 따라 다른 프롬프트 자동 적용 (우선순위 낮음)             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 프롬프트 모듈 구조

```python
class PromptModule:
    """프롬프트 모듈 스키마"""

    id: int
    name: str
    flow_id: int

    # 블로그 연결 (Flow 내 블로그 선택과 동일 방식)
    linked_blog_ids: List[int]

    # 글 생성 프롬프트 (AI 벤더별)
    text_prompts: TextPromptSettings

    # 이미지 생성 프롬프트
    image_prompts: ImagePromptSettings

    # 제목 재조합 설정
    title_settings: TitleSettings

    # 생성 옵션
    generation_options: GenerationOptions


class TextPromptSettings:
    """글 생성 프롬프트 설정"""

    # AI 벤더별 프롬프트
    openai_prompt: OpenAIPromptConfig
    claude_prompt: ClaudePromptConfig
    gemini_prompt: GeminiPromptConfig

    # 현재 사용 벤더
    active_vendor: str  # "openai" | "claude" | "gemini"


class OpenAIPromptConfig:
    """OpenAI 글 생성 프롬프트"""
    model: str = "gpt-4o"
    system_prompt: str
    user_prompt_template: str
    temperature: float = 0.7
    max_tokens: int = 4000
    # OpenAI 특화 설정들...


class ClaudePromptConfig:
    """Claude 글 생성 프롬프트"""
    model: str = "claude-sonnet-4-20250514"
    system_prompt: str
    user_prompt_template: str
    temperature: float = 0.7
    max_tokens: int = 4000
    # Claude 특화 설정들...


class GeminiPromptConfig:
    """Gemini 글 생성 프롬프트"""
    model: str = "gemini-2.0-flash"
    system_prompt: str
    user_prompt_template: str
    temperature: float = 0.7
    max_tokens: int = 4000
    # Gemini 특화 설정들...


class ImagePromptSettings:
    """이미지 생성 프롬프트 설정"""

    # 이미지 생성 활성화 여부
    enabled: bool = False

    # AI 이미지 생성 프롬프트 (DALL-E, Midjourney 등)
    ai_image_prompt: str

    # 이미지 생성 옵션
    image_size: str = "1024x1024"
    image_style: str = "natural"

    # AI 이미지 비활성화 시 → 템플릿 이미지 + 텍스트 오버레이
    fallback_to_template: bool = True


class TitleSettings:
    """제목 재조합 및 줄바꿈 설정"""

    # 제목 재조합 프롬프트
    title_recombine_prompt: str

    # 줄바꿈 설정
    line_break_rules: str
    max_line_length: int = 20

    # 텍스트 오버레이 스타일
    overlay_font: str
    overlay_color: str
    overlay_position: str


class GenerationOptions:
    """생성 옵션"""

    # 글만 생성 / 이미지도 함께 생성
    generate_image: bool = False

    # 이미지 소스 선택
    image_source: str  # "ai" | "template"
```

### 5.3 프롬프트-블로그 연결 검증

```
┌─────────────────────────────────────────────────────────────────┐
│         프롬프트 모듈 블로그 연결 검증 플로우                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [검증 시점] Flow 저장 / 생성 모듈 실행 전                       │
│                                                                 │
│   Step 1: 프롬프트 모듈의 linked_blog_ids 조회                   │
│           └─ 예: [blog_1, blog_2, blog_3]                       │
│                                                                 │
│   Step 2: Flow에 포함된 블로그 목록 조회                          │
│           └─ 예: [blog_1, blog_2]                               │
│                                                                 │
│   Step 3: 비교                                                   │
│           ├─ blog_1: ✅ Flow에 포함                             │
│           ├─ blog_2: ✅ Flow에 포함                             │
│           └─ blog_3: ❌ Flow에 미포함                           │
│                                                                 │
│   Step 4: 불일치 시 처리                                         │
│           ├─ 옵션 A: 프롬프트 모듈 교체                          │
│           └─ 옵션 B: blog_3을 Flow에 추가                        │
│                                                                 │
│   ⚠️ 경고 메시지:                                                │
│   "프롬프트 모듈에 연결된 'blog_3'이 Flow에 포함되어 있지          │
│    않습니다. 프롬프트 모듈을 교체하거나 블로그를 Flow에             │
│    추가해주세요."                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 수동 UI/UX 설계

### 6.1 정식 제목 관리 페이지 - 블로그 선택 드랍다운

```
┌──────────────────────────────────────────────────────────────────────┐
│  데이터 관리 - 정식 제목                                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [탭: 임시 제목 | 정식 제목 | 활성 그룹]                               │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ 블로그 선택: [▼ 블로그를 선택하세요                     ]       │  │
│  │              ├─ 내 워드프레스 블로그 1                          │  │
│  │              ├─ 내 워드프레스 블로그 2                          │  │
│  │              ├─ 구글 블로거 1                                   │  │
│  │              └─ 구글 블로거 2                                   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ※ 블로그 선택 시 자동으로 크롤링 및 유사도 매칭이 진행됩니다.        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 블로그 선택 시 자동 동작 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│               블로그 선택 시 자동 동작                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   사용자: 드랍다운에서 "내 워드프레스 블로그 1" 선택              │
│          ↓                                                      │
│   [Step 1] 크롤링 데이터 확인                                    │
│   ├─ 있음 → DB에서 CrawledPost 호출                             │
│   └─ 없음 → 블로그 크롤링 실행 → 데이터 저장 → 호출              │
│          ↓                                                      │
│   [Step 2] 유사도 매칭 진행                                      │
│   ├─ 호출된 크롤링 데이터 vs 정식 제목 테이블 데이터              │
│   ├─ 생성 모듈 임계값 적용 (없으면 경고 메시지)                  │
│   └─ 매칭 결과 → 테이블에 실시간 표시                            │
│          ↓                                                      │
│   [Step 3] 결과 UI 표시 (이전 버전 참조)                         │
│   ├─ 매칭됨: 초록색 배지                                        │
│   ├─ 대기: 노란색 배지 + [확정/거부] 버튼                        │
│   ├─ 미매칭: 빨간색 배지                                        │
│   └─ 독립포스트: 파란색 배지 + [글 생성] 버튼                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 매칭 결과 테이블 UI (이전 버전 참조)

```
┌──────────────────────────────────────────────────────────────────────┐
│  정식 제목 - 블로그: 내 워드프레스 블로그 1                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📊 매칭 현황                                                        │
│  ├─ 크롤링 포스트: 120개                                             │
│  ├─ 매칭 완료: 85개 (71%)                                            │
│  ├─ 검토 대기: 15개                                                  │
│  ├─ 미매칭: 20개                                                     │
│  └─ 독립포스트 (생성 대상): 50개                                     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────┬─────────────────┬──────────────────┬──────┬────────────────┐ │
│  │ #  │ 정식 제목        │ 크롤링 포스트     │ 점수 │ 상태           │ │
│  ├────┼─────────────────┼──────────────────┼──────┼────────────────┤ │
│  │ 1  │ 서울 맛집 추천   │ 서울 맛집 추천 10선│ 92%  │ 🟢 매칭       │ │
│  │ 2  │ 부산 여행 코스   │ 부산 여행 후기    │ 78%  │ 🟡 대기       │ │
│  │ 3  │ 제주도 카페 투어 │ -                │ -    │ 🔵 독립포스트  │ │
│  │ 4  │ 강남 맛집 탐방   │ -                │ -    │ 🔵 독립포스트  │ │
│  └────┴─────────────────┴──────────────────┴──────┴────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.4 독립포스트 클릭 → AI 글 생성 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│          독립포스트 배지 클릭 → AI 글 생성 플로우                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [Step 1] 독립포스트 배지 클릭                                  │
│          ↓                                                      │
│   [Step 2] 프롬프트 조회                                         │
│   └─ 해당 블로그가 연결된 프롬프트 모듈에서 프롬프트 가져오기      │
│          ↓                                                      │
│   [Step 3] AI 글 생성                                            │
│   └─ 프롬프트 설정에 따라 OpenAI/Claude/Gemini 호출             │
│          ↓                                                      │
│   [Step 4] 이미지 처리                                           │
│   ├─ AI 이미지 생성 활성화 시 → AI 이미지 생성                   │
│   └─ 비활성화 시 → 블로그 설정의 템플릿 이미지 + 제목 오버레이    │
│          ↓                                                      │
│   [Step 5] 결과 팝업 표시                                        │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 📝 생성 결과 미리보기                                    │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │                                                         │   │
│   │ [마크다운 형식 글 미리보기]                              │   │
│   │ # 제목                                                  │   │
│   │ 본문 내용...                                            │   │
│   │                                                         │   │
│   │ [이미지 미리보기]                                        │   │
│   │ ┌─────────────┐                                        │   │
│   │ │   🖼️        │                                        │   │
│   │ │  이미지     │                                        │   │
│   │ └─────────────┘                                        │   │
│   │                                                         │   │
│   │ [내부 링크 추가] [HTML 변환] [CSS 치환] [웹 미리보기]    │   │
│   │                                                         │   │
│   │ [저장] [취소]                                           │   │
│   └─────────────────────────────────────────────────────────┘   │
│          ↓                                                      │
│   [Step 6] 저장 시                                               │
│   ├─ 글/이미지 → 크롤링 포스트 ID에 저장                         │
│   └─ 독립포스트 상태 → "발행대기"로 변경                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.5 글 생성 결과 처리 상세

```
┌─────────────────────────────────────────────────────────────────┐
│              글 생성 결과 처리 단계                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [1] 마크다운 글 미리보기                                       │
│   └─ 생성된 AI 글을 마크다운 형식으로 표시                        │
│                                                                 │
│   [2] 이미지 미리보기                                            │
│   ├─ AI 생성 이미지: AI가 생성한 이미지                          │
│   └─ 템플릿 이미지: 블로그 설정 이미지 + 재조합 제목 오버레이     │
│                                                                 │
│   [3] 내부 링크 추가                                             │
│   └─ 사용자가 내부 링크를 수동으로 추가                          │
│                                                                 │
│   [4] HTML 변환                                                  │
│   └─ 마크다운 → HTML 변환                                        │
│                                                                 │
│   [5] CSS 클래스 치환                                            │
│   └─ 블로그 플랫폼에 맞는 CSS 클래스로 치환                       │
│                                                                 │
│   [6] 웹 미리보기                                                │
│   └─ 최종 HTML/CSS 적용된 상태로 웹 출력 미리보기                 │
│                                                                 │
│   [7] 저장                                                       │
│   ├─ 글/이미지 → 크롤링 포스트 ID에 저장                         │
│   └─ 독립포스트 → "발행대기" 상태로 변경                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.6 발행 및 후처리

```
┌─────────────────────────────────────────────────────────────────┐
│                 발행 및 후처리 플로우                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [발행대기 상태]                                                │
│   └─ 독립포스트 배지: "발행대기" 표시                            │
│                                                                 │
│   [수동 발행 가능]                                               │
│   └─ 사용자가 "발행" 버튼 클릭 → 블로그에 발행                   │
│                                                                 │
│   [발행 완료 시]                                                 │
│   ├─ 발행대기 배지 → "매칭" 배지로 전환                          │
│   ├─ 크롤링 포스트 데이터 업데이트                               │
│   │   └─ match_status: "matched"                                │
│   │   └─ matched_main_title_id: 해당 메인타이틀 ID              │
│   └─ 저장된 글/이미지 삭제 스케줄 등록                           │
│                                                                 │
│   [글/이미지 자동 삭제]                                          │
│   └─ 사용자 설정 기간 이후 자동 삭제 (예: 발행 후 7일)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 데이터 모델 설계

### 7.1 CrawledPost (신규)

```python
class CrawledPost(Base):
    """블로그에서 크롤링한 발행된 포스트"""
    __tablename__ = "crawled_posts"

    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False)

    # 포스트 정보
    title = Column(String(500), nullable=False)
    url = Column(String(1000), unique=True)
    published_at = Column(DateTime)  # 블로그에서의 실제 발행일

    # 매칭 정보
    match_status = Column(String(20), default="pending")
    # pending | matched | waiting | unmatched
    matched_main_title_id = Column(Integer, ForeignKey("main_titles.id"))
    matched_group_id = Column(Integer, ForeignKey("title_groups.id"))
    match_score = Column(Float)

    # 생성된 콘텐츠 저장
    generated_content = Column(Text)  # 생성된 글 (HTML)
    generated_image_path = Column(String(500))  # 생성된 이미지 경로
    content_created_at = Column(DateTime)  # 콘텐츠 생성 시간

    # 발행 정보
    publish_status = Column(String(20), default="none")
    # none | pending | published
    published_at_blog = Column(DateTime)  # 실제 발행 시간

    # 콘텐츠 삭제 스케줄
    content_delete_after = Column(DateTime)  # 이 시간 이후 콘텐츠 삭제

    # 메타데이터
    crawled_at = Column(DateTime, default=func.now())
    last_matched_at = Column(DateTime)

    # 관계
    blog = relationship("Blog", back_populates="crawled_posts")
    matched_main_title = relationship("MainTitle")
    matched_group = relationship("TitleGroup")
```

### 7.2 Blog 모델 확장

```python
class Blog(Base):
    # 기존 필드...

    # 크롤링 상태 추가
    blog_platform = Column(String(20))  # "wordpress" | "blogger"
    last_crawled_at = Column(DateTime)  # 마지막 크롤링 시간
    crawl_status = Column(String(20), default="never")
    # never | synced | outdated | error

    crawled_posts = relationship("CrawledPost", back_populates="blog")
```

### 7.3 매칭 상태 흐름

```
CrawledPost.match_status:

  pending ──┬── 자동매칭 ──┬── score ≥ 75% ──→ matched (자동확정)
            │              │
            │              ├── 65% ≤ score < 75% ──→ waiting (검토대기)
            │              │
            │              └── score < 65% ──→ unmatched (미매칭)
            │
            └── 수동조작 ──┬── 대기 확정 ──→ matched
                          │
                          ├── 대기 거부 ──→ unmatched
                          │
                          ├── 1:1 매칭 ──→ matched (독립포스트와 연결)
                          │
                          └── 독립포스트 생성 ──→ matched (새 MainTitle 생성)


CrawledPost.publish_status (독립포스트 관련):

  none ──→ pending (글 생성 후 저장) ──→ published (발행 완료)
```

---

## 8. 유사도 매칭 알고리즘

### 8.1 하이브리드 매칭 전략

v2 지역명 필터링 + v1 성능 최적화를 조합한 하이브리드 방식 채택

#### 핵심 최적화 포인트

1. **이미 매칭된 제목 제외**: `matched_main_title_id` 존재 시 매칭 비교 제외
2. **활성 그룹 대표 제목만 매칭**: 그룹 내 모든 제목 대신 대표 제목만 비교
3. **v2 지역명 필터링 (Stage 0)**: 지역 불일치 시 즉시 차단
4. **캐노니컬 키 기반 빠른 완전 일치**: 정규화된 키 비교로 100% 매칭
5. **복수 매칭 처리**: 동일 메인타이틀에 여러 크롤링 포스트 매칭 시 처리

### 8.2 매칭 알고리즘 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│              HybridMatchingService.match_blog_titles()           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 크롤링 포스트 조회                                      │
│  ├─ CrawledPost 존재? → DB 조회                                 │
│  └─ 없음? → 크롤링 실행 후 저장 (WordPress / Blogger)            │
│                                                                 │
│  Step 2: 매칭 대상 필터링                                        │
│  └─ matched_main_title_id가 NULL인 것만 선택                    │
│                                                                 │
│  Step 3: 메인타이틀 조회 (최적화)                                │
│  ├─ 활성 그룹 → 대표 제목만 조회                                 │
│  └─ 그룹 없는 제목 → 전체 조회                                   │
│                                                                 │
│  Step 4: 임계값 조회                                             │
│  ├─ 생성 모듈 존재 → 모듈 설정값 사용                            │
│  └─ 없음 → 하드코딩 기본값 (75% / 65%)                           │
│                                                                 │
│  Step 5: 유사도 매칭 실행                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ for each crawled_post:                                  │    │
│  │   for each main_title:                                  │    │
│  │     ├─ Stage 0: 지역명 호환성 검사                       │    │
│  │     │   └─ 불일치 → continue (스킵)                     │    │
│  │     │                                                   │    │
│  │     ├─ Stage 1: 캐노니컬 키 완전 일치                   │    │
│  │     │   └─ 일치 → score = 100                          │    │
│  │     │                                                   │    │
│  │     └─ Stage 2: 하이브리드 유사도 계산                  │    │
│  │         └─ calculate_similarity_v3()                    │    │
│  │         └─ 지역 패널티 적용                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Step 6: 결과 분류 (생성 모듈 임계값 기준)                        │
│  ├─ score ≥ match_threshold_min → matched (자동 확정)           │
│  ├─ waiting_threshold_min ≤ score < match_threshold_min         │
│  │   → waiting (검토 대기)                                       │
│  └─ score < waiting_threshold_min → unmatched (미매칭)          │
│                                                                 │
│  Step 7: 복수 매칭 처리                                          │
│  └─ 동일 메인타이틀에 여러 크롤링 포스트 매칭 시                  │
│      ├─ 최고 점수 → primary match                               │
│      └─ 나머지 → additional matches                             │
│                                                                 │
│  Step 8: 독립포스트 식별                                         │
│  └─ MainTitle 중 CrawledPost와 매칭되지 않은 것                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 지역명 필터링 (v2 신규 기능)

```python
def _check_location_compatibility(title1, title2) -> Dict:
    """
    지역명 호환성 검사 (4가지 케이스)

    Case 1: 둘 다 지역명 있음 + 일치 → compatible=True, penalty=0
    Case 2: 둘 다 지역명 있음 + 불일치 → compatible=False (그룹화 차단!)
    Case 3: 한쪽만 지역명 있음 → compatible=True, penalty=0.30
    Case 4: 둘 다 지역명 없음 → compatible=True, penalty=0
    """
```

**예시:**

| Case | Title1 | Title2 | Result | Reason |
|------|--------|--------|--------|--------|
| 1 | 경북 포항 화환 | 경북 포항시 화환 | ✅ 일치 | 지역 동일, penalty=0 |
| 2 | 경북 포항 화환 | 전남 광주 화환 | ❌ 불일치 | 지역 다름, **차단** |
| 3 | 경북 포항 화환 | 화환 판매처 | ⚠️ 불확실 | 한쪽만 지역, penalty=30% |
| 4 | 화환 판매처 | 꽃배달 서비스 | ✅ 가능 | 지역 없음, penalty=0 |

### 8.4 임계값 설정

```python
class HybridMatchingService:
    # 기본값 (생성 모듈 없을 시 사용)
    DEFAULT_MATCH_THRESHOLD = 75.0    # 매칭 최소값
    DEFAULT_WAITING_MIN = 65.0        # 대기 최소값

    def get_thresholds(self, generate_module: Optional[GenerateModule]):
        """임계값 조회 - 생성 모듈 우선"""
        if generate_module:
            return {
                "match_min": generate_module.match_threshold_min,
                "match_max": generate_module.match_threshold_max,
                "waiting_min": generate_module.waiting_threshold_min,
                "waiting_max": generate_module.waiting_threshold_max,
            }
        return {
            "match_min": self.DEFAULT_MATCH_THRESHOLD,
            "match_max": 100.0,
            "waiting_min": self.DEFAULT_WAITING_MIN,
            "waiting_max": 74.9,
        }
```

---

## 9. API 설계

### 9.1 엔드포인트 목록

```python
# 블로그 선택 시 자동 호출 (크롤링 + 매칭)
GET /api/v1/matching/blog/{blog_id}/status
# Response: 매칭 현황 + 각 카테고리별 카운트

# 대기 → 매칭 확정/거부
POST /api/v1/matching/confirm
# Body: { crawled_post_id, main_title_id, confirmed: bool }

# 미매칭 → 독립포스트 1:1 매칭
POST /api/v1/matching/manual-match
# Body: { crawled_post_id, independent_title_id }

# 미매칭 → 새 독립포스트 생성
POST /api/v1/matching/create-independent
# Body: { crawled_post_id }

# 독립포스트 목록 (선택 가능)
GET /api/v1/titles/independent?blog_id={blog_id}
# Response: 생성 대상 독립포스트 목록

# 전체 재매칭 (force)
POST /api/v1/matching/blog/{blog_id}/rematch

# 독립포스트 글 생성
POST /api/v1/generate/independent/{main_title_id}
# Body: { blog_id, prompt_module_id }

# 생성된 글 저장
POST /api/v1/generate/save
# Body: { crawled_post_id, content, image_path }

# 글 발행
POST /api/v1/generate/publish/{crawled_post_id}
```

### 9.2 Response 스키마

```python
class MatchingStatusResponse(BaseModel):
    """블로그 매칭 현황"""
    blog_id: int
    blog_name: str
    blog_platform: str  # "wordpress" | "blogger"

    # 카운트
    total_crawled: int
    matched_count: int
    waiting_count: int
    unmatched_count: int
    independent_count: int

    # 상세 데이터
    matched: List[MatchedPairResponse]
    waiting: List[MatchedPairResponse]
    unmatched: List[CrawledPostResponse]
    independent: List[MainTitleResponse]

    # 메타데이터
    last_crawled_at: Optional[datetime]
    last_matched_at: Optional[datetime]

    # 임계값 정보
    thresholds: ThresholdInfo
    has_generate_module: bool

class ThresholdInfo(BaseModel):
    """임계값 정보"""
    match_min: float
    match_max: float
    waiting_min: float
    waiting_max: float
    source: str  # "generate_module" | "default"

class MatchedPairResponse(BaseModel):
    """매칭된 쌍 정보"""
    crawled_post: CrawledPostResponse
    main_title: MainTitleResponse
    score: float
    match_status: str  # matched | waiting
    additional_matches: Optional[List[CrawledPostResponse]]  # 복수 매칭 시
```

---

## 10. 파일 구조

```
services/republish/app/
├── models/
│   ├── crawled_post.py          # [신규] 크롤링 포스트 모델
│   ├── generate_module.py       # [신규] 생성 모듈 모델
│   ├── prompt_module.py         # [신규] 프롬프트 모듈 모델
│   └── blog.py                  # [수정] 크롤링 상태 필드 추가
│
├── schemas/
│   ├── crawled_post.py          # [신규] 크롤링 포스트 스키마
│   ├── matching.py              # [신규] 매칭 결과 스키마
│   ├── generate_module.py       # [신규] 생성 모듈 스키마
│   └── prompt_module.py         # [신규] 프롬프트 모듈 스키마
│
├── services/
│   ├── hybrid_matching_service.py  # [신규] 하이브리드 매칭
│   ├── crawl_service.py            # [신규] 블로그 크롤링
│   │   ├── wordpress_crawler.py    # [신규] WordPress 크롤링
│   │   └── blogger_crawler.py      # [신규] Blogger 크롤링
│   ├── independent_post_service.py # [신규] 독립포스트 관리
│   ├── content_generation_service.py # [신규] AI 글/이미지 생성
│   └── publish_service.py          # [신규] 발행 서비스
│
├── routers/
│   ├── matching.py              # [신규] 매칭 관련 API
│   ├── generate.py              # [신규] 생성 관련 API
│   └── prompt.py                # [신규] 프롬프트 관련 API
│
└── templates/
    ├── titles/
    │   └── matching_panel.html  # [신규] 매칭 패널 UI
    └── generate/
        ├── preview_popup.html   # [신규] 생성 결과 미리보기 팝업
        └── module_settings.html # [신규] 생성 모듈 설정 UI
```

---

## 11. 구현 순서

### Phase 1: 기반 구조

- [ ] CrawledPost 모델 생성
- [ ] Blog 모델 확장 (크롤링 상태 필드, 플랫폼 필드)
- [ ] GenerateModule 모델 생성
- [ ] PromptModule 모델 생성
- [ ] 기본 스키마 정의
- [ ] DB 마이그레이션

### Phase 2: 크롤링 서비스

- [ ] CrawlService 기본 구조
- [ ] WordPressCrawler 구현 (RSS Feed / REST API)
- [ ] BloggerCrawler 구현 (Blogger API v3)
- [ ] 크롤링 데이터 저장 로직

### Phase 3: 매칭 서비스

- [ ] HybridMatchingService 구현
  - [ ] 지역명 필터링 로직 (v2)
  - [ ] 대표 제목만 매칭 최적화 (v1)
  - [ ] 이미 매칭된 제목 제외 로직
  - [ ] 복수 매칭 처리 로직
- [ ] 임계값 조회 로직 (생성 모듈 / 기본값)
- [ ] IndependentPostService 구현

### Phase 4: 생성/프롬프트 모듈

- [ ] 생성 모듈 설정 UI
  - [ ] 임계값 설정 (매칭/대기)
  - [ ] 스케줄 설정 (활성 시간대, 생성 간격)
  - [ ] 포스트 수 기반 생성 구간 설정
- [ ] 프롬프트 모듈 설정 UI
  - [ ] AI 벤더별 프롬프트 설정
  - [ ] 이미지 생성 프롬프트 설정
  - [ ] 블로그 연결 설정
  - [ ] 제목 재조합/줄바꿈 설정
- [ ] 조건 검증 로직 (4가지 필수 조건)

### Phase 5: UI 구현

- [ ] 정식 제목 탭 블로그 선택 드랍다운
- [ ] 매칭 결과 테이블 UI (이전 버전 참조)
- [ ] 독립포스트 글 생성 팝업
- [ ] 글 미리보기/HTML 변환/CSS 치환/웹 미리보기
- [ ] 발행 기능

### Phase 6: 자동화 통합

- [ ] 스케줄러 연동 (APScheduler)
- [ ] 생성 모듈 자동 실행 파이프라인
- [ ] 글/이미지 자동 삭제 스케줄
- [ ] 통합 테스트

---

## 12. 레거시 코드 참조

### 12.1 v1 유사도 매칭 (blogauto_new)

**파일**: `blogauto_new/core/similarity_utils.py`

**주요 함수**:
- `batch_similarity_match()`: 기본 배치 매칭
- `enhanced_batch_similarity_match()`: 학습 패턴 적용
- `two_stage_representative_matching()`: 캐싱 최적화 2단계 매칭
- `group_based_similarity_match()`: 그룹 ID 기반 매칭

### 12.2 v2 유사도 매칭 (현재)

**파일**: `shared/services/similarity_service.py`

**주요 메서드**:
- `calculate_similarity_v3()`: 다단계 하이브리드 (지역명 필터링 포함)
- `_check_location_compatibility()`: 지역명 호환성 검사

### 12.3 이전 버전 UI 참조

**파일**: `blogauto_new/templates/` (해당 템플릿 참조)

**참조 항목**:
- 매칭 결과 테이블 출력 방식
- 배지 스타일 및 색상
- 글 생성 결과 팝업 구조
- HTML 변환/CSS 치환 로직

---

## 13. 참고 문서

- [v1 레거시 분석 보고서](./legacy_similarity_analysis.md) (필요시 생성)
- [정식 제목 관리 설계](./main_title_management.md) (필요시 생성)
- [Flow/Module 시스템 설계](./flow_module_system.md) (필요시 생성)

---

**문서 작성**: Claude Code
**최종 수정**: 2025-01-25
