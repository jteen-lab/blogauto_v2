# 회귀 방지 및 수정 작업 지침

> CLAUDE.md에서 참조하는 상세 문서입니다.
> 코드 수정 시 기존 기능을 훼손하지 않기 위한 필수 규칙을 정의합니다.

---

## 1. 수정 전 영향 범위 분석 (MUST)

### 모든 참조처 확인
- 코드 수정 시 **해당 함수/모델 속성을 호출하는 모든 경로**를 추적한다
- `grep -rn "함수명\|변수명\|속성명" app/` 으로 전체 참조를 확인한 후 수정한다
- 특히 다음 변경 시 **모든 호출처** 검증 필수:
  - 모델 속성명/관계명 변경 (예: `flow_modules` → `module_links`)
  - 함수 시그니처 변경 (파라미터 추가/삭제/순서 변경)
  - API 응답 형식 변경
  - Pydantic 스키마 필드 변경

### 연관 모듈 파악
- 수정 대상 파일뿐만 아니라, 해당 파일을 **import/include하는 모든 파일**을 확인한다
- 예: `autorun_service.py` 수정 시 → `autorun.py` (라우터), `flow_scheduler.py`, `scheduler_manager.py` 모두 확인

---

## 2. 수정 후 회귀 테스트 (MUST)

### 기본 규칙
- 기능 A를 수정했을 때, A와 **연관된 기능 B/C도 함께 테스트**한다
- "수정한 파일"이 아닌 "수정이 영향을 미치는 기능 전체"를 테스트 범위로 잡는다

### 오토런/스케줄러 수정 시 필수 검증 항목
1. Docker 재빌드 후 앱 로그에서 `ERROR`/`WARNING` 확인
2. `_register_active_flows` 로그: `Count=N` (N > 0 확인)
3. 플로우 시작(start) → 스케줄 등록 로그 확인
4. 플로우 일시정지(pause) → 스케줄 해제 확인
5. 플로우 재개(resume) → 스케줄 재등록 + **실제 실행** 확인
6. generate/publish/republish 각 액션 실행 여부 확인

### Docker 재빌드 후 필수 확인
```bash
# 1. 앱 로그 에러 확인 (필수)
docker-compose logs app --tail 50 | grep -i "ERROR\|FAIL\|Traceback"

# 2. 스케줄러 초기화 확인
docker-compose logs app | grep "FLOW_SCHEDULER.*Registering\|FLOW_SCHEDULER.*Setup"

# 3. Celery 워커 정상 동작 확인
docker-compose logs celery_generation_worker --tail 10
docker-compose logs celery_publish_worker --tail 10
```

---

## 3. 기존 기능 보호 원칙 (CRITICAL)

### 절대 규칙
- 수정의 목적이 "기능 B 수정"이더라도, **기존에 동작하던 "기능 A"를 훼손해서는 안 된다**
- 새 코드 경로를 추가할 때는 해당 경로에서 참조하는 **모든 모델/함수가 실제 존재하는지** 검증한다
- 수정 완료 보고 전 **전체 동작 시나리오**를 한 번 이상 점검한다

### 전체 동작 시나리오 체크리스트
```
- [ ] 플로우에서 1회 생성 → 성공 확인
- [ ] 플로우에서 1회 발행 → 1건만 발행 확인
- [ ] 오토런에서 플로우 시작 → 스케줄 등록 로그 확인
- [ ] 오토런에서 플로우 일시정지 → 스케줄 해제 확인
- [ ] 오토런에서 플로우 재개 → 스케줄 재등록 + 실행 확인
- [ ] 동작로그에 결과 표시 확인
- [ ] 설정 페이지 정상 동작 확인
- [ ] 데이터 관리 페이지 정상 로드 확인
- [ ] 모듈 관리 페이지 정상 로드 확인
```

---

## 4. 작업 완료 보고 기준

### 보고 기준
- **"코드 수정 완료"가 아닌 "기능 동작 확인 완료"**를 보고 기준으로 한다
- 보고 전 반드시 다음을 수행한다:
  1. Python 구문 검증 (`ast.parse`)
  2. 파일 크기 확인 (< 500줄)
  3. Docker 앱 로그 에러 확인
  4. 핵심 기능 동작 확인 (수정한 기능 + 연관 기능)

### 보고 형식
```
수정 완료:
- 수정 파일: [목록]
- 수정 내용: [요약]
- 영향 범위: [수정으로 영향 받는 기능 목록]
- 검증 결과:
  - [ ] 수정 기능 동작 확인
  - [ ] 연관 기능 회귀 테스트
  - [ ] Docker 앱 로그 에러 없음
```

---

## 5. 자주 발생하는 실수 방지

### 모델 속성 참조 오류
```python
# ❌ 잘못된 참조 (존재하지 않는 속성)
flow.flow_modules  # AttributeError

# ✅ 올바른 참조 (실제 모델 정의 확인)
flow.module_links  # Flow 모델의 실제 relationship 이름
```

**확인 방법**: `grep -n "relationship\|Column\|mapped_column" app/models/flow.py`

### Alpine.js 전역 변수 참조
```javascript
// ❌ x-for에서 전역 변수 직접 참조 (Alpine 프록시에서 찾지 못함)
x-for="item in GLOBAL_CONST"

// ✅ 컴포넌트 데이터로 복사 후 참조
init() { this.localData = GLOBAL_CONST; }
x-for="item in localData"
```

### Celery 이벤트 루프 충돌
```python
# ❌ db_manager.get_session() (이전 루프의 커넥션 풀 충돌)
async with db_manager.get_session() as db: ...

# ✅ celery_db_session() (NullPool로 충돌 방지)
from app.core.celery_async_bridge import celery_db_session
async with celery_db_session() as db: ...
```

### JS 중괄호 균형
- 기존 파일에 메서드를 추가할 때, `return { ... }` 객체의 닫는 괄호 위치를 반드시 확인
- 추가 후 `node -e "new Function(fs.readFileSync('파일경로','utf8'))"` 으로 구문 검증

---

> **최종 수정**: 2026-05-02
