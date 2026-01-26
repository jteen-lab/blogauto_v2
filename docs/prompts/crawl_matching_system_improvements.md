# 크롤링 매칭 시스템 개선안

> **버전**: v1.0.0
> **작성일**: 2025-01-25
> **기반 문서**: crawl_matching_system_design.md v2.0.0
> **상태**: 검토 대기

---

## 1. 현재 설계 분석 결과

### 1.1 비효율성 요약

| 심각도 | 건수 | 주요 항목 |
|--------|------|----------|
| 🔴 높음 | 8건 | 매칭 알고리즘 O(N×M), 에러 처리 부재, 수동 단계 과다 |
| 🟡 중간 | 8건 | 임계값 이중 관리, 캐싱 부재, 동시성 문제 |
| 🟢 낮음 | 1건 | 콘텐츠 삭제 스케줄 누락 위험 |

### 1.2 업계 비교 결과

| 항목 | 업계 표준 | 현재 설계 | 갭 |
|------|----------|----------|-----|
| 자동화 수준 | 85~95% | 60~70% | -20% |
| 유사도 알고리즘 | Sentence-BERT + Cosine | 지역명 필터 + 하이브리드 | 의미적 유사도 미적용 |
| 에러 처리 | 자동 재시도 + 벤더 폴백 | 미정의 | 복원력 부족 |
| 콘텐츠 생성 | 자동화 파이프라인 | 6단계 수동 처리 | 자동화 부족 |

---

## 2. 높은 심각도 문제 상세

### 2.1 O(N×M) 매칭 알고리즘

**문제점 (섹션 8.2 Step 5)**

```python
# 현재 설계: O(N×M) 복잡도
for each crawled_post:       # N개 (예: 1,000개)
    for each main_title:     # M개 (예: 5,000개)
        calculate_similarity()  # 500만 회 비교
```

**영향:**
- 크롤링 포스트 1,000개 × 메인타이틀 5,000개 = 500만 회 비교
- Stage 0 지역명 필터링으로 조기 종료해도 여전히 병목
- 데이터 증가 시 선형적 성능 저하

---

### 2.2 4가지 필수 조건 복잡성

**문제점 (섹션 4.1, 5.1)**

```
현재 생성 모듈 동작 조건:
[조건 1] Flow에 생성 모듈 포함
[조건 2] Flow에 프롬프트 모듈 포함
[조건 3] Flow에 블로그 포함
[조건 4] 프롬프트 모듈에 연결된 블로그가 Flow에 포함  ← N:M 관계 검증
```

**영향:**
- 사용자가 4가지 조건을 모두 맞추기 어려움
- 조건 4는 N:M 관계로 설정 오류 발생 가능성 높음
- 신규 사용자 진입장벽 증가

---

### 2.3 에러 처리 부재

**문제점 (섹션 4.4)**

자동화 파이프라인에서 다음 실패 시나리오 처리 미정의:
- 크롤링: API 응답 오류, 타임아웃, 인증 만료
- AI API: Rate limit, 토큰 초과, 네트워크 오류
- DB: 연결 실패, 트랜잭션 충돌

**영향:**
- 파이프라인 중단 시 복구 방법 없음
- 부분 실패 시 데이터 불일치 발생

---

### 2.4 수동/자동 중복 크롤링

**문제점 (섹션 2.2, 6.2)**

```
자동화: "필요시 자동 실행"
수동: "블로그 선택 → 없으면 자동 크롤링"
```

**영향:**
- "필요시"의 기준 불명확
- 짧은 시간 내 동일 블로그 중복 크롤링 가능
- `last_crawled_at` 필드는 있으나 쿨다운 로직 미정의

---

### 2.5 전체 MainTitle 조회

**문제점 (섹션 8.2 Step 3)**

```
Step 3: 메인타이틀 조회 (최적화)
├─ 활성 그룹 → 대표 제목만 조회
└─ 그룹 없는 제목 → 전체 조회  ← 문제
```

**영향:**
- "그룹 없는 제목"은 필터 없이 전체 조회
- 블로그별 필터링 없음
- 데이터 증가 시 쿼리 성능 저하

---

### 2.6 대기 상태 수동 확정

**문제점 (섹션 2.2, 6.3)**

```
대기 상태 (65%~75%): 모두 수동 확정/거부 필요
```

**영향:**
- 대기 건수 100건 이상 시 사용자 피로도 급증
- 일괄 처리 기능 없음
- 자동화 수준 저하 원인

---

### 2.7 글 생성 후 6단계 수동 처리

**문제점 (섹션 6.5)**

```
[1] 마크다운 미리보기
[2] 이미지 미리보기
[3] 내부 링크 추가      ← 수동
[4] HTML 변환          ← 수동 클릭
[5] CSS 클래스 치환     ← 수동 클릭
[6] 웹 미리보기        ← 수동 클릭
[7] 저장
```

**영향:**
- 4~6단계는 자동화 가능한 작업
- 불필요한 클릭으로 사용자 경험 저하
- 자동화 실행 시에도 수동 개입 필요

---

### 2.8 동일 블로그 동시 크롤링

**문제점 (섹션 4.4, 6.2)**

**영향:**
- 스케줄러와 수동 트리거 동시 실행 시:
  - 중복 CrawledPost 생성
  - 매칭 결과 불일치
- 락 메커니즘 미정의

---

## 3. 개선안

### 3.1 아키텍처 단순화

#### 3.1.1 프롬프트 모듈 통합

**현재 (4가지 조건)**

```
Flow
├── 생성 모듈 ✓
├── 프롬프트 모듈 ✓
├── 블로그 ✓
└── 프롬프트 모듈 내 블로그가 Flow에 포함 ✓  ← 복잡한 N:M 검증
```

**개선안 (2가지 조건으로 단순화)**

```
Flow
├── 생성 모듈 (프롬프트 설정 내장 또는 프리셋 선택) ✓
└── 블로그 ✓

블로그 설정
└── 연결된 프롬프트 프리셋 선택 (1:N 관계)
```

**구현 방식:**

```python
class Blog(Base):
    # 기존 필드...

    # 프롬프트 직접 연결 (N:M → 1:N 단순화)
    prompt_preset_id = Column(Integer, ForeignKey("prompt_presets.id"))
    prompt_preset = relationship("PromptPreset")


class PromptPreset(Base):
    """재사용 가능한 프롬프트 프리셋"""
    __tablename__ = "prompt_presets"

    id = Column(Integer, primary_key=True)
    name = Column(String(100))

    # AI 벤더별 프롬프트
    openai_config = Column(JSONB)
    claude_config = Column(JSONB)
    gemini_config = Column(JSONB)

    # 이미지/제목 설정
    image_config = Column(JSONB)
    title_config = Column(JSONB)

    # 사용 중인 블로그들
    blogs = relationship("Blog", back_populates="prompt_preset")


class GenerateModule(Base):
    # 기존 필드...

    # 프롬프트 모듈 분리 대신 프리셋 참조
    default_prompt_preset_id = Column(Integer, ForeignKey("prompt_presets.id"))

    # 또는 블로그별 프롬프트 오버라이드 허용
    use_blog_prompt_preset = Column(Boolean, default=True)
```

**장점:**
- 사용자 설정 단계 50% 감소
- N:M 관계 검증 제거
- 블로그-프롬프트 1:N 관계로 직관적

---

#### 3.1.2 크롤러 플러그인 아키텍처

**현재 (하드코딩)**

```
services/
└── crawl_service.py
    ├── wordpress_crawler.py   # 개별 파일
    └── blogger_crawler.py     # 개별 파일
```

**개선안 (플러그인 패턴)**

```python
# app/services/crawlers/base.py
from abc import ABC, abstractmethod
from typing import List

class BaseCrawler(ABC):
    """크롤러 기본 인터페이스"""

    @abstractmethod
    async def crawl(self, blog_url: str, **kwargs) -> List[CrawledPost]:
        """블로그 포스트 크롤링"""
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """플랫폼 이름 반환"""
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """URL 유효성 검사"""
        pass

    def get_cooldown_seconds(self) -> int:
        """크롤링 쿨다운 시간 (기본 5분)"""
        return 300


# app/services/crawlers/wordpress.py
class WordPressCrawler(BaseCrawler):
    def get_platform_name(self) -> str:
        return "wordpress"

    async def crawl(self, blog_url: str, **kwargs) -> List[CrawledPost]:
        # RSS Feed 또는 REST API 크롤링
        pass


# app/services/crawlers/blogger.py
class BloggerCrawler(BaseCrawler):
    def get_platform_name(self) -> str:
        return "blogger"

    async def crawl(self, blog_url: str, **kwargs) -> List[CrawledPost]:
        # Blogger API v3 크롤링
        pass


# app/services/crawlers/registry.py
from typing import Dict, Type

class CrawlerRegistry:
    """크롤러 자동 등록 및 조회"""

    _crawlers: Dict[str, Type[BaseCrawler]] = {}

    @classmethod
    def register(cls, crawler_class: Type[BaseCrawler]):
        instance = crawler_class()
        cls._crawlers[instance.get_platform_name()] = crawler_class
        return crawler_class

    @classmethod
    def get_crawler(cls, platform: str) -> BaseCrawler:
        if platform not in cls._crawlers:
            raise UnsupportedPlatformError(platform)
        return cls._crawlers[platform]()

    @classmethod
    def get_all_platforms(cls) -> List[str]:
        return list(cls._crawlers.keys())


# 데코레이터로 자동 등록
@CrawlerRegistry.register
class WordPressCrawler(BaseCrawler):
    ...

@CrawlerRegistry.register
class BloggerCrawler(BaseCrawler):
    ...

# 추후 추가 시
@CrawlerRegistry.register
class TistoryCrawler(BaseCrawler):
    ...

@CrawlerRegistry.register
class NaverCrawler(BaseCrawler):
    ...
```

**장점:**
- 새 플랫폼 추가 시 파일 하나만 생성
- 기존 코드 수정 불필요
- 플랫폼별 설정 캡슐화

---

### 3.2 매칭 알고리즘 최적화

#### 3.2.1 2단계 필터링 전략

**현재: O(N×M)**

```python
for crawled in crawled_posts:
    for main in main_titles:
        score = calculate_similarity(crawled, main)  # 모든 쌍 비교
```

**개선안: O(N × k) where k << M**

```python
class OptimizedMatchingService:
    """2단계 최적화 매칭"""

    async def match_blog_titles(
        self,
        crawled_posts: List[CrawledPost],
        main_titles: List[MainTitle]
    ) -> MatchingResult:

        # 사전 인덱스 구축 (한 번만)
        canonical_index = self._build_canonical_index(main_titles)
        word_index = self._build_word_index(main_titles)
        location_index = self._build_location_index(main_titles)

        results = []

        for crawled in crawled_posts:
            # Stage 1: 빠른 후보군 필터링
            candidates = self._filter_candidates(
                crawled,
                canonical_index,
                word_index,
                location_index
            )

            # Stage 2: 후보군만 정밀 비교
            best_match = None
            for candidate in candidates:  # k개 (평균 10~50개)
                score = self._calculate_similarity(crawled, candidate)
                if score > best_match_score:
                    best_match = (candidate, score)

            results.append(best_match)

        return results

    def _filter_candidates(
        self,
        crawled: CrawledPost,
        canonical_index: Dict,
        word_index: Dict,
        location_index: Dict
    ) -> List[MainTitle]:
        """후보군 필터링 - O(1) ~ O(log N)"""

        candidates = set()

        # 1. 캐노니컬 키 완전 일치 (해시 조회 O(1))
        canonical_key = self._get_canonical_key(crawled.title)
        if canonical_key in canonical_index:
            return [canonical_index[canonical_key]]  # 즉시 반환

        # 2. 지역명 필터링
        location = self._extract_location(crawled.title)
        if location:
            # 같은 지역 또는 지역 없는 제목만 후보
            location_candidates = location_index.get(location, set())
            no_location_candidates = location_index.get(None, set())
            candidates = location_candidates | no_location_candidates
        else:
            candidates = set(main_titles)

        # 3. 단어 집합 Jaccard 필터 (> 0.3)
        crawled_words = set(self._tokenize(crawled.title))
        filtered = []
        for candidate in candidates:
            candidate_words = word_index[candidate.id]
            jaccard = len(crawled_words & candidate_words) / len(crawled_words | candidate_words)
            if jaccard > 0.3:
                filtered.append(candidate)

        return filtered[:50]  # 최대 50개 후보
```

**예상 성능:**
- 기존: 500만 회 비교
- 개선: 1,000 × 50 = 5만 회 비교
- **성능 개선: 99%**

---

#### 3.2.2 벡터 인덱싱 (장기 개선안)

**PostgreSQL + pgvector 활용**

```sql
-- pgvector 확장 설치
CREATE EXTENSION IF NOT EXISTS vector;

-- 메인타이틀 테이블 확장
ALTER TABLE main_titles ADD COLUMN embedding VECTOR(384);

-- 인덱스 생성 (IVFFlat)
CREATE INDEX main_titles_embedding_idx
ON main_titles USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 유사도 검색 쿼리 (O(log N))
SELECT
    id,
    title,
    1 - (embedding <=> $query_embedding) as similarity
FROM main_titles
WHERE 1 - (embedding <=> $query_embedding) > 0.65
ORDER BY embedding <=> $query_embedding
LIMIT 10;
```

**Python 구현:**

```python
from sentence_transformers import SentenceTransformer

class VectorMatchingService:
    """벡터 기반 유사도 검색"""

    def __init__(self):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    async def embed_title(self, title: str) -> List[float]:
        """제목 임베딩 생성"""
        return self.model.encode(title).tolist()

    async def find_similar_titles(
        self,
        crawled_title: str,
        threshold: float = 0.65,
        limit: int = 10
    ) -> List[Tuple[MainTitle, float]]:
        """벡터 유사도 검색"""

        query_embedding = await self.embed_title(crawled_title)

        result = await db.execute(
            """
            SELECT id, title, 1 - (embedding <=> :embedding) as similarity
            FROM main_titles
            WHERE 1 - (embedding <=> :embedding) > :threshold
            ORDER BY embedding <=> :embedding
            LIMIT :limit
            """,
            {
                "embedding": query_embedding,
                "threshold": threshold,
                "limit": limit
            }
        )

        return result.fetchall()
```

---

### 3.3 에러 처리 프레임워크

#### 3.3.1 크롤링 에러 처리

```python
# app/services/error_handlers/crawl_error_handler.py

from enum import Enum
from typing import Optional
import asyncio

class CrawlErrorType(Enum):
    RATE_LIMIT = "rate_limit"
    AUTH_EXPIRED = "auth_expired"
    NETWORK = "network"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"


class CrawlErrorHandler:
    """크롤링 에러 처리기"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [5, 30, 120]  # 지수 백오프

    async def crawl_with_retry(
        self,
        crawler: BaseCrawler,
        blog: Blog
    ) -> Optional[List[CrawledPost]]:
        """재시도 로직이 포함된 크롤링"""

        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                result = await crawler.crawl(blog.url)

                # 성공 시 상태 업데이트
                await self._update_blog_status(blog, "synced")
                return result

            except RateLimitError as e:
                last_error = e
                await self._log_error(blog, CrawlErrorType.RATE_LIMIT, attempt)
                await asyncio.sleep(self.RETRY_DELAYS[attempt])

            except AuthExpiredError as e:
                last_error = e
                await self._log_error(blog, CrawlErrorType.AUTH_EXPIRED, attempt)
                await self._notify_user(blog, "인증이 만료되었습니다. 재인증이 필요합니다.")
                await self._update_blog_status(blog, "auth_expired")
                break  # 재시도 불가

            except TimeoutError as e:
                last_error = e
                await self._log_error(blog, CrawlErrorType.TIMEOUT, attempt)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])

            except NetworkError as e:
                last_error = e
                await self._log_error(blog, CrawlErrorType.NETWORK, attempt)
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])

        # 모든 재시도 실패
        await self._update_blog_status(blog, "error")
        await self._notify_user(
            blog,
            f"크롤링 실패: {last_error}. 나중에 다시 시도됩니다."
        )

        return None

    async def _update_blog_status(self, blog: Blog, status: str):
        blog.crawl_status = status
        blog.last_crawl_error = datetime.now() if status == "error" else None
        await db.commit()

    async def _notify_user(self, blog: Blog, message: str):
        # 알림 시스템 연동
        await notification_service.send(
            user_id=blog.user_id,
            title="크롤링 알림",
            message=f"[{blog.name}] {message}"
        )

    async def _log_error(self, blog: Blog, error_type: CrawlErrorType, attempt: int):
        logger.warning(
            f"Crawl error: blog={blog.id}, type={error_type.value}, "
            f"attempt={attempt + 1}/{self.MAX_RETRIES}"
        )
```

---

#### 3.3.2 AI API 에러 처리 (벤더 폴백)

```python
# app/services/error_handlers/ai_error_handler.py

class AIVendorFallback:
    """AI 벤더 폴백 처리기"""

    VENDOR_PRIORITY = ["openai", "claude", "gemini"]
    MAX_RETRIES_PER_VENDOR = 2

    async def generate_with_fallback(
        self,
        prompt: str,
        prompt_config: PromptConfig
    ) -> GenerationResult:
        """벤더 폴백이 포함된 생성"""

        errors = []

        for vendor in self.VENDOR_PRIORITY:
            vendor_config = getattr(prompt_config, f"{vendor}_config", None)
            if not vendor_config:
                continue

            for attempt in range(self.MAX_RETRIES_PER_VENDOR):
                try:
                    result = await self._generate(vendor, prompt, vendor_config)

                    # 성공 로깅
                    logger.info(f"AI generation success: vendor={vendor}")
                    return result

                except RateLimitError as e:
                    errors.append((vendor, "rate_limit", str(e)))
                    await asyncio.sleep(2 ** attempt)  # 지수 백오프

                except TokenLimitError as e:
                    errors.append((vendor, "token_limit", str(e)))
                    # 토큰 초과는 재시도 불가, 다음 벤더로
                    break

                except NetworkError as e:
                    errors.append((vendor, "network", str(e)))
                    await asyncio.sleep(1)

        # 모든 벤더 실패
        await self._queue_for_retry(prompt, prompt_config)
        raise AllVendorsFailedError(errors)

    async def _generate(
        self,
        vendor: str,
        prompt: str,
        config: dict
    ) -> GenerationResult:
        """벤더별 생성 호출"""

        if vendor == "openai":
            return await openai_client.generate(prompt, **config)
        elif vendor == "claude":
            return await claude_client.generate(prompt, **config)
        elif vendor == "gemini":
            return await gemini_client.generate(prompt, **config)

    async def _queue_for_retry(self, prompt: str, config: PromptConfig):
        """실패한 요청 재시도 큐에 추가"""
        await retry_queue.add({
            "prompt": prompt,
            "config": config.dict(),
            "retry_at": datetime.now() + timedelta(minutes=30)
        })
```

---

### 3.4 동시성 제어

#### 3.4.1 블로그별 크롤링 락

```python
# app/services/locks/crawl_lock.py

import redis.asyncio as redis
from contextlib import asynccontextmanager

class CrawlLockManager:
    """Redis 기반 분산 크롤링 락"""

    LOCK_PREFIX = "crawl_lock:"
    LOCK_TTL = 300  # 5분

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    @asynccontextmanager
    async def acquire_lock(self, blog_id: int):
        """컨텍스트 매니저로 락 관리"""

        lock_key = f"{self.LOCK_PREFIX}{blog_id}"
        lock_acquired = False

        try:
            # NX: 키가 없을 때만 설정
            lock_acquired = await self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=self.LOCK_TTL
            )

            if not lock_acquired:
                raise BlogAlreadyCrawlingError(blog_id)

            yield

        finally:
            if lock_acquired:
                await self.redis.delete(lock_key)

    async def is_locked(self, blog_id: int) -> bool:
        """락 상태 확인"""
        lock_key = f"{self.LOCK_PREFIX}{blog_id}"
        return await self.redis.exists(lock_key) > 0

    async def extend_lock(self, blog_id: int, extra_seconds: int = 60):
        """락 시간 연장"""
        lock_key = f"{self.LOCK_PREFIX}{blog_id}"
        await self.redis.expire(lock_key, self.LOCK_TTL + extra_seconds)


# 사용 예시
class CrawlService:
    async def crawl_blog(self, blog_id: int):
        async with crawl_lock.acquire_lock(blog_id):
            # 락 획득 성공 시에만 크롤링 실행
            await self._do_crawl(blog_id)
```

---

#### 3.4.2 크롤링 쿨다운

```python
# app/services/crawl_cooldown.py

class CrawlCooldownManager:
    """크롤링 쿨다운 관리"""

    DEFAULT_COOLDOWN = 300  # 5분

    async def can_crawl(self, blog: Blog) -> Tuple[bool, Optional[int]]:
        """
        크롤링 가능 여부 확인

        Returns:
            (가능 여부, 남은 대기 시간(초))
        """
        if blog.last_crawled_at is None:
            return True, None

        elapsed = (datetime.now() - blog.last_crawled_at).total_seconds()
        cooldown = blog.crawl_cooldown or self.DEFAULT_COOLDOWN

        if elapsed >= cooldown:
            return True, None

        remaining = int(cooldown - elapsed)
        return False, remaining

    async def crawl_with_cooldown(
        self,
        blog: Blog,
        force: bool = False
    ) -> CrawlResult:
        """쿨다운 체크 후 크롤링"""

        can_crawl, remaining = await self.can_crawl(blog)

        if not can_crawl and not force:
            raise CrawlCooldownError(
                f"크롤링 쿨다운 중입니다. {remaining}초 후 다시 시도하세요."
            )

        return await self._do_crawl(blog)


# API 엔드포인트에서 사용
@router.post("/api/v1/crawl/{blog_id}")
async def trigger_crawl(
    blog_id: int,
    force: bool = Query(False, description="쿨다운 무시 강제 크롤링")
):
    blog = await get_blog(blog_id)

    try:
        result = await cooldown_manager.crawl_with_cooldown(blog, force=force)
        return {"status": "success", "crawled_count": len(result)}
    except CrawlCooldownError as e:
        return {"status": "cooldown", "message": str(e)}
```

---

### 3.5 UX 개선

#### 3.5.1 대기 상태 일괄 처리 UI

**현재**

```
검토대기: 150건
└── 1건씩 [확정] [거부] 클릭 필요
```

**개선안**

```html
<!-- templates/titles/matching_panel.html -->

<div x-data="batchMatchingPanel()">
    <!-- 일괄 작업 바 -->
    <div class="batch-action-bar">
        <label>
            <input type="checkbox" @change="toggleAll($event)" />
            전체 선택 (<span x-text="selectedCount"></span>/<span x-text="totalCount"></span>)
        </label>

        <div class="batch-actions">
            <button
                @click="confirmByThreshold(70)"
                class="btn btn-success"
            >
                70% 이상 일괄 확정
            </button>

            <button
                @click="confirmSelected()"
                class="btn btn-primary"
                :disabled="selectedCount === 0"
            >
                선택 항목 확정 (<span x-text="selectedCount"></span>)
            </button>

            <button
                @click="rejectSelected()"
                class="btn btn-danger"
                :disabled="selectedCount === 0"
            >
                선택 항목 거부
            </button>
        </div>
    </div>

    <!-- 필터 -->
    <div class="filters">
        <select x-model="scoreFilter">
            <option value="all">모든 점수</option>
            <option value="70+">70% 이상</option>
            <option value="65-70">65%~70%</option>
        </select>

        <input
            type="text"
            x-model="searchQuery"
            placeholder="제목 검색..."
        />
    </div>

    <!-- 대기 목록 테이블 -->
    <table>
        <thead>
            <tr>
                <th><input type="checkbox" @change="toggleAll($event)" /></th>
                <th>정식 제목</th>
                <th>크롤링 포스트</th>
                <th>유사도</th>
                <th>액션</th>
            </tr>
        </thead>
        <tbody>
            <template x-for="item in filteredItems">
                <tr :class="{ 'selected': item.selected, 'low-score': item.score < 68 }">
                    <td>
                        <input
                            type="checkbox"
                            :checked="item.selected"
                            @change="toggleItem(item.id)"
                        />
                    </td>
                    <td x-text="item.mainTitle"></td>
                    <td x-text="item.crawledTitle"></td>
                    <td>
                        <span
                            class="score-badge"
                            :class="getScoreClass(item.score)"
                            x-text="item.score + '%'"
                        ></span>
                    </td>
                    <td>
                        <button @click="confirm(item.id)" class="btn-sm btn-success">확정</button>
                        <button @click="reject(item.id)" class="btn-sm btn-danger">거부</button>
                    </td>
                </tr>
            </template>
        </tbody>
    </table>
</div>

<script>
function batchMatchingPanel() {
    return {
        items: [],
        selectedCount: 0,
        scoreFilter: 'all',
        searchQuery: '',

        get filteredItems() {
            return this.items.filter(item => {
                if (this.scoreFilter === '70+' && item.score < 70) return false;
                if (this.scoreFilter === '65-70' && (item.score < 65 || item.score >= 70)) return false;
                if (this.searchQuery && !item.mainTitle.includes(this.searchQuery)) return false;
                return true;
            });
        },

        async confirmByThreshold(threshold) {
            const targets = this.items.filter(i => i.score >= threshold);
            if (confirm(`${targets.length}건을 일괄 확정하시겠습니까?`)) {
                await this.batchConfirm(targets.map(t => t.id));
            }
        },

        async batchConfirm(ids) {
            await fetch('/api/v1/matching/batch-confirm', {
                method: 'POST',
                body: JSON.stringify({ ids, action: 'confirm' })
            });
            this.refresh();
        }
    }
}
</script>
```

---

#### 3.5.2 글 생성 단계 자동화 (6단계 → 3단계)

**현재 (6단계 수동)**

```
[1] 마크다운 미리보기
[2] 이미지 미리보기
[3] 내부 링크 추가
[4] HTML 변환
[5] CSS 치환
[6] 웹 미리보기
[7] 저장
```

**개선안 (3단계로 축소)**

```html
<!-- templates/generate/preview_popup.html -->

<div x-data="contentPreview()" class="preview-modal">
    <!-- 탭 네비게이션 -->
    <div class="preview-tabs">
        <button
            @click="activeTab = 'unified'"
            :class="{ active: activeTab === 'unified' }"
        >
            통합 미리보기
        </button>
        <button
            @click="activeTab = 'markdown'"
            :class="{ active: activeTab === 'markdown' }"
        >
            원본 마크다운
        </button>
        <button
            @click="activeTab = 'html'"
            :class="{ active: activeTab === 'html' }"
        >
            HTML 소스
        </button>
    </div>

    <!-- Step 1: 통합 미리보기 (자동 HTML 변환 + CSS 적용) -->
    <div x-show="activeTab === 'unified'" class="unified-preview">
        <div class="preview-layout">
            <!-- 웹 렌더링 미리보기 -->
            <div class="web-preview">
                <h4>웹 출력 미리보기</h4>
                <iframe
                    :srcdoc="renderedHtml"
                    class="preview-iframe"
                ></iframe>
            </div>

            <!-- 이미지 미리보기 -->
            <div class="image-preview">
                <h4>이미지</h4>
                <img :src="imageUrl" alt="생성된 이미지" />
            </div>
        </div>
    </div>

    <!-- Step 2: 내부 링크 추가 (선택적) -->
    <div class="internal-links-section">
        <h4>내부 링크 추가 (선택)</h4>
        <div class="link-suggestions" x-show="suggestedLinks.length > 0">
            <p>추천 내부 링크:</p>
            <template x-for="link in suggestedLinks">
                <label>
                    <input type="checkbox" :value="link.url" x-model="selectedLinks" />
                    <span x-text="link.title"></span>
                </label>
            </template>
        </div>
        <button @click="insertLinks()" class="btn btn-secondary">
            선택한 링크 삽입
        </button>
    </div>

    <!-- Step 3: 저장 -->
    <div class="action-buttons">
        <button @click="save()" class="btn btn-primary">
            저장
        </button>
        <button @click="saveAndPublish()" class="btn btn-success">
            저장 후 발행
        </button>
        <button @click="close()" class="btn btn-secondary">
            취소
        </button>
    </div>
</div>

<script>
function contentPreview() {
    return {
        activeTab: 'unified',
        markdownContent: '',
        renderedHtml: '',
        imageUrl: '',
        suggestedLinks: [],
        selectedLinks: [],

        async init() {
            // 생성 결과 로드
            const result = await this.loadGenerationResult();
            this.markdownContent = result.markdown;
            this.imageUrl = result.imageUrl;

            // 자동 HTML 변환 + CSS 치환
            this.renderedHtml = await this.autoConvert(result.markdown);

            // 내부 링크 추천
            this.suggestedLinks = await this.fetchSuggestedLinks();
        },

        async autoConvert(markdown) {
            // 서버에서 HTML 변환 + CSS 치환 자동 수행
            const response = await fetch('/api/v1/generate/convert', {
                method: 'POST',
                body: JSON.stringify({
                    markdown,
                    applyCSS: true,
                    blogPlatform: this.blogPlatform
                })
            });
            return (await response.json()).html;
        },

        async save() {
            await fetch('/api/v1/generate/save', {
                method: 'POST',
                body: JSON.stringify({
                    crawledPostId: this.crawledPostId,
                    html: this.renderedHtml,
                    imagePath: this.imageUrl,
                    internalLinks: this.selectedLinks
                })
            });
            this.close();
        }
    }
}
</script>
```

---

#### 3.5.3 생성 모듈 없이 테스트 허용

**현재**

```
생성 모듈 없이 블로그 선택 시:
→ 경고 메시지 + 차단
```

**개선안**

```python
# app/services/matching_service.py

class MatchingService:
    DEFAULT_THRESHOLDS = {
        "match_min": 75.0,
        "match_max": 100.0,
        "waiting_min": 65.0,
        "waiting_max": 74.9,
    }

    async def get_thresholds(self, flow_id: int) -> dict:
        """임계값 조회 - 생성 모듈 없으면 기본값 사용"""

        generate_module = await self._get_generate_module(flow_id)

        if generate_module:
            return {
                "match_min": generate_module.match_threshold_min,
                "match_max": generate_module.match_threshold_max,
                "waiting_min": generate_module.waiting_threshold_min,
                "waiting_max": generate_module.waiting_threshold_max,
                "source": "generate_module"
            }

        # 생성 모듈 없으면 기본값 사용 (차단하지 않음)
        return {
            **self.DEFAULT_THRESHOLDS,
            "source": "default",
            "warning": "생성 모듈이 없어 기본 임계값을 사용합니다. 자동화를 위해 생성 모듈을 추가하세요."
        }


# API 응답
@router.get("/api/v1/matching/blog/{blog_id}/status")
async def get_matching_status(blog_id: int):
    thresholds = await matching_service.get_thresholds(flow_id)

    return {
        "thresholds": thresholds,
        "has_generate_module": thresholds["source"] == "generate_module",
        "warning": thresholds.get("warning"),  # 경고만 표시, 차단하지 않음
        # ... 매칭 결과
    }
```

**UI에서 경고 표시**

```html
<div x-show="!hasGenerateModule" class="warning-banner">
    <span class="warning-icon">⚠️</span>
    <span x-text="thresholds.warning"></span>
    <a href="/modules/generate/create">생성 모듈 만들기</a>
</div>
```

---

### 3.6 캐싱 전략

#### 3.6.1 유사도 결과 캐싱

```python
# app/services/cache/similarity_cache.py

class SimilarityCache:
    """유사도 계산 결과 캐싱"""

    TTL = 86400  # 24시간
    KEY_PREFIX = "sim:"

    def __init__(self, redis_client):
        self.redis = redis_client

    def _make_key(self, title1_id: int, title2_id: int) -> str:
        """정렬된 키 생성 (순서 무관하게 동일 키)"""
        ids = sorted([title1_id, title2_id])
        return f"{self.KEY_PREFIX}{ids[0]}:{ids[1]}"

    async def get(self, title1_id: int, title2_id: int) -> Optional[float]:
        """캐시된 유사도 조회"""
        key = self._make_key(title1_id, title2_id)
        value = await self.redis.get(key)
        return float(value) if value else None

    async def set(self, title1_id: int, title2_id: int, score: float):
        """유사도 캐싱"""
        key = self._make_key(title1_id, title2_id)
        await self.redis.set(key, str(score), ex=self.TTL)

    async def invalidate_for_title(self, title_id: int):
        """특정 제목 관련 캐시 무효화"""
        pattern = f"{self.KEY_PREFIX}*{title_id}*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)


# 매칭 서비스에서 사용
class HybridMatchingService:
    async def calculate_similarity(
        self,
        crawled: CrawledPost,
        main: MainTitle
    ) -> float:
        # 캐시 확인
        cached = await similarity_cache.get(crawled.id, main.id)
        if cached is not None:
            return cached

        # 계산
        score = await self._do_calculate(crawled, main)

        # 캐싱
        await similarity_cache.set(crawled.id, main.id, score)

        return score
```

---

## 4. 구현 우선순위

### 🔴 Phase 1: 핵심 성능/안정성 (1-2주)

| 순위 | 작업 | 파일 | 예상 효과 |
|------|------|------|----------|
| P0-1 | 2단계 필터링 매칭 | `hybrid_matching_service.py` | 성능 95%+ 개선 |
| P0-2 | 크롤링 에러 핸들러 | `crawl_error_handler.py` | 안정성 확보 |
| P0-3 | AI API 에러 핸들러 | `ai_error_handler.py` | 복원력 확보 |
| P0-4 | 블로그 크롤링 락 | `crawl_lock.py` | 동시성 해결 |
| P0-5 | 크롤링 쿨다운 | `crawl_cooldown.py` | 중복 방지 |

### 🟡 Phase 2: UX 개선 (2-3주)

| 순위 | 작업 | 파일 | 예상 효과 |
|------|------|------|----------|
| P1-1 | 대기 일괄 처리 UI | `matching_panel.html` | 피로도 80% 감소 |
| P1-2 | 글 생성 단계 축소 | `preview_popup.html` | 클릭 50% 감소 |
| P1-3 | 테스트 허용 (경고만) | `matching_service.py` | 진입장벽 감소 |

### 🟢 Phase 3: 아키텍처 개선 (3-4주)

| 순위 | 작업 | 파일 | 예상 효과 |
|------|------|------|----------|
| P2-1 | 프롬프트 프리셋 도입 | `prompt_preset.py` | 설정 50% 단순화 |
| P2-2 | 크롤러 플러그인 | `crawlers/base.py` | 확장성 확보 |
| P2-3 | 유사도 캐싱 | `similarity_cache.py` | 반복 계산 제거 |

### 🔵 Phase 4: 고급 기능 (5-6주)

| 순위 | 작업 | 파일 | 예상 효과 |
|------|------|------|----------|
| P3-1 | pgvector 벡터 검색 | `vector_matching.py` | 대규모 대응 |
| P3-2 | 브랜드 보이스 학습 | `style_learner.py` | 품질 향상 |
| P3-3 | 실시간 SEO 피드백 | `seo_checker.py` | 검색 노출 개선 |

---

## 5. 예상 개선 효과 요약

| 지표 | 현재 | 개선 후 | 변화 |
|------|------|--------|------|
| 매칭 성능 | O(N×M) | O(N × k) | **95%+ 개선** |
| 자동화 수준 | 60~70% | 85~90% | **+20%** |
| 사용자 클릭 수 | 6단계 | 3단계 | **50% 감소** |
| 대기 처리 시간 | 개별 처리 | 일괄 처리 | **80% 단축** |
| 설정 복잡도 | 4가지 조건 | 2가지 조건 | **50% 단순화** |
| 에러 복원력 | 없음 | 재시도+폴백 | **안정성 확보** |

---

**문서 작성**: Claude Code
**최종 수정**: 2025-01-25
