# 유사도 매칭 워크플로우 재설계 v2

> **버전**: v2.0.0
> **작성일**: 2025-01-25
> **상태**: 사용자 제안 기반 보강
> **기반**: 사용자 피드백 + crawl_matching_system_improvements.md

---

## 1. 핵심 변경 사항 요약

### 1.1 사용자 제안 핵심 포인트

| 영역 | 이전 설계 | 변경 제안 | 이유 |
|------|----------|----------|------|
| **매칭 시점** | 블로그 선택 시마다 유사도 매칭 | 블로그 등록 시 1회만 (연결테스트) | 1,500개 제목에 3~5분 소요 → 비효율 |
| **매칭 분류** | 매칭/대기/미매칭 3단계 | 매칭/미매칭 2단계로 단순화 | 대기 분류 불필요, 사용자 선택권 제공 |
| **필수 요소** | 유사도 매칭이 글 생성 전 필수 | 선택적 요소로 변경 | 유사 포스트 허용 옵션 추가 |
| **UI 표시** | 블로그 선택 시 실시간 매칭 | 사전 매칭 결과 페어매칭으로 즉시 표시 | 대기 시간 제거 |
| **로그 위치** | 우측 상단 버튼 → 3줄 출력 | 고정요약탭 하단 1줄 + 확장 탭 | UX 개선 |

### 1.2 신규 블로그 vs 기존 운영 블로그

| 구분 | 신규 블로그 | 기존 운영 블로그 |
|------|-----------|----------------|
| **크롤링 필요** | ❌ 불필요 | ✅ 필요 |
| **유사도 매칭** | ❌ 불필요 | ✅ 필요 (백그라운드) |
| **대기/미매칭** | ❌ 발생 안함 | ✅ 발생 가능 |
| **글 생성 흐름** | 생성 → 발행대기 → 발행 → 매칭 | 크롤링 → 매칭 → 생성 → 발행 |

---

## 2. 재설계된 워크플로우

### 2.1 블로그 등록 및 초기 설정 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                  블로그 등록 및 초기 설정 플로우                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [Step 1] 블로그 관리에서 블로그 등록                           │
│   └─ URL, 플랫폼(WordPress/Blogger), 인증 정보 입력              │
│                                                                 │
│   [Step 2] 연결테스트 버튼 클릭                                  │
│   ├─ API 연결 확인                                              │
│   ├─ 포스트 타이틀 크롤링 시작                                   │
│   │   ├─ 신규 블로그: 0개 수집 → 완료                           │
│   │   └─ 기존 블로그: N개 수집 → CrawledPost 저장               │
│   │                                                             │
│   └─ 크롤링 완료 후 (기존 블로그만)                              │
│       └─ [백그라운드] 유사도 매칭 자동 시작                       │
│           ├─ MainTitle ↔ CrawledPost 비교                       │
│           ├─ 매칭 결과 저장 (matched_id 부여)                    │
│           └─ 완료 시 동작로그에 표시                             │
│                                                                 │
│   [Step 3] 연결테스트 완료                                       │
│   ├─ 블로그 카드에 상태 표시                                     │
│   │   ├─ "연결됨" (신규 블로그)                                  │
│   │   ├─ "연결됨 - 매칭 진행 중" (기존 블로그, 매칭 중)          │
│   │   └─ "연결됨 - 매칭 완료 (85/100)" (기존 블로그, 완료)       │
│   └─ 동작로그에 결과 표시                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 신규 블로그 글 생성 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                 신규 블로그 글 생성 플로우                         │
│                 (크롤링 포스트 없음)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [전제] 블로그에 발행된 포스트가 없음                            │
│                                                                 │
│   [Step 1] 메인타이틀 선택 (독립포스트 상태)                      │
│   └─ 모든 메인타이틀이 독립포스트 (매칭된 크롤링 포스트 없음)      │
│                                                                 │
│   [Step 2] AI 글 생성                                            │
│   └─ 프롬프트 적용 → 글/이미지 생성                              │
│                                                                 │
│   [Step 3] 저장                                                  │
│   └─ 메인타이틀 상태: "독립포스트" → "발행대기"                   │
│                                                                 │
│   [Step 4] 발행                                                  │
│   ├─ 블로그에 포스트 발행                                        │
│   ├─ 새 CrawledPost 레코드 자동 생성                             │
│   │   └─ title: 발행된 제목 (재조합된 제목)                      │
│   │   └─ match_status: "matched"                                │
│   │   └─ matched_main_title_id: 해당 메인타이틀 ID              │
│   └─ 메인타이틀 상태: "발행대기" → "매칭"                        │
│                                                                 │
│   ※ 대기/미매칭이 발생하지 않는 구조                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 기존 운영 블로그 글 생성 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│               기존 운영 블로그 글 생성 플로우                      │
│               (크롤링 포스트 있음)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   [전제] 연결테스트 시 백그라운드 유사도 매칭 완료                 │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 생성 모듈 설정: "유사 포스트 중복 발행"                   │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │                                                         │   │
│   │   [옵션 A] 유사 포스트 중복 발행 = ON                    │   │
│   │   └─ 매칭 상태 무관하게 모든 메인타이틀 대상             │   │
│   │   └─ 매칭된 제목도 글 생성 대상                         │   │
│   │   └─ 제목 재조합으로 유사 포스트 발행                   │   │
│   │                                                         │   │
│   │   [옵션 B] 유사 포스트 중복 발행 = OFF                   │   │
│   │   └─ 매칭된 제목 제외                                   │   │
│   │   └─ 미매칭 메인타이틀만 글 생성 대상                   │   │
│   │   └─ (선택) 수동 분류로 미매칭 조정 가능                │   │
│   │                                                         │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   [글 생성 → 발행 → 매칭ID 부여]                                 │
│   └─ 발행 완료 시 해당 제목들끼리 매칭ID 자동 부여               │
│   └─ 다음 블로그 선택 시에도 자동 매칭 유지                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 임계값 단순화

### 3.1 기존 3단계 → 2단계로 변경

**기존 (복잡)**
```
매칭: 75%~100%
대기: 65%~74%  ← 제거
미매칭: <65%
```

**변경 (단순)**
```
매칭: ≥ 임계값 (기본 65%)
미매칭: < 임계값
```

### 3.2 임계값 설정 위치

```python
class GenerateModule(Base):
    """생성 모듈"""

    # 유사 포스트 중복 발행 설정
    allow_duplicate_similar_posts: bool = False

    # 유사도 매칭 임계값 (중복 발행 OFF 시에만 적용)
    matching_threshold: float = 65.0  # 기본값 65%

    # 대기 분류 사용 여부 (선택적)
    use_waiting_category: bool = False  # 기본 OFF
    waiting_threshold_min: float = 50.0  # 사용 시에만 적용
```

### 3.3 사용자 선택 시나리오

| 시나리오 | 설정 | 결과 |
|----------|------|------|
| **유사 제목도 발행하고 싶다** | `allow_duplicate_similar_posts = True` | 모든 메인타이틀 대상 |
| **유사 제목은 제외하고 싶다** | `allow_duplicate_similar_posts = False` | 미매칭만 대상 |
| **대기 분류도 사용하고 싶다** | `use_waiting_category = True` | 매칭/대기/미매칭 3단계 |
| **수동으로 세밀하게 분류하고 싶다** | 데이터 관리에서 수동 분류 | 개별 제목 매칭 조정 |

---

## 4. 데이터 관리 UI 재설계

### 4.1 정식 제목 탭 - 블로그 선택 시 동작 변경

**기존 (매번 유사도 매칭)**
```
블로그 선택 → 크롤링 확인 → 유사도 매칭 실행 (3~5분) → 결과 표시
```

**변경 (사전 매칭 결과 즉시 표시)**
```
블로그 선택 → 크롤링 데이터 호출 → 매칭ID 기반 페어매칭 → 즉시 표시
```

### 4.2 정식 제목 탭 UI

```
┌──────────────────────────────────────────────────────────────────────┐
│  데이터 관리 - 정식 제목                                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [블로그 선택] ▼ 내 워드프레스 블로그 1                                │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ 📊 매칭 현황 (즉시 로드)                                        │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ • 전체 메인타이틀: 500개                                        │  │
│  │ • 매칭됨: 85개                                                  │  │
│  │ • 독립포스트 (미매칭): 415개 ← 글 생성 대상                      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  [탭: 전체 | 매칭됨 | 독립포스트]                                      │
│                                                                      │
│  ┌────┬─────────────────┬──────────────────┬────────────────────┐   │
│  │ #  │ 정식 제목        │ 크롤링 포스트     │ 상태               │   │
│  ├────┼─────────────────┼──────────────────┼────────────────────┤   │
│  │ 1  │ 서울 맛집 추천   │ 서울 맛집 추천 10선│ 🟢 매칭 (92%)      │   │
│  │ 2  │ 부산 여행 코스   │ 부산 여행 완벽가이드│ 🟢 매칭 (78%)      │   │
│  │ 3  │ 제주도 카페 투어 │ -                │ 🔵 독립포스트       │   │
│  │ 4  │ 강남 맛집 탐방   │ -                │ 🔵 독립포스트       │   │
│  └────┴─────────────────┴──────────────────┴────────────────────┘   │
│                                                                      │
│  ※ 미매칭 크롤링 포스트는 표시하지 않음 (기존 블로그 독자 발행 글)     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.3 미매칭 크롤링 포스트 처리

> **변경 포인트**: 미매칭 크롤링 포스트는 정식 제목 탭에 표시하지 않음

**이유:**
- 미매칭 = 기존 운영 블로그의 독자 발행 글 (메인타이틀과 무관)
- 메인타이틀 기반 관리 화면에서 불필요한 노이즈
- 필요시 별도 탭(크롤링 포스트 탭)에서 확인 가능

**별도 크롤링 포스트 탭 (선택적)**
```
┌──────────────────────────────────────────────────────────────────────┐
│  데이터 관리 - 크롤링 포스트                                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [블로그 선택] ▼ 내 워드프레스 블로그 1                                │
│                                                                      │
│  [탭: 전체 | 매칭됨 | 미매칭]                                          │
│                                                                      │
│  ┌────┬─────────────────────┬──────────────────┬──────────────┐     │
│  │ #  │ 크롤링 포스트        │ 매칭된 정식 제목  │ 상태         │     │
│  ├────┼─────────────────────┼──────────────────┼──────────────┤     │
│  │ 1  │ 서울 맛집 추천 10선  │ 서울 맛집 추천    │ 🟢 매칭      │     │
│  │ 2  │ 내 일상 이야기 #1    │ -               │ ⚪ 미매칭     │     │
│  │ 3  │ 광고 포스트          │ -               │ ⚪ 미매칭     │     │
│  └────┴─────────────────────┴──────────────────┴──────────────┘     │
│                                                                      │
│  ※ 미매칭 포스트는 글 생성 대상이 아님 (기존 독자 발행 글)             │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. 동작 로그 UI 재설계

### 5.1 현재 → 변경

**현재**
```
┌──────────────────────────────────────────────────────────────────────┐
│  [우측 상단 버튼] 클릭 시 로그 화면 활성화                              │
│  └─ 로그 3줄 출력                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

**변경**
```
┌──────────────────────────────────────────────────────────────────────┐
│  [고정요약탭]                                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ [요약1] [요약2] [요약3] [요약4]                                 │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ 📋 [최신 로그 1줄] ← 슬라이드 애니메이션 (모바일: 좌우 슬라이드) │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  [고정요약탭 클릭 시 하단시트 확장]                                    │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ [탭: 요약탭 선택 | 최근활동 | 동작로그]                         │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │                                                                │  │
│  │ [요약탭 선택] ← 기존 요약탭 선택 UI                            │  │
│  │                                                                │  │
│  │ [최근활동] ← 최근 수행한 작업 목록                             │  │
│  │  • 15:30 - 블로그 A 글 생성 완료                               │  │
│  │  • 15:25 - 블로그 B 발행 완료                                  │  │
│  │                                                                │  │
│  │ [동작로그] ← 전체 로그 출력                                    │  │
│  │  • 15:30:45 [INFO] 블로그 A 유사도 매칭 완료 (85/100)          │  │
│  │  • 15:30:40 [INFO] 블로그 A 크롤링 완료 (120개)                │  │
│  │  • 15:30:35 [INFO] 블로그 A 연결테스트 시작                    │  │
│  │  ...                                                           │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 모바일 대응

```css
/* 로그 1줄 슬라이드 (모바일) */
.log-line {
    overflow: hidden;
    white-space: nowrap;
}

.log-line-content {
    display: inline-block;
    animation: slide-left 10s linear infinite;
}

@keyframes slide-left {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}

/* 텍스트가 잘리지 않도록 */
@media (max-width: 768px) {
    .log-line-content {
        animation: slide-left 15s linear infinite;
    }
}
```

---

## 6. 발행 후 자동 매칭 처리

### 6.1 발행 완료 시 자동 매칭ID 부여

```python
async def publish_post(
    self,
    main_title_id: int,
    blog_id: int,
    content: str,
    published_title: str  # 재조합된 제목
) -> PublishResult:
    """포스트 발행 및 자동 매칭 처리"""

    # 1. 블로그에 포스트 발행
    result = await self._publish_to_blog(blog_id, content, published_title)

    # 2. 새 CrawledPost 레코드 생성 (발행된 포스트)
    crawled_post = CrawledPost(
        blog_id=blog_id,
        title=published_title,
        url=result.post_url,
        published_at=datetime.now(),
        match_status="matched",
        matched_main_title_id=main_title_id,
        match_score=100.0,  # 직접 발행이므로 100%
        crawled_at=datetime.now()
    )
    db.add(crawled_post)

    # 3. 메인타이틀 상태 업데이트
    main_title = await db.get(MainTitle, main_title_id)
    main_title.publish_status = "published"
    main_title.matched_crawled_post_id = crawled_post.id

    await db.commit()

    return PublishResult(
        success=True,
        post_url=result.post_url,
        crawled_post_id=crawled_post.id
    )
```

### 6.2 다음 블로그 선택 시 자동 매칭 유지

```python
async def get_matching_pairs(
    self,
    blog_id: int
) -> List[MatchingPair]:
    """블로그 선택 시 매칭 페어 조회 (유사도 재계산 없음)"""

    # 사전 매칭된 결과 조회 (matched_main_title_id 기반)
    pairs = await db.execute(
        select(CrawledPost, MainTitle)
        .join(MainTitle, CrawledPost.matched_main_title_id == MainTitle.id)
        .where(CrawledPost.blog_id == blog_id)
        .where(CrawledPost.match_status == "matched")
    )

    return [
        MatchingPair(
            crawled_post=cp,
            main_title=mt,
            score=cp.match_score
        )
        for cp, mt in pairs.fetchall()
    ]
```

---

## 7. 백그라운드 유사도 매칭 상세

### 7.1 연결테스트 후 백그라운드 매칭 트리거

```python
async def connection_test(self, blog_id: int) -> ConnectionTestResult:
    """연결테스트 실행"""

    blog = await db.get(Blog, blog_id)

    # 1. API 연결 확인
    connection_ok = await self._test_connection(blog)
    if not connection_ok:
        return ConnectionTestResult(success=False, error="연결 실패")

    # 2. 포스트 타이틀 크롤링
    crawled_posts = await self._crawl_posts(blog)
    await self._save_crawled_posts(blog_id, crawled_posts)

    # 3. 크롤링 결과 확인
    if len(crawled_posts) == 0:
        # 신규 블로그: 매칭 불필요
        blog.crawl_status = "synced"
        blog.is_new_blog = True
        await db.commit()

        return ConnectionTestResult(
            success=True,
            crawled_count=0,
            is_new_blog=True,
            message="신규 블로그로 등록되었습니다."
        )

    # 4. 기존 운영 블로그: 백그라운드 매칭 시작
    blog.crawl_status = "matching"
    blog.is_new_blog = False
    await db.commit()

    # 백그라운드 태스크로 매칭 실행
    background_tasks.add_task(
        self._run_background_matching,
        blog_id=blog_id,
        crawled_posts=crawled_posts
    )

    return ConnectionTestResult(
        success=True,
        crawled_count=len(crawled_posts),
        is_new_blog=False,
        message=f"{len(crawled_posts)}개 포스트 발견. 백그라운드에서 매칭 진행 중..."
    )


async def _run_background_matching(
    self,
    blog_id: int,
    crawled_posts: List[CrawledPost]
):
    """백그라운드 유사도 매칭 실행"""

    try:
        # 동작로그 시작
        await self._log_activity(blog_id, "유사도 매칭 시작", "info")

        # 메인타이틀 조회
        main_titles = await self._get_main_titles()

        # 유사도 매칭 실행
        matching_results = await self._execute_matching(
            crawled_posts,
            main_titles
        )

        # 결과 저장
        matched_count = 0
        for result in matching_results:
            if result.score >= self.matching_threshold:
                result.crawled_post.match_status = "matched"
                result.crawled_post.matched_main_title_id = result.main_title.id
                result.crawled_post.match_score = result.score
                matched_count += 1
            else:
                result.crawled_post.match_status = "unmatched"

        # 블로그 상태 업데이트
        blog = await db.get(Blog, blog_id)
        blog.crawl_status = "synced"
        blog.last_matched_at = datetime.now()
        await db.commit()

        # 동작로그 완료
        await self._log_activity(
            blog_id,
            f"유사도 매칭 완료 ({matched_count}/{len(crawled_posts)})",
            "success"
        )

    except Exception as e:
        # 에러 처리
        await self._log_activity(blog_id, f"매칭 실패: {str(e)}", "error")
        blog = await db.get(Blog, blog_id)
        blog.crawl_status = "error"
        await db.commit()
```

### 7.2 블로그 카드 상태 표시

```html
<!-- 블로그 카드 상태 배지 -->
<div class="blog-card" x-data="{ status: '{{ blog.crawl_status }}' }">
    <div class="blog-info">
        <h3>{{ blog.name }}</h3>
        <span class="platform-badge">{{ blog.platform }}</span>
    </div>

    <!-- 상태 배지 -->
    <div class="status-badge" :class="getStatusClass(status)">
        <template x-if="status === 'never'">
            <span>⚪ 연결 필요</span>
        </template>
        <template x-if="status === 'synced' && blog.is_new_blog">
            <span>🟢 연결됨 (신규)</span>
        </template>
        <template x-if="status === 'matching'">
            <span class="pulse">🟡 매칭 진행 중...</span>
        </template>
        <template x-if="status === 'synced' && !blog.is_new_blog">
            <span>🟢 연결됨 - 매칭 완료 ({{ blog.matched_count }}/{{ blog.crawled_count }})</span>
        </template>
        <template x-if="status === 'error'">
            <span>🔴 오류</span>
        </template>
    </div>

    <button @click="connectionTest()" :disabled="status === 'matching'">
        연결테스트
    </button>
</div>
```

---

## 8. 데이터 모델 변경

### 8.1 Blog 모델 확장

```python
class Blog(Base):
    # 기존 필드...

    # 신규/기존 블로그 구분
    is_new_blog: bool = True  # True: 신규, False: 기존 운영

    # 크롤링/매칭 상태
    crawl_status: str = "never"  # never | matching | synced | error
    last_crawled_at: Optional[datetime]
    last_matched_at: Optional[datetime]

    # 매칭 통계
    crawled_count: int = 0  # 크롤링된 포스트 수
    matched_count: int = 0  # 매칭된 포스트 수
```

### 8.2 CrawledPost 모델 (단순화)

```python
class CrawledPost(Base):
    """크롤링된 포스트"""
    __tablename__ = "crawled_posts"

    id = Column(Integer, primary_key=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False)

    # 포스트 정보
    title = Column(String(500), nullable=False)
    url = Column(String(1000))
    published_at = Column(DateTime)

    # 매칭 정보 (단순화: 매칭/미매칭 2단계)
    match_status = Column(String(20), default="pending")
    # pending | matched | unmatched
    matched_main_title_id = Column(Integer, ForeignKey("main_titles.id"))
    match_score = Column(Float)

    # 메타데이터
    crawled_at = Column(DateTime, default=func.now())
```

### 8.3 MainTitle 모델 확장

```python
class MainTitle(Base):
    # 기존 필드...

    # 발행 상태
    publish_status: str = "independent"
    # independent: 독립포스트 (미발행)
    # pending: 발행대기 (글 생성 완료)
    # published: 발행 완료

    # 매칭된 크롤링 포스트 (발행 후)
    matched_crawled_post_id = Column(Integer, ForeignKey("crawled_posts.id"))
```

---

## 9. 보강 제안 사항

### 9.1 증분 크롤링 지원

> **문제**: 블로그에 새 포스트가 발행되면 다시 전체 크롤링?

**제안: 증분 크롤링**

```python
async def incremental_crawl(self, blog_id: int):
    """증분 크롤링 - 새 포스트만 수집"""

    blog = await db.get(Blog, blog_id)

    # 마지막 크롤링 시간 이후 포스트만 수집
    new_posts = await self._crawl_posts(
        blog,
        since=blog.last_crawled_at
    )

    if new_posts:
        # 새 포스트 저장 및 매칭
        await self._save_and_match_new_posts(blog_id, new_posts)

    blog.last_crawled_at = datetime.now()
    await db.commit()
```

**트리거:**
- 수동: 블로그 카드에서 "새로고침" 버튼
- 자동: 글 생성 전 자동 증분 크롤링 (선택적)

### 9.2 매칭 결과 수동 조정 기능

> **문제**: 자동 매칭이 틀렸을 때 수정 방법?

**제안: 수동 매칭 조정 UI**

```
┌────────────────────────────────────────────────────────────────┐
│  수동 매칭 조정                                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  [크롤링 포스트]                                                │
│  "서울 맛집 추천 베스트 10선"                                   │
│                                                                │
│  [현재 매칭]: 서울 맛집 추천 (92%)                              │
│                                                                │
│  [액션]                                                        │
│  • [매칭 해제] → 미매칭으로 변경                                │
│  • [다른 제목으로 매칭] → 메인타이틀 선택                        │
│  • [새 메인타이틀 생성 후 매칭] → 메인타이틀 추가                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.3 매칭 품질 대시보드

> **문제**: 매칭 결과의 전반적인 품질 파악 어려움

**제안: 매칭 품질 요약**

```
┌────────────────────────────────────────────────────────────────┐
│  블로그별 매칭 품질 대시보드                                     │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  [블로그 A]                                                    │
│  ├─ 총 크롤링: 120개                                           │
│  ├─ 매칭됨: 85개 (71%)                                         │
│  │   ├─ 고신뢰 (90%+): 60개                                    │
│  │   ├─ 중신뢰 (70~89%): 20개                                  │
│  │   └─ 저신뢰 (65~69%): 5개  ← 검토 권장                      │
│  └─ 미매칭: 35개 (기존 독자 발행)                               │
│                                                                │
│  [액션]                                                        │
│  • [저신뢰 매칭 검토] → 5건 확인                                │
│  • [전체 재매칭] → 임계값 변경 후 재실행                        │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 9.4 알림 시스템 연동

> **문제**: 백그라운드 매칭 완료 시 사용자가 모를 수 있음

**제안: 알림 연동**

```python
async def _notify_matching_complete(self, blog_id: int, result: MatchingResult):
    """매칭 완료 알림"""

    blog = await db.get(Blog, blog_id)

    # 동작로그에 추가 (이미 구현)
    await self._log_activity(
        blog_id,
        f"유사도 매칭 완료 ({result.matched_count}/{result.total_count})",
        "success"
    )

    # 브라우저 알림 (선택적)
    if user_settings.enable_browser_notifications:
        await notification_service.send_browser_notification(
            user_id=blog.user_id,
            title="매칭 완료",
            body=f"{blog.name}: {result.matched_count}개 매칭됨"
        )

    # 이메일 알림 (선택적)
    if user_settings.enable_email_notifications:
        await notification_service.send_email(
            user_id=blog.user_id,
            subject=f"[BlogAuto] {blog.name} 매칭 완료",
            body=f"..."
        )
```

### 9.5 에러 복구 전략

> **문제**: 백그라운드 매칭 중 에러 발생 시 처리

**제안: 자동 재시도 및 부분 성공 저장**

```python
async def _run_background_matching_with_recovery(
    self,
    blog_id: int,
    crawled_posts: List[CrawledPost]
):
    """에러 복구가 포함된 백그라운드 매칭"""

    batch_size = 100
    total_matched = 0
    total_errors = 0

    for i in range(0, len(crawled_posts), batch_size):
        batch = crawled_posts[i:i+batch_size]

        try:
            results = await self._match_batch(batch)
            total_matched += len([r for r in results if r.matched])

            # 배치 완료 시 중간 저장
            await db.commit()

        except Exception as e:
            total_errors += len(batch)
            logger.error(f"Batch {i} failed: {e}")

            # 에러 배치 스킵하고 계속 진행
            continue

    # 최종 결과 업데이트
    blog = await db.get(Blog, blog_id)
    blog.crawl_status = "synced" if total_errors == 0 else "partial"
    blog.matched_count = total_matched
    await db.commit()

    # 부분 실패 시 경고 로그
    if total_errors > 0:
        await self._log_activity(
            blog_id,
            f"매칭 부분 완료: {total_matched}개 성공, {total_errors}개 실패",
            "warning"
        )
```

---

## 10. 구현 우선순위

### Phase 1: 핵심 워크플로우 변경 (1주)

| 순위 | 작업 | 설명 |
|------|------|------|
| P0-1 | 연결테스트 시 크롤링 + 백그라운드 매칭 | 기존 블로그 선택 시 매칭 제거 |
| P0-2 | 매칭/미매칭 2단계 단순화 | 대기 분류 제거 |
| P0-3 | 발행 시 자동 CrawledPost 생성 | 신규 블로그 플로우 |
| P0-4 | 블로그 카드 상태 표시 | 매칭 진행 상태 표시 |

### Phase 2: UI 변경 (1주)

| 순위 | 작업 | 설명 |
|------|------|------|
| P1-1 | 동작로그 위치 변경 | 고정요약탭 하단 1줄 + 확장 탭 |
| P1-2 | 정식 제목 탭 UI 변경 | 페어매칭 즉시 표시 |
| P1-3 | 모바일 로그 슬라이드 | 긴 로그 좌우 스크롤 |

### Phase 3: 생성 모듈 설정 (1주)

| 순위 | 작업 | 설명 |
|------|------|------|
| P2-1 | 유사 포스트 중복 발행 옵션 | ON/OFF 설정 |
| P2-2 | 임계값 단일화 | 매칭 임계값만 설정 |
| P2-3 | 대기 분류 선택적 사용 | 고급 옵션으로 제공 |

### Phase 4: 부가 기능 (1주)

| 순위 | 작업 | 설명 |
|------|------|------|
| P3-1 | 증분 크롤링 | 새 포스트만 수집 |
| P3-2 | 수동 매칭 조정 | 매칭 해제/변경 UI |
| P3-3 | 알림 시스템 | 브라우저/이메일 알림 |

---

## 11. 예상 효과

| 지표 | 기존 | 변경 후 | 개선 |
|------|------|--------|------|
| 블로그 선택 시 대기 시간 | 3~5분 | 즉시 | **100% 제거** |
| 설정 복잡도 | 매칭/대기/미매칭 3단계 | 매칭/미매칭 2단계 | **33% 단순화** |
| 유사도 매칭 실행 횟수 | 블로그 선택마다 | 등록 시 1회 | **95%+ 감소** |
| 사용자 결정 필요 항목 | 대기 분류 수동 확정 | 선택적 | **피로도 감소** |
| 신규 블로그 설정 시간 | 크롤링+매칭 대기 | 즉시 사용 | **100% 제거** |

---

**문서 작성**: Claude Code
**최종 수정**: 2025-01-25
