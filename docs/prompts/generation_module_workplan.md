# 생성 모듈 구현 작업계획서

> **문서 버전**: v1.0  
> **작성일**: 2025-02-06  
> **작성**: 네오 (Claude Chat)  
> **기반 문서**: Generation module design v1.1.md  
> **목표**: 생성 모듈 완성 및 프롬프트 모듈 연동

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 아키텍처](#2-전체-아키텍처)
3. [Phase 1: 기반 인프라 구축](#phase-1-기반-인프라-구축)
4. [Phase 2: 핵심 서비스 구현](#phase-2-핵심-서비스-구현)
5. [Phase 3: 생성 모듈 메인 로직](#phase-3-생성-모듈-메인-로직)
6. [Phase 4: 프롬프트 모듈 연동](#phase-4-프롬프트-모듈-연동)
7. [Phase 5: 통합 테스트 및 디버깅](#phase-5-통합-테스트-및-디버깅)
8. [Phase 6: 발행 모듈 연계 준비](#phase-6-발행-모듈-연계-준비)
9. [파일 구조](#파일-구조)
10. [체크리스트](#체크리스트)

---

## 1. 프로젝트 개요

### 1.1 목표

**생성 모듈**을 완성하여 다음 워크플로우가 자동으로 동작하도록 함:

```
정식 제목 선택 → 제목 재조합 → 참조자료 수집 → 글 생성 → 이미지 생성 
→ 내부링크 삽입 → 치환 처리 → 크롤링 포스트 저장
```

### 1.2 핵심 연동 포인트

| 연동 대상 | 연동 내용 | 중요도 |
|----------|----------|--------|
| **프롬프트 모듈** | 글 생성 프롬프트, 제목 재조합 프롬프트 로드 | 🔴 Critical |
| **참조자료 수집** | 재조합된 제목으로 검색 → 수집 → 프롬프트에 주입 | 🔴 Critical |
| **블로그 설정** | AI 키, 치환자 설정, 내부링크 설정 로드 | 🟡 High |
| **정식 제목** | 미사용 독립포스트 선택 | 🟡 High |
| **크롤링 포스트** | 생성된 글 저장, 재고 관리 | 🟡 High |

### 1.3 예상 일정

| Phase | 내용 | 예상 소요 |
|-------|------|----------|
| Phase 1 | 기반 인프라 (Celery, Redis, 모델) | 2~3일 |
| Phase 2 | 핵심 서비스 (제목 재조합, 참조자료, AI 호출) | 3~4일 |
| Phase 3 | 생성 모듈 메인 로직 | 2~3일 |
| Phase 4 | 프롬프트 모듈 연동 | 2~3일 |
| Phase 5 | 통합 테스트 및 디버깅 | 3~5일 |
| Phase 6 | 발행 모듈 연계 준비 | 1~2일 |
| **총합** | | **13~20일** |

---

## 2. 전체 아키텍처

### 2.1 생성 워크플로우 상세

```
┌─────────────────────────────────────────────────────────────────────┐
│                         생성 모듈 워크플로우                          │
└─────────────────────────────────────────────────────────────────────┘

[트리거: 발행 후 재고 체크]
         │
         ▼
┌─────────────────┐
│ 1. 조건 점검     │
│  - 프롬프트 모듈 │◄─────── 프롬프트 모듈 존재 확인
│  - 블로그 연결   │
│  - 정식 제목    │◄─────── 미사용 독립포스트 존재 확인
│  - 재고 < 기준  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 제목 재조합   │
│  (AI 호출)      │◄─────── 프롬프트 모듈의 "제목 재조합 프롬프트" 사용
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 참조자료 수집 │
│  - 웹 검색      │◄─────── 재조합된 제목으로 검색
│  - 크롤링       │
│  - 요약 (AI)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 글 생성      │
│  (AI 호출)      │◄─────── 프롬프트 모듈의 "글 생성 프롬프트"
│                 │◄─────── + 참조자료 주입
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. 이미지 생성   │
│  (AI 호출)      │◄─────── 블로그 설정의 "이미지 생성 AI"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. 후처리       │
│  - 내부링크 삽입 │
│  - 텍스트 치환  │◄─────── 블로그 설정의 "치환자"
│  - HTML 변환    │
│  - HTML 치환    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. 저장         │
│  - 크롤링포스트 │◄─────── 메타데이터 포함 저장
│  - 재고 +1      │
└─────────────────┘
```

### 2.2 Celery 큐 구조

```
                      ┌──────────────┐
                      │ Redis Broker │
                      └──────┬───────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ title_queue  │    │ content_queue│    │ image_queue  │
│ (제목 재조합) │    │ (글 생성)    │    │ (이미지 생성)│
│ 워커 1~2개   │    │ 워커 3~5개   │    │ 워커 2개     │
└──────────────┘    └──────────────┘    └──────────────┘

※ 참조자료 수집은 content_queue에서 글 생성 전에 동기 실행
  (별도 큐 분리는 Phase 5 이후 필요시 검토)
```

---

## Phase 1: 기반 인프라 구축

### 1.1 목표

- Celery + Redis 설정
- 생성 관련 DB 모델 추가
- 메타데이터 스키마 정의

### 1.2 작업 항목

#### 1.2.1 Celery 설정

**파일**: `app/core/celery_config.py`

```python
# 주요 내용
- Celery 앱 인스턴스 생성
- Redis broker 연결
- 큐 정의 (title_queue, content_queue, image_queue)
- task_routes 설정
- 오토스케일 설정
```

**파일**: `app/core/celery_tasks.py`

```python
# 주요 내용
- @celery_app.task 데코레이터 기반 태스크 정의
- 제목 재조합 태스크
- 글 생성 태스크
- 이미지 생성 태스크
- 생성 완료 후 콜백 태스크
```

#### 1.2.2 DB 모델 추가/수정

**파일**: `app/models/generation_history.py` (신규)

```python
class GenerationHistory(Base):
    """생성 이력 메타데이터"""
    id: int
    blog_id: int                    # 블로그 FK
    source_title_id: int            # 원본 정식 제목 FK
    prompt_module_id: int           # 사용된 프롬프트 모듈 FK
    recombined_title: str           # 재조합된 제목
    ai_model_title: str             # 제목 재조합에 사용된 AI 모델
    ai_model_content: str           # 글 생성에 사용된 AI 모델
    ai_model_image: str             # 이미지 생성에 사용된 AI 모델
    reference_count: int            # 수집된 참조자료 수
    generation_time_seconds: int    # 총 생성 소요 시간
    content_length: int             # 생성된 글 길이
    crawling_post_id: int           # 저장된 크롤링 포스트 FK
    version: int                    # 같은 제목의 몇 번째 버전
    created_at: datetime
```

**파일**: `app/models/blog_growth_setting.py` (신규)

```python
class BlogGrowthSetting(Base):
    """블로그 성장 단계별 설정"""
    id: int
    blog_id: int                    # 블로그 FK
    
    # 급성장기 설정
    rapid_growth_threshold: int     # 이 수치 이하일 때 급성장기 (기본 50)
    rapid_growth_inventory: int     # 재고 기준값 (기본 10)
    
    # 성장기 설정
    growth_threshold: int           # 이 수치 이하일 때 성장기 (기본 150)
    growth_inventory: int           # 재고 기준값 (기본 5)
    
    # 안정기 설정
    stable_inventory: int           # 재고 기준값 (기본 2)
    
    created_at: datetime
    updated_at: datetime
```

**수정 필요**: `app/models/crawling_post.py`

```python
# 추가 필드
generation_history_id: int          # 생성 이력 FK (nullable, 수동 추가 글은 null)
```

#### 1.2.3 Docker Compose 수정

**파일**: `docker-compose.yml`

```yaml
# 추가 서비스
services:
  # 기존 app, db 외에 추가
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
  
  celery_title_worker:
    build: .
    command: celery -A app.core.celery_config worker -Q title_queue --concurrency=2
    depends_on:
      - redis
      - db
  
  celery_content_worker:
    build: .
    command: celery -A app.core.celery_config worker -Q content_queue --autoscale=5,3
    depends_on:
      - redis
      - db
  
  celery_image_worker:
    build: .
    command: celery -A app.core.celery_config worker -Q image_queue --concurrency=2
    depends_on:
      - redis
      - db

volumes:
  redis_data:
```

### 1.3 체크포인트

- [ ] Celery + Redis 연결 테스트 (간단한 태스크 실행)
- [ ] 새 모델 마이그레이션 완료
- [ ] Docker Compose로 전체 스택 실행 확인

---

## Phase 2: 핵심 서비스 구현

### 2.1 목표

- 제목 재조합 서비스
- 참조자료 수집 서비스
- AI 호출 공통 서비스

### 2.2 작업 항목

#### 2.2.1 제목 재조합 서비스

**파일**: `app/services/generation/title_recombiner.py`

```python
class TitleRecombiner:
    """
    정식 제목을 AI로 재조합하는 서비스
    
    연동:
    - 프롬프트 모듈의 "제목 재조합 프롬프트" 사용
    - 블로그 설정의 "제목 재조합 AI" 사용
    """
    
    async def recombine(
        self,
        original_title: str,
        prompt_module_id: int,
        blog_id: int
    ) -> str:
        """
        1. 프롬프트 모듈에서 제목 재조합 프롬프트 로드
        2. 블로그 설정에서 AI 키 로드
        3. AI 호출
        4. 재조합된 제목 반환
        """
        pass
```

**핵심 로직:**

```python
# 1. 프롬프트 모듈 로드
prompt_module = await self._get_prompt_module(prompt_module_id)
recombine_prompt = prompt_module.title_recombine_prompt

# 2. 블로그 AI 설정 로드
ai_settings = await self._get_blog_ai_settings(blog_id)
ai_model = ai_settings.title_recombine_model
api_key = ai_settings.api_key

# 3. 프롬프트 조합
full_prompt = recombine_prompt.format(original_title=original_title)

# 4. AI 호출
recombined = await self.ai_service.generate(
    prompt=full_prompt,
    model=ai_model,
    api_key=api_key
)

return recombined
```

#### 2.2.2 참조자료 수집 서비스

**파일**: `app/services/generation/reference_collector.py`

```python
class ReferenceCollector:
    """
    재조합된 제목으로 참조자료를 수집하고 요약하는 서비스
    
    주의: 프롬프트 모듈의 글 생성 시 이 참조자료가 주입됨
    """
    
    async def collect_and_summarize(
        self,
        recombined_title: str,
        blog_id: int,
        max_references: int = 10
    ) -> ReferenceResult:
        """
        1. 재조합된 제목으로 웹 검색
        2. 상위 결과 크롤링
        3. AI로 요약
        4. 프롬프트에 주입할 형태로 반환
        """
        pass
```

**핵심 로직:**

```python
# 1. 웹 검색 (Google, Naver 등)
search_results = await self.searcher.search(recombined_title, limit=max_references)

# 2. 크롤링
crawled_contents = []
for result in search_results:
    content = await self.crawler.fetch(result.url)
    if content:
        crawled_contents.append({
            'url': result.url,
            'title': result.title,
            'content': content[:5000]  # 길이 제한
        })

# 3. AI로 요약
summary = await self.ai_service.summarize(
    contents=crawled_contents,
    model=ai_settings.content_model,  # 글 생성 모델 사용
    api_key=ai_settings.api_key
)

# 4. 프롬프트 주입용 형태로 반환
return ReferenceResult(
    count=len(crawled_contents),
    summary=summary,
    sources=[c['url'] for c in crawled_contents]
)
```

**반환 형태 (프롬프트 주입용):**

```python
@dataclass
class ReferenceResult:
    count: int
    summary: str           # 프롬프트에 직접 주입될 요약 텍스트
    sources: list[str]     # 출처 URL 목록
    
    def to_prompt_injection(self) -> str:
        """프롬프트에 주입할 형태로 변환"""
        return f"""
[참조자료 요약]
{self.summary}

[출처]
{chr(10).join(f'- {url}' for url in self.sources)}
"""
```

#### 2.2.3 AI 호출 공통 서비스

**파일**: `app/services/ai/ai_service.py`

```python
class AIService:
    """
    OpenAI, Claude, Gemini 등 다양한 AI API를 통합 호출하는 서비스
    """
    
    async def generate(
        self,
        prompt: str,
        model: str,
        api_key: str,
        max_tokens: int = 4000
    ) -> str:
        """텍스트 생성 (제목 재조합, 글 생성)"""
        pass
    
    async def summarize(
        self,
        contents: list[dict],
        model: str,
        api_key: str
    ) -> str:
        """참조자료 요약"""
        pass
    
    async def generate_image(
        self,
        prompt: str,
        model: str,
        api_key: str
    ) -> bytes:
        """이미지 생성"""
        pass
```

### 2.3 체크포인트

- [ ] 제목 재조합 단독 테스트 (프롬프트 모듈 연동)
- [ ] 참조자료 수집 단독 테스트
- [ ] AI 호출 공통 서비스 테스트 (OpenAI/Claude/Gemini)

---

## Phase 3: 생성 모듈 메인 로직

### 3.1 목표

- 생성 모듈 전체 파이프라인 구현
- 내부링크 삽입 로직
- 치환 처리 로직

### 3.2 작업 항목

#### 3.2.1 생성 모듈 메인 서비스

**파일**: `app/services/generation/generator.py`

```python
class ContentGenerator:
    """
    생성 모듈 메인 서비스
    전체 생성 파이프라인을 오케스트레이션
    """
    
    def __init__(
        self,
        title_recombiner: TitleRecombiner,
        reference_collector: ReferenceCollector,
        ai_service: AIService,
        internal_linker: InternalLinker,
        substitution_processor: SubstitutionProcessor
    ):
        self.title_recombiner = title_recombiner
        self.reference_collector = reference_collector
        self.ai_service = ai_service
        self.internal_linker = internal_linker
        self.substitution_processor = substitution_processor
    
    async def generate(
        self,
        blog_id: int,
        prompt_module_id: int,
        source_title_id: int
    ) -> GenerationResult:
        """
        전체 생성 파이프라인 실행
        """
        start_time = time.time()
        
        # 1. 원본 제목 로드
        source_title = await self._get_source_title(source_title_id)
        
        # 2. 제목 재조합
        recombined_title = await self.title_recombiner.recombine(
            original_title=source_title.title,
            prompt_module_id=prompt_module_id,
            blog_id=blog_id
        )
        
        # 3. 참조자료 수집 (★ 핵심: 재조합된 제목 사용)
        references = await self.reference_collector.collect_and_summarize(
            recombined_title=recombined_title,
            blog_id=blog_id
        )
        
        # 4. 글 생성 (★ 핵심: 참조자료를 프롬프트에 주입)
        content_markdown = await self._generate_content(
            recombined_title=recombined_title,
            references=references,
            prompt_module_id=prompt_module_id,
            blog_id=blog_id
        )
        
        # 5. 이미지 생성
        images = await self._generate_images(
            recombined_title=recombined_title,
            content=content_markdown,
            blog_id=blog_id
        )
        
        # 6. 내부링크 삽입
        content_with_links = await self.internal_linker.insert_links(
            content=content_markdown,
            blog_id=blog_id,
            current_title=recombined_title
        )
        
        # 7. 치환 처리 (텍스트 → HTML → CSS)
        final_html = await self.substitution_processor.process(
            content=content_with_links,
            blog_id=blog_id
        )
        
        # 8. 저장
        crawling_post = await self._save_to_crawling_post(
            blog_id=blog_id,
            title=recombined_title,
            content=final_html,
            images=images
        )
        
        # 9. 메타데이터 저장
        generation_history = await self._save_generation_history(
            blog_id=blog_id,
            source_title_id=source_title_id,
            prompt_module_id=prompt_module_id,
            recombined_title=recombined_title,
            references=references,
            crawling_post_id=crawling_post.id,
            generation_time=time.time() - start_time
        )
        
        # 10. 원본 제목 사용 처리
        await self._mark_title_as_used(source_title_id)
        
        return GenerationResult(
            success=True,
            crawling_post_id=crawling_post.id,
            generation_history_id=generation_history.id
        )
```

#### 3.2.2 글 생성 (참조자료 주입) - 핵심 연동 부분

```python
async def _generate_content(
    self,
    recombined_title: str,
    references: ReferenceResult,
    prompt_module_id: int,
    blog_id: int
) -> str:
    """
    ★ 핵심: 프롬프트 모듈의 글 생성 프롬프트에 참조자료를 주입하여 글 생성
    """
    # 1. 프롬프트 모듈 로드
    prompt_module = await self._get_prompt_module(prompt_module_id)
    content_prompt_template = prompt_module.content_generation_prompt
    
    # 2. 블로그 AI 설정 로드
    ai_settings = await self._get_blog_ai_settings(blog_id)
    
    # 3. 프롬프트 조합 (★ 참조자료 주입)
    full_prompt = content_prompt_template.format(
        title=recombined_title,
        reference_materials=references.to_prompt_injection()  # 참조자료 주입
    )
    
    # 4. AI 호출
    content = await self.ai_service.generate(
        prompt=full_prompt,
        model=ai_settings.content_model,
        api_key=ai_settings.api_key
    )
    
    return content
```

#### 3.2.3 내부링크 삽입 서비스

**파일**: `app/services/generation/internal_linker.py`

```python
class InternalLinker:
    """
    생성된 글에 내부링크를 삽입하는 서비스
    
    위치별 규칙:
    - 서론 뒤: 유사 제목 글 (버튼, 최대 5개)
    - 본문 섹션 뒤: 유사 제목 글 (일반 링크, 섹션당 1개)
    - 결론 뒤: 랜덤 글 (일반 링크, 설정 수)
    """
    
    async def insert_links(
        self,
        content: str,
        blog_id: int,
        current_title: str
    ) -> str:
        """
        마크다운 상태의 글에 내부링크 삽입
        """
        # 블로그 설정 로드 (내부링크 ON/OFF, 카테고리 우선순위)
        settings = await self._get_link_settings(blog_id)
        if not settings.internal_link_enabled:
            return content
        
        # 유사 제목 글 검색
        similar_posts = await self._find_similar_posts(
            blog_id=blog_id,
            title=current_title,
            category_priority=settings.category_priority
        )
        
        # 랜덤 글 검색
        random_posts = await self._find_random_posts(
            blog_id=blog_id,
            exclude_ids=[p.id for p in similar_posts],
            count=settings.conclusion_link_count
        )
        
        # 사용된 링크 추적 (중복 방지)
        used_links = set()
        
        # 1. 서론 뒤 링크 삽입
        content = self._insert_intro_links(
            content, similar_posts[:5], used_links
        )
        
        # 2. 본문 섹션 링크 삽입
        content = self._insert_section_links(
            content, similar_posts, used_links
        )
        
        # 3. 결론 뒤 링크 삽입
        content = self._insert_conclusion_links(
            content, random_posts, used_links
        )
        
        return content
```

#### 3.2.4 치환 처리 서비스

**파일**: `app/services/generation/substitution_processor.py`

```python
class SubstitutionProcessor:
    """
    치환 처리 서비스
    
    순서:
    1. 텍스트 치환 (마크다운 상태)
    2. HTML 변환
    3. HTML/CSS 치환
    """
    
    async def process(
        self,
        content: str,
        blog_id: int
    ) -> str:
        # 블로그 치환자 설정 로드
        substitutions = await self._get_substitutions(blog_id)
        
        # 1. 텍스트 치환 (마크다운 상태에서)
        content = self._apply_text_substitutions(
            content, 
            substitutions.text_substitutions
        )
        
        # 2. HTML 변환
        html_content = self._convert_to_html(content)
        
        # 3. HTML/CSS 치환
        final_html = self._apply_html_substitutions(
            html_content,
            substitutions.html_substitutions
        )
        
        return final_html
```

### 3.3 체크포인트

- [ ] 전체 생성 파이프라인 단독 실행 테스트
- [ ] 참조자료가 프롬프트에 정상 주입되는지 확인
- [ ] 내부링크 삽입 결과 확인
- [ ] 치환 처리 결과 확인
- [ ] 크롤링 포스트 저장 확인
- [ ] 메타데이터 저장 확인

---

## Phase 4: 프롬프트 모듈 연동

### 4.1 목표

- 프롬프트 모듈과의 완전한 연동
- 플로우 실행 시 생성 모듈 트리거
- 재고 기반 자동 생성

### 4.2 작업 항목

#### 4.2.1 프롬프트 모듈 연동 확인 및 수정

**확인 필요한 프롬프트 모듈 필드:**

```python
# app/models/prompt_module.py (기존 파일)

class PromptModule(Base):
    id: int
    name: str
    blog_id: int                     # ★ 연결된 블로그
    
    # 제목 재조합 관련
    title_recombine_prompt: str      # ★ 제목 재조합 프롬프트
    
    # 글 생성 관련
    content_generation_prompt: str   # ★ 글 생성 프롬프트 (참조자료 주입 위치 포함)
    
    # 기타
    category_id: int                 # 연결된 카테고리
    ...
```

**프롬프트 템플릿 예시 (content_generation_prompt):**

```text
당신은 전문 블로그 작가입니다.

[제목]
{title}

[참조자료]
{reference_materials}

위 참조자료를 바탕으로 SEO에 최적화된 블로그 글을 작성해주세요.

[작성 규칙]
- 마크다운 형식으로 작성
- 서론, 본문 (3~5개 섹션), 결론 구조
- 각 섹션에 소제목 (##) 사용
...
```

#### 4.2.2 플로우-생성 모듈 연동

**파일**: `app/services/flow/flow_executor.py` (수정)

```python
class FlowExecutor:
    """플로우 실행 시 생성 모듈 트리거 추가"""
    
    async def execute_generation_module(
        self,
        flow_id: int,
        blog_id: int
    ):
        """
        플로우의 생성 모듈 실행
        
        조건:
        1. 프롬프트 모듈 존재
        2. 미사용 정식 제목 존재
        3. 크롤링 포스트 재고 < 기준값
        """
        # 1. 프롬프트 모듈 확인
        prompt_modules = await self._get_prompt_modules(flow_id, blog_id)
        if not prompt_modules:
            logger.info(f"[GENERATION] 프롬프트 모듈 없음: flow={flow_id}, blog={blog_id}")
            return
        
        # 2. 정식 제목 확인 (미사용 독립포스트)
        source_title = await self._get_unused_title(blog_id)
        if not source_title:
            logger.info(f"[GENERATION] 미사용 제목 없음: blog={blog_id}")
            return
        
        # 3. 재고 확인
        inventory = await self._get_crawling_post_count(blog_id)
        threshold = await self._get_inventory_threshold(blog_id)
        
        if inventory >= threshold:
            logger.info(f"[GENERATION] 재고 충분: {inventory} >= {threshold}")
            return
        
        # 4. 생성 태스크 큐에 추가
        for prompt_module in prompt_modules:
            generate_post_task.delay(
                blog_id=blog_id,
                prompt_module_id=prompt_module.id,
                source_title_id=source_title.id
            )
            logger.info(f"[GENERATION] 태스크 큐 추가: prompt_module={prompt_module.id}")
```

#### 4.2.3 재고 기반 트리거

**파일**: `app/services/generation/inventory_trigger.py`

```python
class InventoryTrigger:
    """
    발행 후 재고 체크하여 생성 트리거
    """
    
    async def check_and_trigger(
        self,
        blog_id: int,
        flow_id: int
    ):
        """
        발행 완료 후 호출되어 재고 체크 → 생성 트리거
        """
        # 1. 현재 재고 확인
        inventory = await self._get_crawling_post_count(blog_id)
        
        # 2. 성장 단계별 기준값 확인
        threshold = await self._get_threshold_by_growth_stage(blog_id)
        
        # 3. 재고 부족 시 생성 트리거
        if inventory < threshold:
            await self.flow_executor.execute_generation_module(
                flow_id=flow_id,
                blog_id=blog_id
            )
```

#### 4.2.4 블로그-프롬프트 모듈 자동 연동

**파일**: `app/api/prompt_modules.py` (수정)

```python
@router.post("/prompt-modules")
async def create_prompt_module(data: PromptModuleCreate):
    """
    프롬프트 모듈 생성 시 플로우에 블로그 자동 연결
    """
    # 1. 프롬프트 모듈 생성
    prompt_module = await prompt_module_service.create(data)
    
    # 2. 플로우에 블로그 자동 연결 (★ 핵심)
    if data.flow_id and data.blog_id:
        await flow_service.link_blog(
            flow_id=data.flow_id,
            blog_id=data.blog_id
        )
    
    return prompt_module
```

### 4.3 더블체크 항목

| 체크 항목 | 확인 내용 | 상태 |
|----------|----------|------|
| 프롬프트 모듈 → 생성 모듈 | 제목 재조합 프롬프트 정상 로드? | ⬜ |
| 프롬프트 모듈 → 생성 모듈 | 글 생성 프롬프트 정상 로드? | ⬜ |
| 참조자료 → 프롬프트 | `{reference_materials}` 플레이스홀더에 정상 주입? | ⬜ |
| 블로그 설정 → 생성 모듈 | AI 키 정상 로드? | ⬜ |
| 블로그 설정 → 생성 모듈 | 치환자 설정 정상 로드? | ⬜ |
| 정식 제목 → 생성 모듈 | 미사용 독립포스트 정상 선택? | ⬜ |
| 생성 모듈 → 크롤링 포스트 | 생성된 글 정상 저장? | ⬜ |
| 플로우 → 생성 모듈 | 트리거 정상 동작? | ⬜ |

### 4.4 체크포인트

- [ ] 프롬프트 모듈과 연동하여 글 생성 테스트
- [ ] 참조자료가 글에 실제로 반영되는지 확인
- [ ] 플로우 실행 시 생성 모듈 트리거 확인
- [ ] 재고 기반 자동 생성 동작 확인

---

## Phase 5: 통합 테스트 및 디버깅

### 5.1 목표

- 전체 시스템 통합 테스트
- 엣지 케이스 처리
- 성능 최적화

### 5.2 테스트 시나리오

#### 5.2.1 정상 케이스 테스트

| # | 시나리오 | 예상 결과 |
|---|----------|----------|
| 1 | 새 블로그 (급성장기) 첫 생성 | 재고 0 → 생성 실행 → 재고 1 |
| 2 | 재고 충분할 때 | 생성 스킵 |
| 3 | 프롬프트 모듈 2개인 플로우 | 각각 독립 실행 |
| 4 | 참조자료 0개일 때 | 참조자료 없이 글 생성 |
| 5 | 성장기 블로그 | 기준값 5로 동작 |

#### 5.2.2 엣지 케이스 테스트

| # | 시나리오 | 예상 처리 |
|---|----------|----------|
| 1 | 프롬프트 모듈 없음 | 생성 스킵, 로그 기록 |
| 2 | 미사용 제목 없음 | 생성 스킵, 로그 기록 |
| 3 | AI API 오류 | 재시도 3회 후 실패 처리 |
| 4 | 참조자료 수집 실패 | 참조자료 없이 계속 진행 |
| 5 | 이미지 생성 실패 | 이미지 없이 저장 |
| 6 | DB 저장 오류 | 롤백 및 로그 기록 |

#### 5.2.3 통합 테스트 코드

**파일**: `tests/integration/test_generation_flow.py`

```python
@pytest.mark.asyncio
async def test_full_generation_flow():
    """전체 생성 플로우 통합 테스트"""
    
    # Given: 테스트 데이터 준비
    blog = await create_test_blog()
    prompt_module = await create_test_prompt_module(blog.id)
    source_title = await create_test_source_title(blog.id)
    
    # When: 생성 실행
    result = await content_generator.generate(
        blog_id=blog.id,
        prompt_module_id=prompt_module.id,
        source_title_id=source_title.id
    )
    
    # Then: 검증
    assert result.success is True
    
    # 크롤링 포스트 저장 확인
    crawling_post = await get_crawling_post(result.crawling_post_id)
    assert crawling_post is not None
    assert crawling_post.title is not None
    assert crawling_post.content is not None
    
    # 메타데이터 저장 확인
    history = await get_generation_history(result.generation_history_id)
    assert history.source_title_id == source_title.id
    assert history.prompt_module_id == prompt_module.id
    
    # 원본 제목 사용 처리 확인
    source_title_updated = await get_source_title(source_title.id)
    assert source_title_updated.is_used is True


@pytest.mark.asyncio
async def test_reference_injection():
    """참조자료 프롬프트 주입 테스트"""
    
    # Given
    blog = await create_test_blog()
    prompt_module = await create_test_prompt_module(
        blog_id=blog.id,
        content_prompt="""
        제목: {title}
        
        참조자료:
        {reference_materials}
        
        위 내용을 바탕으로 글을 작성하세요.
        """
    )
    
    # When
    result = await content_generator.generate(...)
    
    # Then: 생성된 글에 참조자료 내용이 반영되었는지 확인
    crawling_post = await get_crawling_post(result.crawling_post_id)
    # (실제로는 AI 출력을 검증하기 어려우므로, 로그나 메타데이터로 확인)
    history = await get_generation_history(result.generation_history_id)
    assert history.reference_count > 0
```

### 5.3 디버깅 포인트

#### 로그 추가 위치

```python
# 1. 제목 재조합
logger.info(f"[RECOMBINE] 원본: {original_title} → 재조합: {recombined_title}")

# 2. 참조자료 수집
logger.info(f"[REFERENCE] 수집 완료: {references.count}개, 요약 길이: {len(references.summary)}")

# 3. 글 생성
logger.info(f"[CONTENT] 프롬프트 길이: {len(full_prompt)}, 참조자료 포함: {has_references}")
logger.info(f"[CONTENT] 생성 완료: 길이={len(content)}")

# 4. 이미지 생성
logger.info(f"[IMAGE] 생성 완료: {len(images)}개")

# 5. 저장
logger.info(f"[SAVE] 크롤링 포스트 저장: id={crawling_post.id}")
```

### 5.4 체크포인트

- [ ] 정상 케이스 전체 통과
- [ ] 엣지 케이스 전체 통과
- [ ] 로그로 각 단계 정상 동작 확인
- [ ] 100개 블로그 시뮬레이션 테스트

---

## Phase 6: 발행 모듈 연계 준비

### 6.1 목표

- 발행 모듈과의 연계 인터페이스 준비
- 재고 → 발행 → 재고 체크 → 생성 사이클 완성

### 6.2 작업 항목

#### 6.2.1 발행 모듈 연계 인터페이스

**파일**: `app/services/generation/inventory_manager.py`

```python
class InventoryManager:
    """
    크롤링 포스트 재고 관리
    발행 모듈과 생성 모듈 사이의 인터페이스
    """
    
    async def get_post_for_publish(
        self,
        blog_id: int
    ) -> CrawlingPost | None:
        """발행할 포스트 1개 가져오기 (FIFO)"""
        return await self.repository.get_oldest_unpublished(blog_id)
    
    async def mark_as_published(
        self,
        post_id: int
    ):
        """발행 완료 처리 (재고 -1 효과)"""
        await self.repository.mark_published(post_id)
    
    async def on_publish_complete(
        self,
        blog_id: int,
        flow_id: int
    ):
        """
        발행 완료 후 콜백
        → 재고 체크 → 부족 시 생성 트리거
        """
        await self.inventory_trigger.check_and_trigger(
            blog_id=blog_id,
            flow_id=flow_id
        )
```

#### 6.2.2 전체 자동화 사이클

```
┌─────────────────────────────────────────────────────────────┐
│                    자동화 사이클 (완성 시)                    │
└─────────────────────────────────────────────────────────────┘

[재발행 모듈] ─────────────────────────────────────────────┐
     │                                                     │
     ▼                                                     │
[발행 모듈] (Phase 6 이후)                                  │
     │                                                     │
     │ 발행 완료                                            │
     ▼                                                     │
[재고 체크] ◄──────────────────────────────────────────────┘
     │
     │ 재고 < 기준값?
     ▼
[생성 모듈] ◄── 현재 작업 중
     │
     │ 생성 완료
     ▼
[크롤링 포스트 저장] (재고 +1)
     │
     └────────────────────────► [발행 모듈] (다음 사이클)
```

### 6.3 체크포인트

- [ ] InventoryManager 구현
- [ ] 발행 모듈 연계 인터페이스 준비
- [ ] 수동 발행 테스트로 사이클 검증

---

## 파일 구조

### 신규 생성 파일

```
app/
├── core/
│   ├── celery_config.py          # Celery 설정
│   └── celery_tasks.py           # Celery 태스크 정의
│
├── models/
│   ├── generation_history.py     # 생성 이력 메타데이터
│   └── blog_growth_setting.py    # 블로그 성장 설정
│
├── services/
│   ├── ai/
│   │   └── ai_service.py         # AI 호출 공통 서비스
│   │
│   └── generation/
│       ├── generator.py          # 메인 생성 서비스
│       ├── title_recombiner.py   # 제목 재조합
│       ├── reference_collector.py # 참조자료 수집
│       ├── internal_linker.py    # 내부링크 삽입
│       ├── substitution_processor.py # 치환 처리
│       ├── inventory_trigger.py  # 재고 기반 트리거
│       └── inventory_manager.py  # 재고 관리
│
└── tests/
    ├── unit/
    │   └── test_generation/
    │       ├── test_title_recombiner.py
    │       ├── test_reference_collector.py
    │       └── test_internal_linker.py
    │
    └── integration/
        └── test_generation_flow.py
```

### 수정 필요 파일

```
app/
├── models/
│   ├── crawling_post.py          # generation_history_id 필드 추가
│   └── __init__.py               # 새 모델 등록
│
├── services/
│   └── flow/
│       └── flow_executor.py      # 생성 모듈 트리거 추가
│
├── api/
│   └── prompt_modules.py         # 블로그 자동 연결 로직
│
└── docker-compose.yml            # Redis, Celery 워커 추가
```

---

## 체크리스트

### Phase 1 완료 조건

- [ ] Celery + Redis 연결 테스트 통과
- [ ] 새 모델 마이그레이션 완료
- [ ] Docker Compose 전체 스택 실행

### Phase 2 완료 조건

- [ ] 제목 재조합 단독 테스트 통과
- [ ] 참조자료 수집 단독 테스트 통과
- [ ] AI 서비스 테스트 통과

### Phase 3 완료 조건

- [ ] 전체 생성 파이프라인 실행 성공
- [ ] 내부링크 정상 삽입
- [ ] 치환 처리 정상 동작
- [ ] 크롤링 포스트 저장 확인

### Phase 4 완료 조건

- [ ] 프롬프트 모듈 연동 완료
- [ ] 참조자료 → 프롬프트 주입 확인
- [ ] 플로우 트리거 정상 동작
- [ ] 재고 기반 자동 생성 동작

### Phase 5 완료 조건

- [ ] 통합 테스트 전체 통과
- [ ] 엣지 케이스 처리 완료
- [ ] 100개 블로그 시뮬레이션 통과

### Phase 6 완료 조건

- [ ] InventoryManager 구현
- [ ] 발행 모듈 인터페이스 준비
- [ ] 전체 사이클 수동 테스트 통과

---

## 다음 단계 (생성 모듈 완료 후)

1. **발행 모듈 구현**: 생성된 크롤링 포스트를 WordPress/Blogger에 발행
2. **전체 자동화 테스트**: 재발행 → 발행 → 재고 체크 → 생성 사이클
3. **모니터링 대시보드**: 생성 현황, 재고 현황, 오류 현황
4. **성능 최적화**: 워커 수 조정, 큐 최적화

---

> **문서 버전**: v1.0  
> **최종 수정**: 2025-02-06  
> **담당**: 네오 (설계) + Claude Code (구현)
