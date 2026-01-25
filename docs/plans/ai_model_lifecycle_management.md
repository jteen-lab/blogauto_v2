# AI 모델 수명주기 관리 시스템 구현 계획서

> **작성일**: 2026-01-24
> **버전**: v1.0
> **상태**: 계획 수립 완료

---

## 1. 개요

### 1.1 목적
AI 모델의 Deprecation(지원 중단) 정보를 자동으로 추적하고, 사용자에게 종료 예정 모델에 대한 경고 및 대체 모델 자동 마이그레이션 기능을 제공합니다.

### 1.2 핵심 결정 사항

| 항목 | 결정 |
|------|------|
| 업데이트 주기 | 자동 업데이트 (사용자 설정 주기) + 수동 업데이트 |
| 데이터 소스 | API 우선 |
| 알림 방식 | 모달 경고 |
| 기존 설정 처리 | 자동 마이그레이션 |

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AI 모델 수명주기 관리 시스템                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      데이터 수집 계층                           │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │ │
│  │  │ OpenAI API  │  │ Google API  │  │ Anthropic   │            │ │
│  │  │ models.list │  │ genai.list  │  │ (스크래핑)   │            │ │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │ │
│  │         │                │                │                    │ │
│  │         └────────────────┼────────────────┘                    │ │
│  │                          ▼                                     │ │
│  │              ┌───────────────────────┐                         │ │
│  │              │   Model Sync Service  │                         │ │
│  │              │   (데이터 수집/통합)    │                         │ │
│  │              └───────────┬───────────┘                         │ │
│  └──────────────────────────┼─────────────────────────────────────┘ │
│                             ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      데이터 저장 계층                           │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │                    ai_models 테이블                      │  │ │
│  │  │  - 모델 정보, 상태, 종료일, 대체 모델, 가격 정보          │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │               ai_model_sync_settings 테이블              │  │ │
│  │  │  - 동기화 주기, 마지막 동기화 시간, 활성화 여부           │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                             │                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      비즈니스 로직 계층                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐ │ │
│  │  │ Model Registry  │  │ Deprecation     │  │ Migration      │ │ │
│  │  │ Service         │  │ Checker         │  │ Service        │ │ │
│  │  │                 │  │                 │  │                │ │ │
│  │  │ - 모델 조회     │  │ - 종료 예정 체크│  │ - 자동 마이그  │ │ │
│  │  │ - 상태 관리     │  │ - 경고 생성     │  │ - 대체 모델    │ │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                             │                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                        API 계층                                │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ /api/v1/ai-models                                       │  │ │
│  │  │ GET  /              - 모델 목록 조회                     │  │ │
│  │  │ GET  /{id}          - 모델 상세 조회                     │  │ │
│  │  │ POST /sync          - 수동 동기화 실행                   │  │ │
│  │  │ GET  /deprecated    - 종료 예정 모델 조회                │  │ │
│  │  │ POST /migrate       - 자동 마이그레이션 실행             │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │ /api/v1/settings/ai-model-sync                          │  │ │
│  │  │ GET  /              - 동기화 설정 조회                   │  │ │
│  │  │ POST /              - 동기화 설정 저장                   │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                             │                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      프론트엔드 계층                            │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐ │ │
│  │  │ AI 탭           │  │ 경고 모달       │  │ 관리자 설정    │ │ │
│  │  │ (모델 선택 UI)  │  │ (종료 예정 알림)│  │ (동기화 주기)  │ │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 데이터베이스 설계

### 3.1 ai_models 테이블

```sql
CREATE TABLE ai_models (
    id SERIAL PRIMARY KEY,

    -- 기본 정보
    provider VARCHAR(50) NOT NULL,           -- openai, anthropic, google, nanobanana
    model_id VARCHAR(100) NOT NULL UNIQUE,   -- API에서 사용하는 모델 ID
    display_name VARCHAR(100),               -- 사용자에게 표시할 이름
    description TEXT,                        -- 모델 설명
    category VARCHAR(50) NOT NULL,           -- text, image, embedding, vision

    -- 상태 관리
    status VARCHAR(20) DEFAULT 'active',     -- active, deprecated, sunset, unknown
    deprecation_date DATE,                   -- Deprecated 시작일
    sunset_date DATE,                        -- 완전 종료일 (이후 사용 불가)
    deprecation_notice TEXT,                 -- 공식 안내 메시지

    -- 대체 모델 정보
    replacement_model_id VARCHAR(100),       -- 권장 대체 모델 ID
    migration_guide_url VARCHAR(500),        -- 마이그레이션 가이드 URL
    auto_migrate BOOLEAN DEFAULT TRUE,       -- 자동 마이그레이션 허용 여부

    -- 가격/무료 정보 (JSON)
    free_tier JSON,
    -- 예: {
    --   "requests_per_minute": 15,
    --   "requests_per_day": 1500,
    --   "tokens_per_minute": 1000000,
    --   "tokens_per_day": null,
    --   "note": "무료 사용 가능"
    -- }

    pricing JSON,
    -- 예: {
    --   "input_per_1m_tokens": 0.075,
    --   "output_per_1m_tokens": 0.30,
    --   "currency": "USD",
    --   "note": "2024년 1월 기준"
    -- }

    -- 모델 스펙 (JSON)
    capabilities JSON,
    -- 예: {
    --   "context_window": 1000000,
    --   "max_output_tokens": 8192,
    --   "supports_vision": true,
    --   "supports_function_calling": true,
    --   "supports_streaming": true
    -- }

    -- 정렬/표시
    sort_order INT DEFAULT 0,                -- 정렬 순서 (낮을수록 상단)
    is_recommended BOOLEAN DEFAULT FALSE,    -- 추천 모델 여부
    is_visible BOOLEAN DEFAULT TRUE,         -- 목록에 표시 여부

    -- 관리
    source VARCHAR(50) DEFAULT 'api',        -- api, manual, scraping
    last_checked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- 인덱스
    CONSTRAINT idx_provider_category UNIQUE (provider, model_id)
);

CREATE INDEX idx_ai_models_provider ON ai_models(provider);
CREATE INDEX idx_ai_models_category ON ai_models(category);
CREATE INDEX idx_ai_models_status ON ai_models(status);
CREATE INDEX idx_ai_models_sunset_date ON ai_models(sunset_date);
```

### 3.2 ai_model_sync_settings 테이블

```sql
CREATE TABLE ai_model_sync_settings (
    id SERIAL PRIMARY KEY,
    user_id INT DEFAULT 1,

    -- 동기화 설정
    auto_sync_enabled BOOLEAN DEFAULT TRUE,
    sync_interval VARCHAR(20) DEFAULT 'weekly',  -- daily, weekly, monthly
    sync_day_of_week INT DEFAULT 1,              -- 0=일, 1=월, ..., 6=토 (weekly일 때)
    sync_day_of_month INT DEFAULT 1,             -- 1-28 (monthly일 때)
    sync_hour INT DEFAULT 3,                     -- 실행 시간 (0-23)

    -- 알림 설정
    notify_deprecation BOOLEAN DEFAULT TRUE,     -- 종료 예정 모델 알림
    notify_days_before INT DEFAULT 30,           -- 종료 며칠 전부터 알림
    auto_migrate_enabled BOOLEAN DEFAULT TRUE,   -- 자동 마이그레이션 활성화

    -- 동기화 상태
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(20),                -- success, failed, partial
    last_sync_message TEXT,
    next_sync_at TIMESTAMP WITH TIME ZONE,

    -- 관리
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3.3 ai_model_migrations 테이블 (마이그레이션 이력)

```sql
CREATE TABLE ai_model_migrations (
    id SERIAL PRIMARY KEY,

    -- 대상
    blog_id INT NOT NULL,
    config_type VARCHAR(50) NOT NULL,            -- writing_ai, title_ai, image_ai

    -- 변경 내용
    old_provider VARCHAR(50),
    old_model_id VARCHAR(100),
    new_provider VARCHAR(50),
    new_model_id VARCHAR(100),

    -- 마이그레이션 정보
    reason VARCHAR(50) NOT NULL,                 -- sunset, deprecated, manual
    migration_type VARCHAR(20) NOT NULL,         -- auto, manual

    -- 상태
    status VARCHAR(20) DEFAULT 'completed',      -- completed, rolled_back, failed

    -- 관리
    migrated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    migrated_by VARCHAR(50) DEFAULT 'system'     -- system, user
);

CREATE INDEX idx_migrations_blog ON ai_model_migrations(blog_id);
CREATE INDEX idx_migrations_date ON ai_model_migrations(migrated_at);
```

---

## 4. API 설계

### 4.1 모델 관리 API

```yaml
# 모델 목록 조회
GET /api/v1/ai-models
Query Parameters:
  - provider: string (optional) - 제공자 필터
  - category: string (optional) - 카테고리 필터 (text, image)
  - status: string (optional) - 상태 필터 (active, deprecated)
  - include_sunset: boolean (optional, default: false) - 종료된 모델 포함
Response:
  {
    "models": [
      {
        "id": 1,
        "provider": "google",
        "model_id": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "category": "text",
        "status": "active",
        "sunset_date": null,
        "replacement_model_id": null,
        "free_tier": {...},
        "pricing": {...},
        "capabilities": {...},
        "is_recommended": true
      }
    ],
    "total": 45,
    "deprecated_count": 3,
    "by_provider": {"google": 15, "openai": 18, "anthropic": 12}
  }

# 종료 예정 모델 조회
GET /api/v1/ai-models/deprecated
Query Parameters:
  - days_until_sunset: int (optional, default: 90) - N일 내 종료 예정
Response:
  {
    "deprecated_models": [
      {
        "model_id": "gemini-1.0-pro",
        "display_name": "Gemini 1.0 Pro",
        "sunset_date": "2025-03-01",
        "days_remaining": 35,
        "replacement": {
          "model_id": "gemini-1.5-flash",
          "display_name": "Gemini 1.5 Flash"
        },
        "affected_blogs": [1, 5, 8]  // 이 모델을 사용 중인 블로그 ID
      }
    ]
  }

# 수동 동기화 실행
POST /api/v1/ai-models/sync
Request Body:
  {
    "providers": ["google", "openai", "anthropic"]  // optional, 전체면 생략
  }
Response:
  {
    "status": "success",
    "synced_at": "2026-01-24T12:00:00Z",
    "summary": {
      "added": 2,
      "updated": 5,
      "deprecated": 1,
      "removed": 0
    },
    "changes": [
      {"action": "added", "model_id": "gemini-3-pro"},
      {"action": "deprecated", "model_id": "gemini-1.0-pro", "sunset_date": "2025-03-01"}
    ]
  }

# 자동 마이그레이션 실행
POST /api/v1/ai-models/migrate
Request Body:
  {
    "blog_ids": [1, 5, 8],  // optional, 전체면 생략
    "dry_run": false        // true면 미리보기만
  }
Response:
  {
    "status": "success",
    "migrations": [
      {
        "blog_id": 1,
        "config_type": "writing_ai",
        "old_model": "gemini-1.0-pro",
        "new_model": "gemini-1.5-flash",
        "reason": "sunset"
      }
    ],
    "skipped": [],
    "failed": []
  }
```

### 4.2 동기화 설정 API

```yaml
# 동기화 설정 조회
GET /api/v1/settings/ai-model-sync
Response:
  {
    "auto_sync_enabled": true,
    "sync_interval": "weekly",
    "sync_day_of_week": 1,
    "sync_hour": 3,
    "notify_deprecation": true,
    "notify_days_before": 30,
    "auto_migrate_enabled": true,
    "last_sync_at": "2026-01-20T03:00:00Z",
    "last_sync_status": "success",
    "next_sync_at": "2026-01-27T03:00:00Z"
  }

# 동기화 설정 저장
POST /api/v1/settings/ai-model-sync
Request Body:
  {
    "auto_sync_enabled": true,
    "sync_interval": "weekly",
    "sync_day_of_week": 1,
    "sync_hour": 3,
    "notify_deprecation": true,
    "notify_days_before": 30,
    "auto_migrate_enabled": true
  }
```

---

## 5. 서비스 구현

### 5.1 Model Sync Service (데이터 수집)

```python
# app/services/model_sync_service.py

class ModelSyncService:
    """AI 모델 동기화 서비스"""

    async def sync_all_providers(self) -> SyncResult:
        """모든 제공자의 모델 정보 동기화"""
        results = []

        # 각 제공자별 동기화
        results.append(await self.sync_openai_models())
        results.append(await self.sync_google_models())
        results.append(await self.sync_anthropic_models())

        return self._merge_results(results)

    async def sync_openai_models(self) -> ProviderSyncResult:
        """OpenAI 모델 동기화"""
        # 1. API로 활성 모델 목록 조회
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        models = await client.models.list()

        # 2. Deprecation 정보는 공식 문서에서 스크래핑 (필요 시)
        deprecations = await self._fetch_openai_deprecations()

        # 3. DB 업데이트
        return await self._update_models('openai', models, deprecations)

    async def sync_google_models(self) -> ProviderSyncResult:
        """Google Gemini 모델 동기화"""
        # 1. Gemini API로 모델 목록 조회
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        models = genai.list_models()

        # 2. Deprecation 정보 수집
        deprecations = await self._fetch_google_deprecations()

        # 3. DB 업데이트
        return await self._update_models('google', models, deprecations)

    async def sync_anthropic_models(self) -> ProviderSyncResult:
        """Anthropic 모델 동기화"""
        # Anthropic은 공식 API로 모델 목록 제공 안 함
        # 공식 문서 스크래핑 또는 하드코딩된 목록 사용
        models = await self._fetch_anthropic_models()
        deprecations = await self._fetch_anthropic_deprecations()

        return await self._update_models('anthropic', models, deprecations)

    async def _fetch_google_deprecations(self) -> List[DeprecationInfo]:
        """Google Deprecation 문서 파싱"""
        url = "https://ai.google.dev/gemini-api/docs/deprecations"
        # HTML 파싱하여 모델별 종료일 추출
        ...
```

### 5.2 Deprecation Checker Service

```python
# app/services/deprecation_checker.py

class DeprecationCheckerService:
    """모델 종료 예정 체크 서비스"""

    async def check_blog_models(self, blog_id: int) -> List[DeprecationWarning]:
        """특정 블로그의 AI 설정에서 종료 예정 모델 체크"""
        blog = await self.blog_repo.get(blog_id)
        warnings = []

        for config_type in ['writing_ai', 'title_ai', 'image_ai']:
            config = blog.ai_config.get(config_type, {})
            model_id = config.get('model')

            if model_id:
                model = await self.model_repo.get_by_model_id(model_id)
                if model and model.is_deprecated_soon(days=30):
                    warnings.append(DeprecationWarning(
                        blog_id=blog_id,
                        config_type=config_type,
                        model=model,
                        replacement=await self.get_replacement(model)
                    ))

        return warnings

    async def get_all_deprecated_usages(self) -> List[DeprecationWarning]:
        """모든 블로그에서 종료 예정 모델 사용 현황 조회"""
        deprecated_models = await self.model_repo.get_deprecated_models()
        warnings = []

        for model in deprecated_models:
            blogs = await self.blog_repo.find_by_model(model.model_id)
            for blog in blogs:
                warnings.append(...)

        return warnings
```

### 5.3 Migration Service

```python
# app/services/migration_service.py

class MigrationService:
    """AI 모델 자동 마이그레이션 서비스"""

    async def migrate_blog(
        self,
        blog_id: int,
        config_type: str,
        dry_run: bool = False
    ) -> MigrationResult:
        """특정 블로그의 AI 설정 마이그레이션"""
        blog = await self.blog_repo.get(blog_id)
        config = blog.ai_config.get(config_type, {})

        old_model_id = config.get('model')
        old_model = await self.model_repo.get_by_model_id(old_model_id)

        if not old_model or old_model.status == 'active':
            return MigrationResult(skipped=True, reason="Model is active")

        # 대체 모델 찾기
        new_model = await self._find_replacement(old_model, config_type)

        if not new_model:
            return MigrationResult(failed=True, reason="No replacement found")

        if dry_run:
            return MigrationResult(
                dry_run=True,
                old_model=old_model_id,
                new_model=new_model.model_id
            )

        # 실제 마이그레이션 수행
        blog.ai_config[config_type]['model'] = new_model.model_id
        await self.blog_repo.update(blog)

        # 이력 저장
        await self._save_migration_history(
            blog_id, config_type, old_model_id, new_model.model_id
        )

        return MigrationResult(
            success=True,
            old_model=old_model_id,
            new_model=new_model.model_id
        )

    async def _find_replacement(
        self,
        model: AIModel,
        config_type: str
    ) -> Optional[AIModel]:
        """대체 모델 찾기"""
        # 1. 명시적으로 지정된 대체 모델
        if model.replacement_model_id:
            replacement = await self.model_repo.get_by_model_id(
                model.replacement_model_id
            )
            if replacement and replacement.status == 'active':
                return replacement

        # 2. 같은 제공자의 추천 모델
        recommended = await self.model_repo.get_recommended(
            provider=model.provider,
            category=model.category
        )
        if recommended:
            return recommended

        # 3. 같은 제공자의 최신 활성 모델
        latest = await self.model_repo.get_latest_active(
            provider=model.provider,
            category=model.category
        )
        return latest
```

---

## 6. 스케줄러 구현

```python
# app/scheduler/model_sync_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class ModelSyncScheduler:
    """모델 동기화 스케줄러"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.job_id = "ai_model_sync"

    async def start(self):
        """스케줄러 시작"""
        settings = await self._load_settings()

        if settings.auto_sync_enabled:
            self._schedule_sync(settings)

        self.scheduler.start()

    def _schedule_sync(self, settings: SyncSettings):
        """동기화 작업 스케줄링"""
        if settings.sync_interval == 'daily':
            trigger = CronTrigger(hour=settings.sync_hour)
        elif settings.sync_interval == 'weekly':
            trigger = CronTrigger(
                day_of_week=settings.sync_day_of_week,
                hour=settings.sync_hour
            )
        elif settings.sync_interval == 'monthly':
            trigger = CronTrigger(
                day=settings.sync_day_of_month,
                hour=settings.sync_hour
            )

        self.scheduler.add_job(
            self._run_sync,
            trigger=trigger,
            id=self.job_id,
            replace_existing=True
        )

    async def _run_sync(self):
        """동기화 실행"""
        logger.info("AI 모델 동기화 시작")

        try:
            # 1. 모델 동기화
            sync_service = ModelSyncService()
            result = await sync_service.sync_all_providers()

            # 2. 종료 예정 모델 체크 및 자동 마이그레이션
            settings = await self._load_settings()
            if settings.auto_migrate_enabled:
                migration_service = MigrationService()
                await migration_service.migrate_all_deprecated()

            # 3. 상태 업데이트
            await self._update_sync_status('success', result)

        except Exception as e:
            logger.error(f"AI 모델 동기화 실패: {e}")
            await self._update_sync_status('failed', str(e))

    async def update_schedule(self, settings: SyncSettings):
        """스케줄 설정 업데이트"""
        self.scheduler.remove_job(self.job_id)

        if settings.auto_sync_enabled:
            self._schedule_sync(settings)
```

---

## 7. 프론트엔드 구현

### 7.1 AI 탭 모델 선택 (수정)

```html
<!-- 모델 선택 드롭다운 (DB에서 조회) -->
<select x-model="aiConfig.writing_ai.model">
    <option value="">선택하세요</option>
    <template x-for="model in getModelsForProvider('writing_ai')" :key="model.model_id">
        <option
            :value="model.model_id"
            :class="{'text-orange-600': model.status === 'deprecated'}"
            :disabled="model.status === 'sunset'">
            <span x-text="model.display_name"></span>
            <span x-show="model.is_recommended">✨</span>
            <span x-show="model.status === 'deprecated'">
                ⚠️ (종료 예정: <span x-text="model.sunset_date"></span>)
            </span>
        </option>
    </template>
</select>

<!-- 모델 정보 표시 -->
<div x-show="selectedModel" class="mt-2 p-3 bg-gray-50 rounded-lg text-sm">
    <div class="flex items-center gap-2 mb-2">
        <span class="font-medium" x-text="selectedModel.display_name"></span>
        <span x-show="selectedModel.is_recommended"
              class="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
            추천
        </span>
    </div>

    <!-- 무료 정보 -->
    <div x-show="selectedModel.free_tier" class="text-green-600">
        💚 무료: <span x-text="formatFreeTier(selectedModel.free_tier)"></span>
    </div>

    <!-- 가격 정보 -->
    <div x-show="selectedModel.pricing" class="text-gray-600">
        💰 <span x-text="formatPricing(selectedModel.pricing)"></span>
    </div>

    <!-- 컨텍스트 크기 -->
    <div x-show="selectedModel.capabilities?.context_window" class="text-gray-600">
        📝 컨텍스트: <span x-text="formatTokens(selectedModel.capabilities.context_window)"></span>
    </div>
</div>
```

### 7.2 종료 예정 경고 모달

```html
<!-- 종료 예정 모델 경고 모달 -->
<div x-show="showDeprecationModal"
     class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden">
        <!-- 헤더 -->
        <div class="bg-orange-500 px-6 py-4">
            <div class="flex items-center gap-3 text-white">
                <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
                <h3 class="text-xl font-bold">종료 예정 모델 알림</h3>
            </div>
        </div>

        <!-- 본문 -->
        <div class="p-6">
            <p class="text-gray-700 mb-4">
                현재 사용 중인 AI 모델이 곧 종료됩니다.
                서비스 중단을 방지하기 위해 대체 모델로 변경하시기 바랍니다.
            </p>

            <!-- 종료 예정 모델 목록 -->
            <div class="space-y-3 mb-6">
                <template x-for="warning in deprecationWarnings" :key="warning.model_id">
                    <div class="border border-orange-200 rounded-lg p-4 bg-orange-50">
                        <div class="flex justify-between items-start mb-2">
                            <div>
                                <span class="font-medium" x-text="warning.display_name"></span>
                                <span class="text-sm text-gray-500 ml-2"
                                      x-text="'(' + warning.config_type_display + ')'"></span>
                            </div>
                            <span class="px-2 py-1 bg-red-100 text-red-700 text-xs rounded-full"
                                  x-text="warning.days_remaining + '일 후 종료'"></span>
                        </div>

                        <div class="text-sm text-gray-600">
                            종료일: <span x-text="warning.sunset_date"></span>
                        </div>

                        <!-- 추천 대체 모델 -->
                        <div class="mt-3 p-3 bg-white rounded border border-green-200">
                            <div class="text-sm text-green-700 font-medium mb-1">
                                ✅ 추천 대체 모델
                            </div>
                            <div class="flex items-center justify-between">
                                <span x-text="warning.replacement.display_name"></span>
                                <button @click="migrateModel(warning)"
                                        class="px-3 py-1 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700">
                                    변경하기
                                </button>
                            </div>
                        </div>
                    </div>
                </template>
            </div>

            <!-- 일괄 변경 버튼 -->
            <div class="flex gap-3">
                <button @click="migrateAllModels()"
                        class="flex-1 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700">
                    모두 대체 모델로 변경
                </button>
                <button @click="showDeprecationModal = false"
                        class="flex-1 py-3 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200">
                    나중에
                </button>
            </div>

            <!-- 다시 보지 않기 옵션 -->
            <label class="flex items-center gap-2 mt-4 text-sm text-gray-500 cursor-pointer">
                <input type="checkbox" x-model="dontShowAgain" class="rounded">
                <span>이 모델에 대해 다시 알리지 않기</span>
            </label>
        </div>
    </div>
</div>
```

### 7.3 관리자 설정 페이지 (동기화 설정)

```html
<!-- 전역 설정 > AI 모델 동기화 설정 -->
<div class="bg-white border border-gray-200 rounded-lg p-6">
    <h3 class="text-lg font-semibold text-gray-900 mb-4">AI 모델 동기화 설정</h3>

    <!-- 자동 동기화 -->
    <div class="mb-6">
        <label class="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" x-model="syncSettings.auto_sync_enabled"
                   class="w-5 h-5 rounded border-gray-300 text-blue-600">
            <div>
                <span class="font-medium">자동 동기화 활성화</span>
                <p class="text-sm text-gray-500">AI 모델 목록을 주기적으로 업데이트합니다</p>
            </div>
        </label>
    </div>

    <!-- 동기화 주기 -->
    <div x-show="syncSettings.auto_sync_enabled" class="space-y-4 mb-6">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">동기화 주기</label>
            <select x-model="syncSettings.sync_interval"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="daily">매일</option>
                <option value="weekly">매주</option>
                <option value="monthly">매월</option>
            </select>
        </div>

        <!-- 요일 선택 (weekly) -->
        <div x-show="syncSettings.sync_interval === 'weekly'">
            <label class="block text-sm font-medium text-gray-700 mb-2">요일</label>
            <select x-model="syncSettings.sync_day_of_week"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="0">일요일</option>
                <option value="1">월요일</option>
                <option value="2">화요일</option>
                <option value="3">수요일</option>
                <option value="4">목요일</option>
                <option value="5">금요일</option>
                <option value="6">토요일</option>
            </select>
        </div>

        <!-- 날짜 선택 (monthly) -->
        <div x-show="syncSettings.sync_interval === 'monthly'">
            <label class="block text-sm font-medium text-gray-700 mb-2">날짜</label>
            <select x-model="syncSettings.sync_day_of_month"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <template x-for="day in Array.from({length: 28}, (_, i) => i + 1)">
                    <option :value="day" x-text="day + '일'"></option>
                </template>
            </select>
        </div>

        <!-- 시간 -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">시간</label>
            <select x-model="syncSettings.sync_hour"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <template x-for="hour in Array.from({length: 24}, (_, i) => i)">
                    <option :value="hour" x-text="hour + '시'"></option>
                </template>
            </select>
        </div>
    </div>

    <!-- 알림 설정 -->
    <div class="border-t pt-6 mb-6">
        <h4 class="font-medium text-gray-900 mb-4">알림 설정</h4>

        <label class="flex items-center gap-3 cursor-pointer mb-4">
            <input type="checkbox" x-model="syncSettings.notify_deprecation"
                   class="w-5 h-5 rounded border-gray-300 text-blue-600">
            <div>
                <span class="font-medium">종료 예정 모델 알림</span>
                <p class="text-sm text-gray-500">사용 중인 모델이 종료 예정일 때 알림</p>
            </div>
        </label>

        <div x-show="syncSettings.notify_deprecation" class="ml-8">
            <label class="block text-sm font-medium text-gray-700 mb-2">
                종료 며칠 전부터 알림
            </label>
            <select x-model="syncSettings.notify_days_before"
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="7">7일 전</option>
                <option value="14">14일 전</option>
                <option value="30">30일 전</option>
                <option value="60">60일 전</option>
                <option value="90">90일 전</option>
            </select>
        </div>
    </div>

    <!-- 자동 마이그레이션 -->
    <div class="border-t pt-6 mb-6">
        <label class="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" x-model="syncSettings.auto_migrate_enabled"
                   class="w-5 h-5 rounded border-gray-300 text-blue-600">
            <div>
                <span class="font-medium">자동 마이그레이션</span>
                <p class="text-sm text-gray-500">모델 종료 시 자동으로 대체 모델로 변경</p>
            </div>
        </label>
    </div>

    <!-- 동기화 상태 -->
    <div class="border-t pt-6 mb-6">
        <h4 class="font-medium text-gray-900 mb-4">동기화 상태</h4>

        <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
                <span class="text-gray-500">마지막 동기화:</span>
                <span class="ml-2" x-text="formatDateTime(syncSettings.last_sync_at)"></span>
            </div>
            <div>
                <span class="text-gray-500">상태:</span>
                <span class="ml-2"
                      :class="syncSettings.last_sync_status === 'success' ? 'text-green-600' : 'text-red-600'"
                      x-text="syncSettings.last_sync_status === 'success' ? '성공' : '실패'"></span>
            </div>
            <div>
                <span class="text-gray-500">다음 동기화:</span>
                <span class="ml-2" x-text="formatDateTime(syncSettings.next_sync_at)"></span>
            </div>
        </div>
    </div>

    <!-- 버튼 -->
    <div class="flex gap-3">
        <button @click="saveSettings()"
                class="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700">
            설정 저장
        </button>
        <button @click="syncNow()"
                :disabled="syncing"
                class="px-6 py-3 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200">
            <span x-show="!syncing">지금 동기화</span>
            <span x-show="syncing" class="flex items-center gap-2">
                <svg class="w-4 h-4 animate-spin" viewBox="0 0 24 24">...</svg>
                동기화 중...
            </span>
        </button>
    </div>
</div>
```

---

## 8. 구현 단계

### Phase 1: 기반 구축 (우선순위 높음)
1. **DB 테이블 생성** - ai_models, ai_model_sync_settings
2. **초기 데이터 입력** - 현재 하드코딩된 모델 목록을 DB로 이전
3. **Model Registry Service** - 기본 CRUD
4. **AI 탭 수정** - DB에서 모델 조회하도록 변경

### Phase 2: 동기화 시스템 (우선순위 중간)
5. **Model Sync Service** - 각 API별 동기화 로직
6. **Deprecation Checker** - 종료 예정 모델 체크
7. **스케줄러 구현** - APScheduler 통합
8. **동기화 설정 API/UI** - 관리자 설정 페이지

### Phase 3: 사용자 경험 (우선순위 중간)
9. **종료 예정 경고 모달** - UI 구현
10. **Migration Service** - 자동 마이그레이션
11. **마이그레이션 이력** - 로그 및 롤백

### Phase 4: 고급 기능 (우선순위 낮음)
12. **가격/무료 정보 표시** - 모델별 비용 정보
13. **모델 비교 기능** - 성능/가격 비교
14. **관리자 대시보드** - 모델 현황 통계

---

## 9. 예상 일정

| Phase | 작업 | 예상 기간 |
|-------|------|----------|
| Phase 1 | 기반 구축 | 2-3일 |
| Phase 2 | 동기화 시스템 | 3-4일 |
| Phase 3 | 사용자 경험 | 2-3일 |
| Phase 4 | 고급 기능 | 2-3일 |
| **총합** | | **9-13일** |

---

## 10. 고려사항

### 10.1 API 제한
- OpenAI/Google API는 Rate Limit이 있으므로 동기화 시 고려
- Anthropic은 공식 모델 목록 API가 없어 스크래핑 필요

### 10.2 데이터 정확성
- 공식 문서의 구조 변경 시 스크래핑 로직 수정 필요
- 수동 검증 기능 포함 권장

### 10.3 롤백
- 자동 마이그레이션 후 문제 발생 시 롤백 기능 필요
- 마이그레이션 이력 보관

---

이 계획서를 기반으로 구현을 진행할까요?
