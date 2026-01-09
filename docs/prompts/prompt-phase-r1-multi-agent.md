# Phase R-1: 플로우 엔진 및 재발행 기능 구현

## 📋 작업 개요

플로우에 등록된 모듈들이 실제로 동작하도록 **플로우 엔진**을 구현합니다.
우선 **재발행 동작**을 먼저 구현하고 테스트합니다.

---

## 🎯 목표

1. 플로우 엔진: 모듈 조합에 따라 동작 실행
2. WordPress 재발행: REST API로 글 재발행
3. Blogger 재발행: Google API로 글 재발행
4. APScheduler: 설정된 시간에 자동 실행
5. 테스트용 API: 수동 실행 엔드포인트

---

## 📌 핵심 개념: 모듈 조합 = 동작 패턴

```
[재발행 동작] - 이번 Phase에서 구현
블로그 + 재발행 모듈
→ 기존 글의 날짜를 업데이트하여 최신 글처럼 노출

[글 생성 동작] - 차후 구현
블로그 + 프롬프트 + 생성 → 저장

[발행 동작] - 차후 구현
블로그 + 발행 (저장된 글을)
```

**중요**: 모듈들은 순차 실행이 아니라, 조합별로 독립적으로 동작

---

## 🤖 에이전트별 작업 분배

### @explorer-agent (레거시 분석)

**작업**: `blogauto_new/`에서 WordPress/Blogger 재발행 관련 코드 분석

**분석 대상**:
1. WordPress 재발행 로직 위치 및 구현 방식
2. Blogger 재발행 로직 위치 및 구현 방식
3. 인증 방식 (Application Password, OAuth 등)
4. API 호출 패턴

**출력**: 분석 결과를 @backend-agent에게 전달

---

### @backend-agent (핵심 구현)

**작업 1**: WordPress 재발행 서비스

```
파일: app/services/wordpress_service.py (< 200줄)

기능:
- get_posts(): 글 목록 조회 (오래된 순)
- update_post_date(): 글 날짜 업데이트
- republish(): 재발행 실행 (위 두 기능 조합)

인증: Basic Auth (username + Application Password)
API: WordPress REST API v2
```

**작업 2**: Blogger 재발행 서비스

```
파일: app/services/blogger_service.py (< 200줄)

기능:
- get_posts(): 글 목록 조회
- revert_to_draft_and_publish(): 임시저장 후 재발행
- republish(): 재발행 실행

인증: OAuth (GoogleCredential 모델 사용)
API: Blogger API v3
```

**작업 3**: 플로우 엔진

```
파일 구조:
app/engine/
├── __init__.py
├── flow_engine.py          # 메인 엔진 (< 150줄)
└── actions/
    ├── __init__.py
    └── republish.py        # 재발행 액션 (< 100줄)

FlowEngine.execute(flow, action_type, blog, module):
- action_type에 따라 해당 액션 실행
- 통합 엔진 + 조건문 방식 (핸들러 패턴 아님)
```

**작업 4**: APScheduler 설정

```
파일: app/scheduler/scheduler.py (< 150줄)

기능:
- 매 시간 정각에 check_and_execute_flows() 실행
- 현재 시간에 스케줄된 모듈의 플로우 조회
- 오토런에 등록되고 실행 중인 플로우만 대상
- FlowEngine으로 실행
```

**작업 5**: main.py 수정

```
- lifespan 이벤트에 스케줄러 등록
- setup_scheduler() / shutdown_scheduler()
```

**작업 6**: 테스트용 API

```
파일: app/routers/engine.py (< 150줄)

엔드포인트:
- POST /api/v1/engine/execute/{flow_id}?action_type=republish
  → 수동 재발행 실행
- GET /api/v1/engine/test-connection/{blog_id}
  → 블로그 API 연결 테스트
```

**작업 7**: requirements.txt 추가

```
apscheduler>=3.10.0
httpx>=0.25.0
```

---

### @reviewer-agent (리뷰 및 테스트)

**작업**:
1. 각 파일 줄 수 검증 (< 300줄)
2. 함수 크기 검증 (< 50줄)
3. 타입 힌트 확인
4. 에러 처리 확인
5. 로깅 확인

---

## 📁 생성할 파일 목록

| # | 파일 경로 | 담당 | 예상 줄 수 |
|---|----------|------|-----------|
| 1 | app/services/wordpress_service.py | @backend-agent | 150줄 |
| 2 | app/services/blogger_service.py | @backend-agent | 150줄 |
| 3 | app/engine/__init__.py | @backend-agent | 5줄 |
| 4 | app/engine/flow_engine.py | @backend-agent | 100줄 |
| 5 | app/engine/actions/__init__.py | @backend-agent | 5줄 |
| 6 | app/engine/actions/republish.py | @backend-agent | 80줄 |
| 7 | app/scheduler/__init__.py | @backend-agent | 5줄 |
| 8 | app/scheduler/scheduler.py | @backend-agent | 150줄 |
| 9 | app/routers/engine.py | @backend-agent | 120줄 |

| # | 수정할 파일 | 담당 | 수정 내용 |
|---|------------|------|----------|
| 1 | app/main.py | @backend-agent | lifespan에 스케줄러 등록 |
| 2 | requirements.txt | @backend-agent | apscheduler, httpx 추가 |

---

## 🔧 기술 상세

### WordPress 재발행 방식

```python
# 1. 오래된 글 조회
GET /wp-json/wp/v2/posts?per_page=1&orderby=date&order=asc

# 2. 날짜 업데이트 (재발행)
POST /wp-json/wp/v2/posts/{id}
{
    "date": "2026-01-09T15:00:00",
    "date_gmt": "2026-01-09T06:00:00"
}

# 인증: Basic Auth
Authorization: Basic base64(username:app_password)
```

### Blogger 재발행 방식

```python
# 1. 글 목록 조회
GET /blogger/v3/blogs/{blog_id}/posts?maxResults=1&orderBy=published

# 2. 임시저장으로 변경
POST /blogger/v3/blogs/{blog_id}/posts/{post_id}/revert

# 3. 다시 발행
POST /blogger/v3/blogs/{blog_id}/posts/{post_id}/publish

# 인증: OAuth Bearer Token
Authorization: Bearer {access_token}
```

### 스케줄러 동작

```
매 시간 0분에 실행:
1. 현재 요일/시간 확인 (예: 월요일 09시)
2. module_schedules에서 해당 시간 스케줄 조회
3. 스케줄된 모듈을 포함하는 플로우 조회
   - is_in_autorun = true
   - status = 'active'
4. 각 플로우의 블로그에 대해 FlowEngine.execute() 호출
```

---

## ⚠️ 제약사항

- 파일당 300줄 미만 (권장)
- 함수당 50줄 미만
- 타입 힌트 필수
- docstring 필수
- 에러 처리 필수
- 로깅 필수 (logger.info, logger.error)
- `blogauto_new/` 참조만, 수정 금지

---

## 🧪 테스트 방법

### 1. 블로그 연결 테스트
```bash
curl -X GET "http://localhost:8001/api/v1/engine/test-connection/{blog_id}"
```

### 2. 수동 재발행 테스트
```bash
curl -X POST "http://localhost:8001/api/v1/engine/execute/{flow_id}?action_type=republish"
```

### 3. 스케줄러 로그 확인
```bash
docker-compose logs app --tail 50 | grep SCHEDULER
```

---

## 📋 구현 순서

```
1. @explorer-agent: 레거시 코드 분석 (WordPress/Blogger 재발행)
   ↓
2. @backend-agent: wordpress_service.py 생성
   ↓
3. @backend-agent: blogger_service.py 생성
   ↓
4. @backend-agent: engine/actions/republish.py 생성
   ↓
5. @backend-agent: engine/flow_engine.py 생성
   ↓
6. @backend-agent: scheduler/scheduler.py 생성
   ↓
7. @backend-agent: routers/engine.py 생성
   ↓
8. @backend-agent: main.py 수정 (스케줄러 등록)
   ↓
9. @backend-agent: requirements.txt 수정
   ↓
10. @reviewer-agent: 전체 코드 리뷰
```

---

## 🚀 시작

위 내용대로 구현을 시작해주세요.

**우선 @explorer-agent가 `blogauto_new/`에서 WordPress/Blogger 재발행 관련 코드를 분석**해주세요.
