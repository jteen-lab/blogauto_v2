# BlogAuto V2 — 통합 대시보드 구현 프롬프트 모음

> Claude Code에 그대로 붙여넣어 사용하세요.  
> 세 가지 디자인 중 하나를 선택해 해당 프롬프트를 전달하면 됩니다.

---

## 📋 공통 전달 사항 (모든 프롬프트 앞에 붙이세요)

```
CLAUDE.md 규칙을 반드시 준수해:
- 파일 < 500줄, 함수 < 50줄
- blogauto_new/ 절대 수정 금지
- 서버 실행 금지
- git add -A 금지, 파일별 개별 커밋
- 한국어로 보고
```

---

---

## 🅐 디자인 A — 클린 미니멀 (Plausible 스타일)

```
통합 대시보드 페이지를 구현해줘.

📐 디자인 방향: "클린 미니멀" — Plausible Analytics 스타일
- 초록(#1D9E75) + 파랑(#378ADD) 포인트 컬러
- 여백 충분, 0.5px 테두리, 카드 기반 레이아웃
- 단일 스크롤 페이지 (탭 없음)
- 폰트: DM Sans (Google Fonts CDN)

📊 포함할 차트 (ApexCharts CDN 사용):
1. KPI 카드 5개 (각 카드 하단에 미니 스파크라인)
   - 활성 블로그 수 / 오늘 생성 / 오늘 발행 / 성공률 / 대기 큐
2. Area Chart: 7일 생성·발행·재발행 트렌드 (상단 좌측, 60% 너비)
3. Donut Chart: 콘텐츠 상태 분포 생성56%·발행41%·실패3% (상단 우측, 40% 너비)
4. 워커 상태 패널: 진행률 바 (Generation/Publish/Upload 3개)
5. 활동 로그 패널: 최근 5건 타임라인 (성공=초록점, 실패=빨간점)
6. 콘텐츠 테이블: 최근 4건 (제목/블로그/상태배지/날짜)

🗂️ 생성할 파일:
1. app/templates/dashboard/dashboard_v2.html  (메인 템플릿, < 300줄)
2. app/static/js/dashboard/kpi_cards.js       (KPI + 스파크라인, < 150줄)
3. app/static/js/dashboard/charts.js          (Area + Donut, < 150줄)
4. app/static/js/dashboard/activity.js        (워커 + 로그 + 테이블, < 150줄)
5. app/api/dashboard.py                       (트렌드 API 엔드포인트, < 100줄)

📡 API 엔드포인트 (신규 1개만 추가):
- GET /api/v1/dashboard/trends?days=7
  응답: { dates[], generated[], published[], republished[] }
- 기존 API 재활용: /api/v1/dashboard/summary, /api/v1/blogs/stats

🎨 레이아웃 상세:
┌─ KPI 5개 카드 (grid 5열) ──────────────────┐
├─ Area Chart (60%) │ Donut Chart (40%) ──────┤
├─ Worker Status (50%) │ Activity Log (50%) ──┤
└─ Content Table (100%) ─────────────────────┘

💡 Alpine.js 데이터 구조:
<div x-data="dashboardApp()" x-init="init()">
  - dashboardApp(): { kpi, trends, workers, logs, contents }
  - init(): 병렬로 API 3개 호출 후 차트 렌더링
  - refreshData(): 60초마다 KPI만 폴링

⚙️ 기술 제약:
- ApexCharts: CDN (https://cdn.jsdelivr.net/npm/apexcharts)
- Alpine.js: 기존 프로젝트 버전 유지
- Tailwind CSS: 기존 클래스만 사용
- 다크모드: CSS 변수 활용 (var(--color-*))
- 반응형: 모바일에서 KPI 2열, 차트 1열로 변경

🚫 금지사항:
- ApexCharts 없이 Canvas 직접 사용 금지
- 인라인 스타일 남용 금지 (Tailwind 클래스 우선)
- 500줄 초과 파일 생성 금지

작업 순서:
1. app/api/dashboard.py 먼저 작성 (트렌드 API)
2. dashboard_v2.html 레이아웃 구조 작성
3. JS 파일 3개 순서대로 작성
4. base.html에 라우트 연결 확인

각 파일 완성 후 줄 수를 알려줘.
```

---

---

## 🅑 디자인 B — Editorial 스타일 (타이포그래피 중심)

```
통합 대시보드 페이지를 구현해줘.

📐 디자인 방향: "Editorial" — 뉴스레터/매거진 감성
- 상단에 1.5px 굵은 구분선 + 제목 + 날짜 헤더
- 초록(#3B6D11) + 파랑(#185FA5) 컬러, 여백 활용
- KPI 카드는 테두리 공유 방식 (카드 사이 구분선만, 외부 테두리 1개)
- 폰트: IBM Plex Sans (Google Fonts CDN)
- 단일 스크롤 페이지

📊 포함할 차트 (ApexCharts CDN 사용):
1. KPI 5개 (테두리 공유 grid, 각 셀에 delta 표시)
   - 활성 블로그 / 오늘 생성 / 오늘 발행 / 성공률 / 대기 큐
2. Area Chart (70% 너비): 7일 생성·발행 트렌드, fill 투명도 낮게
3. Donut Chart (30% 너비, 100px): 상태 분포 + 아래 mini stat 4개
4. Horizontal Bar Chart: 블로그별 발행량 TOP 5 (단색 농도 차이)
5. Column Chart (소형): 시간대별 발행 분포 (08~20시)
6. 활동 로그: 태그(발행/생성/실패) + 제목 리스트

🗂️ 생성할 파일:
1. app/templates/dashboard/dashboard_v2.html  (메인 템플릿, < 300줄)
2. app/static/js/dashboard/kpi_cards.js       (KPI 렌더링, < 120줄)
3. app/static/js/dashboard/trend_chart.js     (Area Chart, < 120줄)
4. app/static/js/dashboard/dist_charts.js     (Donut + Bar + Hour, < 180줄)
5. app/static/js/dashboard/log_panel.js       (활동 로그, < 100줄)
6. app/api/dashboard.py                       (트렌드 + 블로그별 통계 API, < 120줄)

📡 API 엔드포인트 (신규 2개):
- GET /api/v1/dashboard/trends?days=7
  응답: { dates[], generated[], published[], republished[] }
- GET /api/v1/dashboard/blog_stats
  응답: [{ blog_name, published_7d, generated_7d }]
- 기존 재활용: /api/v1/dashboard/summary

🎨 레이아웃 상세:
┌─ 헤더: "BlogAuto 운영 현황" │ 날짜 ────────┐ ← 1.5px border-bottom
├─ KPI 5개 (border 공유 grid) ───────────────┤
├─ Area Chart (전체 너비) ────────────────────┤
├─ Horizontal Bar (60%) │ Donut+Stats (40%) ─┤
├─ Hour Chart (50%) │ 활동 로그 (50%) ────────┤
└─ 콘텐츠 테이블 (전체 너비) ────────────────┘

💡 Alpine.js 구조:
<div x-data="editorialDashboard()" x-init="loadAll()">
  - loadAll(): Promise.all([summary, trends, blogStats, logs])
  - KPI delta: 양수=초록, 음수=빨강으로 자동 판별
  - 날짜: new Date().toLocaleDateString('ko-KR', {full options})

⚙️ 특별 스타일 포인트:
- KPI grid: border: 0.5px solid var(--border); border-radius 바깥에만
  → grid 내부는 border-right로 구분 (마지막 셀 제외)
- Area Chart fill: opacity 0.06~0.08로 매우 연하게
- Horizontal Bar: 같은 색상, 퍼센트에 따라 opacity 차등 (1.0 → 0.4)
- 헤더 구분선: border-bottom: 1.5px solid var(--color-text-primary)

🚫 금지사항:
- 그라데이션 배경 사용 금지
- box-shadow 남용 금지
- 500줄 초과 파일 생성 금지

작업 순서:
1. app/api/dashboard.py (API 2개 먼저)
2. dashboard_v2.html (레이아웃 + 헤더 구조)
3. JS 파일 순서대로 (kpi → trend → dist → log)
4. 라우트 등록 확인

각 파일 완성 후 줄 수 보고해줘.
```

---

---

## 🅒 디자인 C — 컴팩트 데이터 대시보드 (Ghost/Vercel 스타일)

```
통합 대시보드 페이지를 구현해줘.

📐 디자인 방향: "컴팩트 데이터" — Ghost CMS / Vercel Analytics 스타일
- 정보 밀도 최대화, 패딩 최소화
- 진한 초록(#0F6E56) + 진한 파랑(#0C447C) 컬러
- KPI 카드 안에 스파크라인 내장 (카드 하단 30px 영역)
- 폰트: Sora (Google Fonts CDN)
- 단일 스크롤 페이지

📊 포함할 차트 (ApexCharts CDN 사용):
1. KPI 카드 5개 — 각 카드 내부에 sparkline 차트 포함
   - 활성 블로그(스파크: 30일 추이) / 오늘 생성(스파크: 7일)
   - 오늘 발행(스파크: 7일) / 성공률(스파크: 7일, 빨강)
   - 대기 큐(스파크: 24시간)
2. Line Chart (65% 너비): 7일 생성·발행 (fill 매우 연하게, 포인트 작게)
3. Segmented Bar: 콘텐츠 상태 분포 (1줄짜리 가로 세그먼트 바)
   + 아래 3개 수치 (건수 포함: "56% · 847건")
4. Column Chart (소형, 35% 너비): 시간대별 발행 분포
5. Horizontal Bar: 블로그별 발행량 (progress bar 형태, 6px 높이)
6. 워커 진행률: wtrack/wfill 형태, dot 상태 표시
7. 활동 로그: 시간 + 태그(OK/ERR 배지) + 제목 (초밀도)
8. 콘텐츠 테이블: 4행, 상태 pill 배지 (발행/생성/실패/대기)

🗂️ 생성할 파일:
1. app/templates/dashboard/dashboard_v2.html   (메인 템플릿, < 300줄)
2. app/static/js/dashboard/kpi_spark.js        (KPI + 스파크라인 5개, < 180줄)
3. app/static/js/dashboard/main_charts.js      (Line + Segment + Hour, < 160줄)
4. app/static/js/dashboard/perf_panel.js       (블로그별 Bar + 워커 + 로그, < 150줄)
5. app/static/js/dashboard/content_table.js    (테이블 렌더링, < 80줄)
6. app/api/dashboard.py                        (API 엔드포인트 3개, < 130줄)

📡 API 엔드포인트:
- GET /api/v1/dashboard/trends?days=7
  응답: { dates[], generated[], published[], republished[] }
- GET /api/v1/dashboard/blog_stats
  응답: [{ blog_name, published_7d, generated_7d, success_rate }]
- GET /api/v1/dashboard/hourly
  응답: { hours[0..23], counts[] }
- 기존 재활용: /api/v1/dashboard/summary

🎨 레이아웃 상세 (컴팩트, gap: 8px):
┌─ KPI 5개 (grid-cols-5, 각 카드 안에 sparkline) ─┐
├─ Line+Segment (65%) │ Hour Chart (35%) ──────────┤
├─ Blog Perf Bar (100%) ───────────────────────────┤
├─ Content Table (60%) │ Worker+Log (40%) ──────────┤
└───────────────────────────────────────────────────┘

💡 ApexCharts 스파크라인 설정:
{
  chart: { type: 'line', sparkline: { enabled: true }, height: 30 },
  stroke: { width: 1.5, curve: 'smooth' },
  tooltip: { enabled: false }
}
→ sparkline: true 사용 시 axes/grid 자동 숨김

💡 Alpine.js 구조:
<div x-data="compactDashboard()" x-init="init()">
  - init(): 4개 API 병렬 호출
  - renderSparklines(): KPI 카드 DOM 마운트 후 ApexCharts 순서대로 초기화
  - x-effect 사용: KPI 데이터가 준비되면 sparkline 렌더링

⚙️ 세그먼트 바 구현:
<div class="flex h-2 rounded-full overflow-hidden gap-0.5">
  <div :style="`width:${pct.generated}%`" class="bg-[#0F6E56] rounded-sm"></div>
  <div :style="`width:${pct.published}%`" class="bg-[#0C447C] rounded-sm"></div>
  <div :style="`width:${pct.failed}%`" class="bg-[#993C1D] rounded-sm"></div>
</div>

⚙️ 블로그별 바 (progress 형태):
<div class="flex items-center gap-2 text-xs">
  <span class="w-20 text-right text-secondary truncate">{{ blog.name }}</span>
  <div class="flex-1 h-1.5 bg-secondary rounded">
    <div :style="`width:${blog.pct}%`" class="h-full bg-[#0C447C] rounded"></div>
  </div>
  <span class="w-8 font-medium">{{ blog.count }}</span>
</div>

🚫 금지사항:
- 스파크라인을 canvas 직접 그리기 금지 (ApexCharts sparkline 사용)
- 과도한 padding/margin으로 밀도 낮추기 금지
- 500줄 초과 파일 생성 금지
- 인라인 onclick 사용 금지 (Alpine.js @click 사용)

작업 순서:
1. app/api/dashboard.py (API 3개)
2. dashboard_v2.html (전체 레이아웃 구조, Alpine x-data 바인딩)
3. kpi_spark.js (스파크라인 초기화 핵심)
4. main_charts.js (Line + Segment + Hour)
5. perf_panel.js (Blog Bar + Worker + Log)
6. content_table.js (테이블)
7. 라우트 등록

각 파일 작성 후:
- 줄 수 보고
- 타입 힌트 확인
- 함수별 50줄 이하 확인
```

---

---

## 💡 선택 가이드

| | 디자인 A | 디자인 B | 디자인 C |
|---|---|---|---|
| **작업 난이도** | ⭐⭐ 쉬움 | ⭐⭐⭐ 보통 | ⭐⭐⭐⭐ 높음 |
| **신규 파일 수** | 5개 | 6개 | 7개 |
| **신규 API 수** | 1개 | 2개 | 3개 |
| **차트 수** | 4개 | 6개 | 8개 |
| **정보 밀도** | 낮음 (여백 많음) | 보통 | 높음 |
| **추천 상황** | 빠르게 완성 원할 때 | 레이아웃 실험할 때 | 데이터 많이 보고 싶을 때 |

> **초보자 추천**: 디자인 A부터 구현하고, 만족스러우면 C 방향으로 개선하는 것을 권장합니다.
