# 멀티 에이전트 시스템 상세 가이드

> CLAUDE.md에서 참조하는 상세 문서입니다.

## 시스템 구조

```
사용자 → /multi-agent [작업] → 오케스트레이터 → 에이전트 자동 협업 → 결과
```

## 에이전트 역할

| 에이전트 | 역할 | 담당 영역 |
|---------|------|----------|
| **@orchestrator** | 작업 분배, 결과 통합, 조율 | 전체 프로젝트 |
| **@frontend-agent** | UI/템플릿 작업 | `app/templates/`, `app/static/` |
| **@backend-agent** | API/모델/서비스 작업 | `app/api/`, `app/models/`, `app/services/` |
| **@explorer-agent** | 레거시 코드 분석 | `blogauto_new/` (읽기 전용) |
| **@reviewer-agent** | 코드 리뷰, 테스트 | `tests/`, `docs/` |

## 에이전트 파일 위치

```
~/.claude/
├── agents/
│   ├── orchestrator.md
│   ├── frontend-agent.md
│   ├── backend-agent.md
│   ├── explorer-agent.md
│   └── reviewer-agent.md
└── commands/
    └── multi-agent.md
```

## 사용 방법

```bash
# 복잡한 작업: 멀티 에이전트 사용
/multi-agent 새로운 모듈 관리 기능을 구현해줘

# 개별 에이전트 호출
@frontend-agent Flow 관리 페이지 UI를 개선해줘
@backend-agent Modules API 엔드포인트를 구현해줘
@explorer-agent blogauto_new에서 스케줄러 로직을 분석해줘
@reviewer-agent 방금 작성한 코드를 리뷰해줘
```

## 에이전트 간 통신 프로토콜

```
[FROM: agent-name]
[TO: target-agent]
[TYPE: request/response/error/review/notify]
[CONTENT]: 작업 내용
[FILES]: 관련 파일 목록
[DEPENDENCY]: 의존성 있는 다른 에이전트 작업
```

### 통신 유형

| TYPE | 설명 |
|------|------|
| `request` | 작업 요청 |
| `response` | 요청에 대한 응답 |
| `error` | 오류 보고 |
| `review` | 리뷰 결과 |
| `notify` | 작업 완료 알림 |

### 통신 예시

#### Backend -> Frontend 작업 완료 알림
```
[FROM: backend-agent]
[TO: orchestrator]
[TYPE: notify]
[CONTENT]: Modules API 엔드포인트 생성 완료
[FILES]: app/api/modules.py, app/schemas/module.py
[FOR: frontend-agent]
```

#### Reviewer -> Backend 수정 요청
```
[FROM: reviewer-agent]
[TO: orchestrator]
[TYPE: fix-request]
[TARGET-AGENT]: backend-agent
[FILE]: app/api/modules.py
[ISSUE]: 타입 힌트 누락
[LINE]: 45-50
```

#### 오류 발생 시 협의
```
[FROM: frontend-agent]
[TO: orchestrator]
[TYPE: error]
[CONTENT]: API 엔드포인트 호출 시 404 오류
[SUGGESTION]: backend-agent에게 엔드포인트 확인 요청
```

## 멀티 에이전트 워크플로우

### 기능 개발 흐름
```
1. 사용자 → /multi-agent 작업 지시
2. 오케스트레이터 → 작업 분석
3. (필요 시) @explorer-agent → 레거시 분석
4. 병렬 실행: @backend-agent + @frontend-agent
5. 결과 동기화
6. @reviewer-agent → 코드 리뷰
7. 문제 발견 시 → 해당 에이전트에 수정 요청
8. 최종 보고 → 사용자
```

### 오류 처리 흐름
```
1. 오류 발생 → 오케스트레이터에 보고
2. 관련 에이전트들 협의
3. 합의된 해결책 도출
4. 해당 에이전트가 수정
5. @reviewer-agent 재검증
6. 해결 안 되면 사용자에게 보고
```

### 멀티 에이전트 작업 전 체크리스트
```
- [ ] 작업 범위가 복잡한가? -> /multi-agent 사용
- [ ] Flowchart 준비되었는가?
- [ ] 레거시 분석이 필요한가? -> @explorer-agent 포함
- [ ] UI 작업이 포함되는가? -> @frontend-agent 포함
- [ ] API 작업이 포함되는가? -> @backend-agent 포함
```
