# 프롬프트 모듈 + 생성 모듈 자동화 파이프라인 개선 계획서

## 문서 정보

| 항목 | 내용 |
|------|------|
| **작성일** | 2026-03-02 |
| **버전** | v1.0.0 |
| **대상** | Claude Code 구현 에이전트 |
| **범위** | Phase A ~ Phase D + Step-by-Step 테스트 API |

---

## 1. 배경 및 목표

### 1.1 현재 상태 요약

현재 프롬프트 모듈(prompt 타입 Module)의 UI에서 카테고리, 블로그, AI 설정, 이미지 설정 등을 저장할 수 있지만, 실제 글 생성 파이프라인에서는 이 설정들이 제대로 활용되지 않는 문제가 있습니다.

구체적인 GAP:

| GAP ID | 문제 | 영향 |
|--------|------|------|
| G1 | InventoryTrigger가 Module.settings.categories를 무시하고 BlogCategory(블로그 설정)를 사용 | 프롬프트 모듈의 카테고리 선택이 의미 없음 |
| G2 | 제목 선택 시 `created_at ASC LIMIT 1`로 항상 첫 번째만 선택 | 다양한 제목이 활용되지 않음 |
| G3 | 이미지 생성 전체 미구현 (AI + 템플릿 오버레이) | 이미지 없이 글만 생성됨 |
| G4 | 단계별 테스트 기능 없음 | 문제 발생 시 원인 파악 어려움 |
| G5 | settings 레거시 키(`generation_prompt`)와 새 구조(`content_generation.user_prompt_template`) 혼재 | 설정값 출처가 불명확 |
| G6 | 프롬프트 모듈의 AI 설정(provider/temperature 등)이 ContentGenerator에서 무시됨 | Blog.ai_config만 사용됨 |
| G7 | Blog.image_mode 분기 처리 미구현 | ai/template/both 구분 불가 |

### 1.2 목표 상태

```
프롬프트 모듈 설정이 실제 파이프라인에서 활용되어:
1. 모듈에서 선택한 카테고리로 제목이 필터링되고 (Phase A)
2. 모듈에서 선택한 AI 설정이 글 생성에 사용되며 (Phase B)
3. 이미지가 AI 또는 템플릿 방식으로 생성되고 (Phase C)
4. 각 단계를 개별 테스트할 수 있다 (Phase D)
```

### 1.3 설정 우선순위 원칙

모든 설정값은 다음 우선순위를 따릅니다:

```
1순위: Module.settings (프롬프트 모듈 설정) <- 가장 구체적
2순위: Blog.ai_config (블로그 설정)
3순위: 하드코딩된 기본값
```

비유하면 "모듈 설정 = 작업 지시서, 블로그 설정 = 회사 기본 방침, 기본값 = 업계 관행"과 같습니다. 작업 지시서가 있으면 그걸 따르고, 없으면 회사 방침을, 그마저도 없으면 업계 관행을 따르는 구조입니다.

---

## 2. 관련 파일 맵

### 2.1 핵심 파일 (수정 대상)

```
services/republish/app/
├── services/generation/
│   ├── inventory_trigger.py       <- Phase A: 카테고리 소스 + 랜덤 선택
│   ├── generator.py               <- Phase B: AI 설정 정규화 + Phase C: 이미지 단계 추가
│   ├── flow_generate_executor.py  <- Phase A: module_settings 전달
│   ├── title_recombiner.py        <- Phase B: AI provider 우선순위 적용
│   └── image_generator.py         <- Phase C: 새로 생성
│       ai_image_service.py        <- Phase C: 새로 생성
│       template_image_service.py  <- Phase C: 새로 생성
├── services/ai/
│   └── ai_service.py              <- Phase B: system_prompt 파라미터 추가
├── routers/
│   └── generation_test.py         <- Phase D: 새로 생성
└── services/generation/
    └── pipeline_tester.py         <- Phase D: 새로 생성
```

### 2.2 프롬프트 모듈 settings JSONB 전체 구조 (참조)

아래는 Module.settings 컬럼에 저장되는 JSON 전체 구조입니다. 각 Phase에서 어떤 키를 사용하는지 참고하세요.

```json
{
  "categories": [{"topic_id": "int", "subtopic_id": "int|null"}],
  "blogs": ["int"],
  "title_recombine": {
    "enabled": "bool",
    "styles": ["emotional", "practical"],
    "count_per_style": "int",
    "custom_prompt": "str"
  },
  "reference": {
    "enabled": true,
    "max_search": "int",
    "crawl_target": "int",
    "summary_count": "int",
    "summary_method": "ai|algorithm",
    "ai_provider": "str",
    "ai_model": "str",
    "summary_style": "str",
    "algorithm_type": "str",
    "max_length": "int"
  },
  "content_generation": {
    "enabled": "bool",
    "provider": "str",
    "temperature": "float",
    "max_tokens": "int",
    "top_p": "float",
    "frequency_penalty": "float",
    "presence_penalty": "float",
    "top_k": "int",
    "system_prompt": "str",
    "user_prompt_template": "str"
  },
  "image_generation": {
    "enabled": "bool",
    "provider": "dalle|nanobanana",
    "prompt_template": "str",
    "images_per_post": "int",
    "dalle": {"size": "str", "quality": "str", "style": "str"},
    "nanobanana": {"aspectRatio": "str", "style": "str"}
  }
}
```

### 2.3 Blog 모델 관련 필드 (참조)

```python
# Blog.ai_config (JSONB)
{
  "title_ai": {"provider": "str", "model": "str"},
  "writing_ai": {"provider": "str", "model": "str"}
}

# Blog.image_mode (String): "ai" | "template" | "both"
# Blog.overlay_config (JSONB): 템플릿 이미지 설정
# Blog.placeholders (JSONB): HTML/CSS/텍스트 치환 설정
```

---

## 3. Phase A: 프롬프트 모듈 카테고리 기반 제목 선택 + 랜덤화

### 3.1 개요

| 항목 | 내용 |
|------|------|
| **해결하는 GAP** | G1, G2 |
| **수정 파일** | `inventory_trigger.py`, `flow_generate_executor.py` |
| **난이도** | 낮음 |

### 3.2 변경 전후 동작 비교

**변경 전** (현재 동작):

```
FlowGenerateExecutor.execute_for_blog()
  -> InventoryTrigger.check_inventory(blog_id)
    -> _find_available_title(blog_id)
      -> _get_blog_category_filter_ids(blog_id)  <- BlogCategory 테이블 조회
      -> _query_title_with_filters(..., LIMIT 1)  <- 항상 첫 번째
```

**변경 후** (목표 동작):

```
FlowGenerateExecutor.execute_for_blog()
  -> InventoryTrigger.check_inventory(blog_id, module_settings=module.settings)
    -> _find_available_title(blog_id, module_settings)
      -> _parse_module_categories(settings["categories"])  <- 모듈 설정 우선
      -> (없으면) _get_blog_category_filter_ids(blog_id)   <- 기존 방식 폴백
      -> _query_title_with_filters(..., LIMIT 10)
      -> random.choice(candidates)  <- 랜덤 선택
```

### 3.3 구현 상세

#### 3.3.1 `inventory_trigger.py` 수정

**변경 1: `check_inventory()` 시그니처 변경**

```python
# 파일: services/republish/app/services/generation/inventory_trigger.py
# 위치: check_inventory() 메서드

# 변경 전 (Line 49-52)
async def check_inventory(
    self, blog_id: int,
    min_inventory: Optional[int] = None,
) -> InventoryCheckResult:

# 변경 후
async def check_inventory(
    self, blog_id: int,
    min_inventory: Optional[int] = None,
    module_settings: Optional[dict] = None,
) -> InventoryCheckResult:
```

**변경 2: `_find_available_title()` 호출 시 module_settings 전달**

```python
# 위치: check_inventory() 내부 (현재 Line 84)

# 변경 전
title = await self._find_available_title(blog_id)

# 변경 후
title = await self._find_available_title(blog_id, module_settings)
```

**변경 3: `_find_available_title()` 수정**

```python
# 위치: _find_available_title() 메서드 (현재 Line 199-265)

# 변경 전 시그니처
async def _find_available_title(self, blog_id: int) -> Optional[MainTitle]:

# 변경 후 시그니처
async def _find_available_title(
    self, blog_id: int, module_settings: Optional[dict] = None
) -> Optional[MainTitle]:
```

메서드 본문 변경:

```python
async def _find_available_title(
    self, blog_id: int, module_settings: Optional[dict] = None
) -> Optional[MainTitle]:
    """카테고리 필터링 적용하여 사용 가능한 제목 1개를 랜덤 선택"""
    blog_id_str = str(blog_id)

    # 카테고리 소스 결정: 모듈 설정 우선, 없으면 BlogCategory 폴백
    if module_settings and module_settings.get("categories"):
        subtopic_ids, topic_only_ids = self._parse_module_categories(
            module_settings["categories"]
        )
        category_source = "module_settings"
    else:
        subtopic_ids, topic_only_ids = await self._get_blog_category_filter_ids(blog_id)
        category_source = "blog_category"

    has_category = bool(subtopic_ids or topic_only_ids)

    logger.debug(
        f"[INVENTORY] 카테고리 소스: {category_source} | "
        f"subtopic_ids={subtopic_ids}, topic_only_ids={topic_only_ids}"
    )

    # 이하 기존 로직과 동일하되
    # _query_title_with_filters 내부에서 LIMIT 10 + 랜덤 선택 적용
    # ... (변경 5 참조)
```

**변경 4: 새 메서드 `_parse_module_categories()` 추가**

```python
def _parse_module_categories(
    self, categories: list
) -> Tuple[Set[int], Set[int]]:
    """
    모듈 settings.categories에서 subtopic_id / topic_id 집합 분리

    Args:
        categories: [{"topic_id": 1, "subtopic_id": 3}, {"topic_id": 2, "subtopic_id": null}]

    Returns:
        (subtopic_ids, topic_only_ids) 튜플
        - subtopic_ids: subtopic_id가 있는 항목의 subtopic_id 집합
        - topic_only_ids: subtopic_id가 없는 항목의 topic_id 집합
    """
    subtopic_ids: Set[int] = set()
    topic_only_ids: Set[int] = set()

    for cat in categories:
        if cat.get("subtopic_id"):
            subtopic_ids.add(cat["subtopic_id"])
        elif cat.get("topic_id"):
            topic_only_ids.add(cat["topic_id"])

    return subtopic_ids, topic_only_ids
```

**변경 5: `_query_title_with_filters()` -> 랜덤 선택으로 수정**

```python
# 변경 전 (Line 267-300)
async def _query_title_with_filters(self, blog_id_str, category_conditions, matched_only):
    # ... 조건 구성 ...
    query = select(MainTitle).where(*conditions).order_by(MainTitle.created_at.asc()).limit(1)
    result = await self.db.execute(query)
    return result.scalar_one_or_none()

# 변경 후
import random  # 파일 상단 import에 추가

async def _query_title_with_filters(self, blog_id_str, category_conditions, matched_only):
    # ... 조건 구성 (기존과 동일) ...
    query = select(MainTitle).where(*conditions).limit(10)  # LIMIT 10으로 변경
    result = await self.db.execute(query)
    candidates = list(result.scalars().all())
    return random.choice(candidates) if candidates else None  # 랜덤 선택
```

#### 3.3.2 `flow_generate_executor.py` 수정

```python
# 파일: services/republish/app/services/generation/flow_generate_executor.py
# 위치: execute_for_blog() 메서드 내부 (현재 Line 71-73)

# 변경 전
check_result = await self.inventory_trigger.check_inventory(
    blog_id, min_inventory=min_inventory,
)

# 변경 후
module_settings = module.settings or {}
check_result = await self.inventory_trigger.check_inventory(
    blog_id, min_inventory=min_inventory,
    module_settings=module_settings,
)
```

### 3.4 테스트 관점

- 프롬프트 모듈에 `categories=[{"topic_id":1, "subtopic_id":3}]` 설정 후 실행 -> 해당 카테고리 제목만 선택되는지 확인
- categories가 빈 배열이면 기존 BlogCategory 폴백이 동작하는지 확인
- 동일 조건으로 여러 번 실행 시 다른 제목이 선택되는지 확인 (랜덤)

---

## 4. Phase B: 설정값 정규화 (프롬프트 모듈 우선)

### 4.1 개요

| 항목 | 내용 |
|------|------|
| **해결하는 GAP** | G5, G6 |
| **수정 파일** | `generator.py`, `ai_service.py` |
| **난이도** | 중간 |

### 4.2 변경 전후 동작 비교

**변경 전** (현재 동작):

```
ContentGenerator._generate_content_with_meta()
  프롬프트: settings.get("generation_prompt")     <- 레거시 키
  AI: Blog.ai_config.writing_ai.provider/model    <- 블로그 설정만
  온도: 하드코딩 0.7
  토큰: 하드코딩 4000
  시스템 프롬프트: 미지원

TitleRecombiner.recombine()
  AI: Blog.ai_config.title_ai.provider            <- 블로그 설정만
```

**변경 후** (목표 동작):

```
ContentGenerator._generate_content_with_meta()
  프롬프트: settings.content_generation.user_prompt_template
           -> settings.generation_prompt -> 기본값
  AI: settings.content_generation.provider
      -> Blog.ai_config.writing_ai.provider
  온도: settings.content_generation.temperature -> 0.7
  토큰: settings.content_generation.max_tokens -> 4000
  시스템 프롬프트: settings.content_generation.system_prompt (있으면 사용)

TitleRecombiner 호출 시:
  AI: settings.content_generation.provider
      -> Blog.ai_config.title_ai.provider
```

### 4.3 구현 상세

#### 4.3.1 `ai_service.py` 수정 - system_prompt 지원

```python
# 파일: services/republish/app/services/ai/ai_service.py
```

**변경 1: `generate()` 시그니처에 system_prompt 추가 (Line 28-35)**

```python
async def generate(
    self,
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,  # 추가
) -> Optional[dict]:
```

**변경 2: `_try_provider()`에 system_prompt 전달 (Line 52-54)**

```python
result = await self._try_provider(
    prov, prompt, model, max_tokens, temperature, system_prompt
)
```

**변경 3: `_try_provider()` 시그니처 변경 (Line 123)**

```python
async def _try_provider(
    self, provider, prompt, model, max_tokens, temperature, system_prompt=None
) -> Optional[dict]:
```

**변경 4: `_try_provider` 내부에서 각 `_call_*` 함수 호출 시 system_prompt 전달**

```python
# _try_provider 내부 (현재 Line 150-170)
if provider == AIProvider.OPENAI:
    content = await self._call_openai(
        key.api_key, prompt, model or "gpt-4o-mini",
        max_tokens, temperature, system_prompt,  # 추가
    )
elif provider == AIProvider.ANTHROPIC:
    content = await self._call_anthropic(
        key.api_key, prompt, model or "claude-3-haiku-20240307",
        max_tokens, temperature, system_prompt,  # 추가
    )
elif provider == AIProvider.GOOGLE:
    content = await self._call_google(
        key.api_key, prompt, model or "gemini-2.0-flash",
        max_tokens, temperature, system_prompt,  # 추가
    )
```

**변경 5: `_call_openai()` 수정 (Line 196-214)**

```python
async def _call_openai(
    self, api_key, prompt, model, max_tokens, temperature, system_prompt=None
):
    client = openai.AsyncOpenAI(api_key=api_key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()
```

**변경 6: `_call_anthropic()` 수정 (Line 216-234)**

```python
async def _call_anthropic(
    self, api_key, prompt, model, max_tokens, temperature, system_prompt=None
):
    client = anthropic.AsyncAnthropic(api_key=api_key)
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    resp = await client.messages.create(**kwargs)
    return resp.content[0].text.strip()
```

**변경 7: `_call_google()` 수정 (Line 236-269)**

```python
async def _call_google(
    self, api_key, prompt, model, max_tokens, temperature, system_prompt=None
):
    # system_prompt가 있으면 prompt 앞에 붙임 (Gemini는 별도 system 필드 사용)
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    # ... 이하 기존 로직에서 prompt -> full_prompt로 변경
```

#### 4.3.2 `generator.py` 수정

**변경 1: `_generate_content_with_meta()` 수정 (Line 265-313)**

```python
async def _generate_content_with_meta(
    self, title: str, reference_injection: str, settings: dict, blog: Blog,
) -> dict:
    """AI로 글 생성 (프롬프트 모듈 설정 우선 적용)"""

    # 콘텐츠 생성 설정 (프롬프트 모듈 우선)
    cg = settings.get("content_generation", {})
    ai_config = blog.ai_config or {}
    writing_ai = ai_config.get("writing_ai", {})

    # 프롬프트: 모듈 새 형식 -> 모듈 레거시 키 -> 기본값
    prompt_template = (
        cg.get("user_prompt_template")
        or settings.get("generation_prompt")
        or DEFAULT_CONTENT_PROMPT
    )

    full_prompt = prompt_template.replace(
        "{title}", title
    ).replace(
        "{reference_materials}", reference_injection
    )

    # AI 제공자: 모듈 설정 -> 블로그 설정
    provider = cg.get("provider") or writing_ai.get("provider")
    model = writing_ai.get("model")  # 모델은 블로그 설정에서만

    # 세부 설정: 모듈 설정 -> 기본값
    temperature = cg.get("temperature", 0.7)
    max_tokens = cg.get("max_tokens", 4000)
    system_prompt = cg.get("system_prompt") or None

    # 설정 소스 로깅
    logger.info(
        f"[GENERATOR] AI 설정 소스: provider={provider} "
        f"(source={'module' if cg.get('provider') else 'blog'}), "
        f"temperature={temperature}, max_tokens={max_tokens}, "
        f"has_system_prompt={bool(system_prompt)}"
    )

    # AI 호출
    result = await self.ai_service.generate(
        prompt=full_prompt,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
    )

    if not result:
        raise RuntimeError("AI 글 생성 실패: 모든 제공자 호출 실패")

    return result
```

**변경 2: `_execute_pipeline()` 2단계 - 제목 재조합 AI도 모듈 설정 우선**

```python
# 현재 Line 152-160

# 변경 전
ai_config = blog.ai_config or {}
title_ai = ai_config.get("title_ai", {})
recombine_result = await self.title_recombiner.recombine(
    original_title=source_title.title,
    module_id=prompt_module_id,
    provider=title_ai.get("provider"),
    model=title_ai.get("model"),
)

# 변경 후
cg = settings.get("content_generation", {})
ai_config = blog.ai_config or {}
title_ai = ai_config.get("title_ai", {})
# 프롬프트 모듈 provider 우선 -> 블로그 설정
title_provider = cg.get("provider") or title_ai.get("provider")
recombine_result = await self.title_recombiner.recombine(
    original_title=source_title.title,
    module_id=prompt_module_id,
    provider=title_provider,
    model=title_ai.get("model"),
)
```

### 4.4 테스트 관점

- 모듈 `settings.content_generation.provider="google"`이고 `Blog.ai_config.writing_ai.provider="openai"`인 경우 -> google이 사용되는지 확인
- 모듈 `settings.content_generation`이 비어있으면 `Blog.ai_config`가 사용되는지 확인
- `system_prompt`가 있을 때 AI 호출에 반영되는지 확인
- `temperature`/`max_tokens`가 모듈 설정값으로 적용되는지 확인

---

## 5. Phase C: 이미지 생성 서비스 구현

### 5.1 개요

| 항목 | 내용 |
|------|------|
| **해결하는 GAP** | G3, G7 |
| **새 파일** | `image_generator.py`, `ai_image_service.py`, `template_image_service.py` |
| **수정 파일** | `generator.py`, (필요 시 모델 마이그레이션) |
| **난이도** | 높음 |

### 5.2 아키텍처

```
ImageGenerator (총괄)
  |
  +-- AIImageService (DALL-E, Nanobanana 등)
  |     +-- AIService를 통한 이미지 생성 API 호출
  |
  +-- TemplateImageService (배경 + 텍스트 합성)
        +-- Pillow 라이브러리 사용
```

비유하면 ImageGenerator는 "이미지 담당 매니저"로, 블로그 설정(image_mode)에 따라 "AI 디자이너(AIImageService)"에게 맡길지, "템플릿 디자이너(TemplateImageService)"에게 맡길지 결정합니다.

### 5.3 새 파일: `image_generator.py` (~250줄)

```python
"""
이미지 생성 총괄 서비스

Blog.image_mode에 따라 AI 이미지 또는 템플릿 이미지를 생성합니다.
"""

@dataclass
class ImageResult:
    """이미지 생성 결과"""
    success: bool
    image_url: Optional[str] = None
    image_mode: Optional[str] = None    # "ai" | "template"
    provider: Optional[str] = None
    generation_time_seconds: int = 0
    error: Optional[str] = None

class ImageGenerator:
    """이미지 생성 총괄 서비스"""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.ai_image = AIImageService(db, user_id)
        self.template_image = TemplateImageService()

    async def generate(
        self, blog: Blog, title: str, module_settings: dict
    ) -> ImageResult:
        """
        블로그 설정에 따라 이미지 생성

        동작 흐름:
        1. module_settings.image_generation.enabled 확인
        2. blog.image_mode에 따라 분기:
           - "ai": AI 이미지만 시도
           - "template": 템플릿 이미지만 시도
           - "both": AI 시도 -> 실패 시 템플릿
           - None/"none": 이미지 생성 안 함
        """
        img_settings = module_settings.get("image_generation", {})
        if not img_settings.get("enabled", False):
            return ImageResult(success=True)  # 비활성화 시 건너뜀

        image_mode = getattr(blog, "image_mode", None) or "ai"

        if image_mode == "ai":
            return await self._generate_ai_image(blog, title, img_settings)
        elif image_mode == "template":
            return await self._generate_template_image(blog, title)
        elif image_mode == "both":
            result = await self._generate_ai_image(blog, title, img_settings)
            if not result.success:
                return await self._generate_template_image(blog, title)
            return result
        else:
            return ImageResult(success=True)  # 이미지 불필요
```

### 5.4 새 파일: `ai_image_service.py` (~200줄)

```python
"""
AI 이미지 생성 서비스 (DALL-E, Nanobanana)

프롬프트 모듈의 image_generation 설정을 기반으로
AI API를 호출하여 이미지를 생성합니다.
"""

class AIImageService:
    async def generate(self, title: str, settings: dict) -> Optional[str]:
        """
        1. settings.prompt_template에서 프롬프트 구성 ({title} 치환)
        2. settings.provider에 따라 DALL-E 또는 Nanobanana 호출
        3. 생성된 이미지를 static/generated/images/ 에 저장
        4. 이미지 URL 반환
        """

    async def _call_dalle(self, api_key, prompt, settings):
        """OpenAI DALL-E API 호출"""
        # settings.dalle.size, quality, style 사용

    async def _call_nanobanana(self, api_key, prompt, settings):
        """Nanobanana API 호출 (추후 구현)"""
        pass
```

### 5.5 새 파일: `template_image_service.py` (~250줄)

```python
"""
템플릿 기반 이미지 합성 서비스

배경 이미지 위에 제목 텍스트를 합성하여 블로그 헤더 이미지를 생성합니다.
Blog.overlay_config 설정을 사용합니다.
"""
from PIL import Image, ImageDraw, ImageFont

class TemplateImageService:
    async def generate(self, title: str, blog: Blog) -> Optional[str]:
        """
        1. Blog.overlay_config에서 배경 이미지, 글꼴, 위치 설정 로드
        2. Pillow로 배경 위에 텍스트 합성
        3. static/generated/images/ 에 저장
        4. 이미지 URL 반환
        """

    def _compose_image(self, background_path, title, config):
        """이미지 합성 실행"""
        # 배경 로드 -> 텍스트 위치/크기 계산 -> 텍스트 그리기 -> 저장
```

### 5.6 `generator.py` 파이프라인 수정

현재 파이프라인 순서에서 "치환 처리"와 "GenerationHistory 저장" 사이에 이미지 생성 단계를 삽입합니다.

```
현재: ... -> 6. 치환 처리 -> 7. GenerationHistory 저장
변경: ... -> 6. 치환 처리 -> 6.5 이미지 생성 -> 7. GenerationHistory 저장
```

```python
# 현재 순서: 치환(Line 200-206) -> GenerationHistory 저장(Line 209-222)
# 변경 후: 치환 -> 이미지 생성 -> GenerationHistory 저장

# 6.5 이미지 생성 (실패해도 글 생성은 계속)
image_url = None
try:
    image_generator = ImageGenerator(self.db, self.user_id)
    img_result = await image_generator.generate(
        blog=blog, title=working_title, module_settings=settings
    )
    if img_result.success and img_result.image_url:
        image_url = img_result.image_url
        logger.info(f"[GENERATOR] 이미지 생성 완료 | mode={img_result.image_mode}")
except Exception as e:
    logger.warning(f"[GENERATOR] 이미지 생성 실패 (글 생성은 계속): {e}")

# 7. GenerationHistory 저장 시 image_url 추가
history = GenerationHistory(
    blog_id=blog_id,
    # ... 기존 필드들 ...
    image_url=image_url,  # 추가
)
```

### 5.7 필요한 추가 작업

| 작업 | 설명 |
|------|------|
| `requirements.txt`에 `Pillow` 추가 | 템플릿 이미지 합성용 |
| `GenerationHistory` 모델에 `image_url` 컬럼 추가 | Alembic 마이그레이션 필요 |
| `CrawledPost` 모델에 `image_url` 컬럼 확인/추가 | 이미지 URL 저장용 |
| `static/generated/images/` 디렉토리 구조 생성 | 이미지 파일 저장 경로 |

### 5.8 테스트 관점

- `image_generation.enabled=False`면 이미지 생성이 건너뛰어지는지 확인
- `blog.image_mode="ai"`일 때 DALL-E가 호출되는지 확인
- `blog.image_mode="template"`일 때 Pillow 합성이 실행되는지 확인
- 이미지 생성 실패 시 글 생성이 정상 완료되는지 확인 (핵심 테스트)

---

## 6. Phase D: 단계별 테스트 기능 구현

### 6.1 개요

| 항목 | 내용 |
|------|------|
| **해결하는 GAP** | G4 |
| **새 파일** | `generation_test.py` (라우터), `pipeline_tester.py` (서비스) |
| **난이도** | 중간 |

### 6.2 API 엔드포인트 목록

| Step | 엔드포인트 | 설명 |
|------|-----------|------|
| 1 | `POST /api/v1/generation/test/select-title` | 제목 선택 테스트 |
| 2 | `POST /api/v1/generation/test/recombine-title` | 제목 재조합 테스트 |
| 3 | `POST /api/v1/generation/test/collect-references` | 참조자료 수집 테스트 |
| 4 | `POST /api/v1/generation/test/generate-content` | 글 생성 테스트 |
| 5 | `POST /api/v1/generation/test/generate-image` | 이미지 생성 테스트 |
| 6 | `POST /api/v1/generation/test/full-pipeline` | 전체 파이프라인 테스트 |

각 Step은 독립적으로 실행할 수 있으며, 이전 Step의 결과를 다음 Step의 입력으로 활용할 수 있습니다. 비유하면 "자동차 조립 라인의 각 공정을 개별 점검하는 것"과 같습니다.

### 6.3 각 Step별 요청/응답 상세

#### Step 1: 제목 선택 테스트

```python
# 요청
class SelectTitleRequest(BaseModel):
    blog_id: int
    module_id: int
```

```json
// 응답
{
    "step": "select_title",
    "success": true,
    "result": {
        "selected_title": {
            "id": 42,
            "title": "...",
            "topic": "...",
            "subtopic": "..."
        },
        "total_candidates": 8,
        "candidates": [{"id": 1, "title": "..."}, {"id": 2, "title": "..."}],
        "filter_info": {
            "source": "module_settings",
            "categories": [{"topic_id": 1, "subtopic_id": 3}],
            "selection_method": "random"
        }
    }
}
```

#### Step 2: 제목 재조합 테스트

```python
# 요청
class RecombineTitleRequest(BaseModel):
    module_id: int
    title_id: Optional[int] = None      # DB에서 제목 로드
    title_text: Optional[str] = None     # 직접 텍스트 입력
```

```json
// 응답
{
    "step": "recombine_title",
    "success": true,
    "result": {
        "original_title": "원본 제목",
        "recombined_title": "재조합된 제목",
        "is_modified": true,
        "ai_provider": "openai",
        "ai_model": "gpt-4o-mini",
        "settings_used": {
            "enabled": true,
            "styles": ["emotional"],
            "custom_prompt": null
        }
    }
}
```

#### Step 3: 참조자료 수집 테스트

```python
# 요청
class CollectReferencesRequest(BaseModel):
    module_id: int
    search_query: str
```

```json
// 응답
{
    "step": "collect_references",
    "success": true,
    "result": {
        "search_query": "검색어",
        "total_searched": 30,
        "total_crawled": 8,
        "summaries": [
            {"source_url": "https://...", "summary": "...", "length": 350}
        ],
        "summary_method": "ai",
        "reference_injection": "참조자료 프롬프트 텍스트 (Step 4에서 사용)",
        "settings_used": {
            "max_search": 30,
            "crawl_target": 10,
            "summary_count": 3
        }
    }
}
```

#### Step 4: 글 생성 테스트

```python
# 요청
class GenerateContentRequest(BaseModel):
    module_id: int
    blog_id: int
    title: str
    reference_text: Optional[str] = None  # 없으면 참조자료 없이 생성
```

```json
// 응답
{
    "step": "generate_content",
    "success": true,
    "result": {
        "content_markdown": "마크다운 형태 글",
        "content_html": "HTML 형태 글 (치환 적용)",
        "content_length": 2847,
        "ai_provider": "gemini",
        "ai_model": "gemini-2.0-flash",
        "generation_time_seconds": 12,
        "settings_used": {
            "provider_source": "module_settings",
            "temperature": 0.7,
            "max_tokens": 4096,
            "has_system_prompt": true,
            "prompt_source": "content_generation.user_prompt_template"
        }
    }
}
```

#### Step 5: 이미지 생성 테스트

```python
# 요청
class GenerateImageRequest(BaseModel):
    module_id: int
    blog_id: int
    title: str
```

```json
// 응답
{
    "step": "generate_image",
    "success": true,
    "result": {
        "image_url": "/static/generated/images/...",
        "image_mode": "ai",
        "ai_provider": "dalle",
        "prompt_used": "사용된 이미지 프롬프트",
        "generation_time_seconds": 8
    }
}
```

#### Step 6: 전체 파이프라인 테스트

```python
# 요청
class FullPipelineRequest(BaseModel):
    blog_id: int
    module_id: int
    dry_run: bool = True  # True면 DB에 저장하지 않음
```

```json
// 응답
{
    "step": "full_pipeline",
    "success": true,
    "dry_run": true,
    "steps": {
        "1_select_title": {"success": true, "title_id": 42, "title": "..."},
        "2_recombine_title": {"success": true, "title": "...", "is_modified": true},
        "3_collect_references": {"success": true, "count": 3},
        "4_generate_content": {"success": true, "length": 2847, "provider": "gemini"},
        "5_generate_image": {"success": true, "url": "...", "mode": "ai"}
    },
    "total_time_seconds": 35,
    "saved": false
}
```

### 6.4 서비스 구현: `pipeline_tester.py` (~350줄)

```python
"""
파이프라인 단계별 테스트 서비스

각 생성 단계를 독립적으로 실행하여 결과를 확인할 수 있는 서비스.
실제 DB에 영향을 주지 않는 테스트 모드를 지원합니다.
"""
import random
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.module import Module
from ...models.blog import Blog
from ...models.title import MainTitle
from .inventory_trigger import InventoryTrigger
from .title_recombiner import TitleRecombiner
from .reference_collector import ReferenceCollector
from .internal_linker import InternalLinker
from .substitution_processor import SubstitutionProcessor
from ..ai.ai_service import AIService
# Phase C 완료 후: from .image_generator import ImageGenerator


class PipelineTester:
    """파이프라인 단계별 테스트 서비스"""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.inventory_trigger = InventoryTrigger(db)
        self.title_recombiner = TitleRecombiner(db, user_id)
        self.reference_collector = ReferenceCollector(db, user_id)
        self.ai_service = AIService(db, user_id)
        self.internal_linker = InternalLinker(db)
        self.substitution_processor = SubstitutionProcessor(db)

    async def test_select_title(self, blog_id: int, module_id: int) -> dict:
        """Step 1: 제목 선택 테스트 (DB 변경 없음)"""
        module = await self.db.get(Module, module_id)
        if not module:
            return {
                "step": "select_title",
                "success": False,
                "error": "모듈을 찾을 수 없습니다",
            }

        settings = module.settings or {}

        # 후보 목록 조회
        candidates = await self.inventory_trigger.find_available_titles(
            blog_id, limit=10
            # Phase A 완료 후: module_settings=settings 추가
        )

        if not candidates:
            return {
                "step": "select_title",
                "success": False,
                "error": "사용 가능한 제목이 없습니다",
            }

        selected = random.choice(candidates)

        # 카테고리 소스 정보
        has_module_cats = bool(settings.get("categories"))

        return {
            "step": "select_title",
            "success": True,
            "result": {
                "selected_title": {
                    "id": selected.id,
                    "title": selected.title,
                },
                "total_candidates": len(candidates),
                "candidates": [
                    {"id": t.id, "title": t.title} for t in candidates
                ],
                "filter_info": {
                    "source": "module_settings" if has_module_cats else "blog_category",
                    "categories": settings.get("categories", []),
                    "selection_method": "random",
                },
            },
        }

    async def test_recombine_title(
        self,
        module_id: int,
        title_id: Optional[int] = None,
        title_text: Optional[str] = None,
    ) -> dict:
        """Step 2: 제목 재조합 테스트 (DB 변경 없음)"""
        # title_id가 있으면 DB에서 로드, 없으면 title_text 사용
        if title_id:
            title_obj = await self.db.get(MainTitle, title_id)
            original = title_obj.title if title_obj else title_text
        else:
            original = title_text

        if not original:
            return {
                "step": "recombine_title",
                "success": False,
                "error": "제목을 지정해주세요",
            }

        module = await self.db.get(Module, module_id)
        settings = module.settings or {} if module else {}
        cg = settings.get("content_generation", {})

        result = await self.title_recombiner.recombine(
            original_title=original,
            module_id=module_id,
            provider=cg.get("provider"),
        )

        tr_settings = settings.get("title_recombine", {})

        return {
            "step": "recombine_title",
            "success": True,
            "result": {
                "original_title": result.original_title,
                "recombined_title": result.recombined_title,
                "is_modified": result.is_modified,
                "ai_provider": result.ai_provider,
                "ai_model": result.ai_model,
                "settings_used": {
                    "enabled": tr_settings.get("enabled", False),
                    "styles": tr_settings.get("styles", []),
                    "custom_prompt": tr_settings.get("custom_prompt"),
                },
            },
        }

    # test_collect_references, test_generate_content, test_generate_image,
    # test_full_pipeline도 동일 패턴으로 구현
```

### 6.5 라우터 구현: `generation_test.py` (~300줄)

```python
"""
생성 파이프라인 테스트 API

각 단계를 독립적으로 테스트할 수 있는 엔드포인트를 제공합니다.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from ..core.database import get_db_session
from ..routers.auth import get_current_user
from ..services.generation.pipeline_tester import PipelineTester

router = APIRouter(
    prefix="/api/v1/generation/test",
    tags=["generation-test"],
)


class SelectTitleRequest(BaseModel):
    blog_id: int
    module_id: int


@router.post("/select-title")
async def test_select_title(
    request: SelectTitleRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    tester = PipelineTester(db, current_user.id)
    return await tester.test_select_title(request.blog_id, request.module_id)

# ... 나머지 Step 2~6도 동일 패턴
```

### 6.6 라우터 등록

```python
# app/main.py 또는 라우터 등록 파일에서
from .routers.generation_test import router as generation_test_router
app.include_router(generation_test_router)
```

---

## 7. 구현 순서 및 의존관계

```
Phase A (카테고리 + 랜덤)   <- 가장 먼저 (다른 Phase의 기반)
  |
  v
Phase B (설정값 정규화)      <- A 완료 후 (AI 설정 체계 정리)
  |
  v
Phase C (이미지 생성)        <- B 완료 후 (AI 설정 체계 활용)
  |
  v
Phase D (테스트 API)         <- A~C 완료 후 (모든 단계 테스트 가능)
```

### 7.1 각 Phase 예상 작업량

| Phase | 수정 파일 | 새 파일 | 예상 변경 줄 수 | 핵심 효과 |
|-------|----------|--------|----------------|----------|
| A | 2개 | 0개 | ~80줄 | 카테고리 필터 + 랜덤 제목 선택 |
| B | 2개 | 0개 | ~120줄 | 프롬프트 모듈 AI 설정 우선 적용 |
| C | 1개 수정 + 마이그레이션 | 3개 | ~700줄 | 이미지 자동 생성 |
| D | 라우터 등록 | 2개 | ~650줄 | 단계별 테스트 가능 |

### 7.2 체크리스트

각 Phase 완료 시 확인 사항:

**Phase A 완료 후:**

- [ ] 프롬프트 모듈의 categories 설정이 제목 필터에 사용되는가?
- [ ] categories가 비어있으면 BlogCategory 폴백이 작동하는가?
- [ ] 동일 조건 여러 번 실행 시 다른 제목이 선택되는가?

**Phase B 완료 후:**

- [ ] 모듈의 content_generation.provider가 Blog.ai_config보다 우선 적용되는가?
- [ ] system_prompt가 AI 호출에 반영되는가?
- [ ] 모듈 설정이 없을 때 기존 동작과 호환되는가?

**Phase C 완료 후:**

- [ ] image_generation.enabled=true일 때 이미지가 생성되는가?
- [ ] image_mode별 분기가 올바른가 (ai/template/both)?
- [ ] 이미지 생성 실패 시 글 생성은 정상 완료되는가?
- [ ] 생성된 이미지가 올바른 경로에 저장되는가?

**Phase D 완료 후:**

- [ ] 각 Step API가 독립적으로 동작하는가?
- [ ] dry_run=true일 때 DB에 변경사항이 없는가?
- [ ] 이전 Step 결과를 다음 Step에 입력으로 사용할 수 있는가?

---

## 8. 주의사항

### 8.1 하위 호환성

- 기존 `settings.generation_prompt` (레거시 키)를 사용하는 모듈이 있을 수 있으므로, Phase B에서 이 키도 2순위로 계속 지원해야 합니다.
- `Module.settings`에 categories가 없는 기존 모듈은 Phase A에서 BlogCategory 폴백으로 기존 동작을 유지해야 합니다.

### 8.2 파일 크기 제한

- 모든 파일은 **500줄 이하** (CLAUDE.md 규칙)
- 모든 함수는 **50줄 이하**
- 필요 시 헬퍼 함수로 분리

### 8.3 에러 처리

- 이미지 생성 실패가 전체 파이프라인을 중단시키면 안 됨 (`try/except`)
- 테스트 API는 DB를 변경하지 않아야 함 (Step 6의 `dry_run=false` 제외)
- AI API 호출 실패 시 명확한 에러 메시지 반환

### 8.4 로깅

각 Phase에서 추가하는 로직에 적절한 로그를 추가하세요. 특히 **"어떤 설정 소스가 사용되었는지"** 로깅은 필수입니다.

```python
# 예시: 설정 소스 로깅
logger.info(
    f"[GENERATOR] AI 설정 소스: provider={provider} "
    f"(source={'module' if cg.get('provider') else 'blog'})"
)
```

```python
# 예시: 카테고리 소스 로깅
logger.debug(
    f"[INVENTORY] 카테고리 소스: {category_source} | "
    f"subtopic_ids={subtopic_ids}, topic_only_ids={topic_only_ids}"
)
```

이 로그들은 문제 발생 시 "어디서 잘못된 설정이 적용되었는지"를 빠르게 파악하는 데 도움을 줍니다.
