# CLAUDE.md

> **BlogAuto v2** | **버전**: v4.0.0 | **날짜**: 2026-04-07

## 언어

**IMPORTANT: 모든 소통은 한국어로 합니다.** (작업 보고, 커밋 메시지, 오류 설명 포함)

---

## 절대 금지 (NEVER)

**1. 서버 실행 금지** — `runserver`, `gunicorn`, `celery` 등 서버 시작 명령 사용 금지. 사용자가 직접 관리.

**2. blogauto_new/ 수정 금지** — 레거시 코드. 읽기 전용 참조만 가능. `@explorer-agent`만 분석 가능.

**3. 파일 크기 초과 금지** — 파일 500줄, 함수 50줄 초과 시 즉시 분리.

**4. Flowchart 없이 개발 금지** — 모든 기능은 Mermaid 순서도(`docs/flowcharts/`)부터 작성.

**5. `git add -A` 사용 금지** — 파일별 개별 `git add`. `.env` 파일은 절대 수정/덮어쓰기 금지.

---

## 환경변수 규칙

- `.env`에 새 환경변수 추가 시 **반드시** `.env.required`에도 등록
- `.env`는 git 미추적 (개인정보 보호), `.env.required`는 git 추적 (변수 목록)
- 롤백/리셋 시 `.env` 파일은 절대 수정하지 않음
- 앱 시작 시 누락된 환경변수를 자동 경고 (`validate_env_required()`)

---

## 멀티 에이전트 시스템

복잡한 작업은 `/multi-agent` 커맨드 사용. 작업 시작 전 **에이전트별 작업 배정표를 먼저 작성**하고 사용자에게 보고 후 진행.

| 에이전트 | 담당 영역 |
|---------|----------|
| **@orchestrator** | 작업 분배, 조율, 통합 |
| **@frontend-agent** | `app/templates/`, `app/static/` |
| **@backend-agent** | `app/api/`, `app/models/`, `app/services/` |
| **@explorer-agent** | `blogauto_new/` (읽기 전용, Gemini CLI) |
| **@reviewer-agent** | `tests/`, `docs/`, 코드 리뷰 |

**상세 가이드**: `docs/claude/AGENTS.md` 참조

---

## 필수 규칙 (MUST)

### 코드 품질
- **타입 힌트**: 필수
- **Docstring**: 필수
- **에러 처리 + 로깅**: 필수
- **커밋 메시지**: Conventional Commits (`feat/fix/docs/test/refactor/chore`)

### Git Workflow
- 파일별 개별 커밋
- 커밋 메시지: `<type>(<scope>): <subject>` (한국어)

### 배포 전 체크리스트
```
- [ ] 모든 파일 < 500줄, 함수 < 50줄
- [ ] 타입 힌트 + Docstring 작성
- [ ] 테스트 통과
- [ ] .env.required 업데이트 (새 환경변수 시)
```

---

## 기술 스택 (요약)

| 영역 | 기술 |
|------|------|
| Backend | FastAPI, SQLAlchemy, PostgreSQL/SQLite |
| Frontend | Alpine.js, Jinja2, Tailwind CSS |
| Queue | Redis, APScheduler |
| Container | Docker, docker-compose |

**상세 가이드**: `docs/claude/DEVELOPMENT.md` 참조

---

## Docker 명령어 (빠른 참조)

```bash
# 로컬 테스트
cd ~/blogauto_v2/services/republish
docker-compose down && docker-compose build --no-cache && docker-compose up -d

# 로그 확인
docker-compose logs app --tail 30
```

---

## 프로젝트 구조 (요약)

```
blogauto_v2/services/republish/     # 작업 디렉토리
├── app/                            # 애플리케이션 코드
│   ├── api/, models/, services/    # @backend-agent
│   ├── templates/, static/         # @frontend-agent
│   └── scheduler/                  # 스케줄러
├── tests/                          # @reviewer-agent
├── alembic/                        # DB 마이그레이션
├── .env                            # 환경변수 (git 미추적)
└── .env.required                   # 필수 변수 목록 (git 추적)
```

**상세 구조**: `docs/claude/PROJECT_STRUCTURE.md` 참조

---

## 핵심 원칙

```
1. 복잡한 작업은 /multi-agent 사용
2. 에이전트별 작업 배정표 먼저 작성
3. Flowchart first, code later
4. Files < 500줄, Functions < 50줄
5. .env 수정 시 .env.required도 업데이트
6. .env 파일은 롤백 시에도 절대 수정 금지
7. NEVER modify blogauto_new/
8. NEVER start servers
9. ALWAYS use type hints and docstrings
10. 모든 소통은 한국어
```

---

## 상세 문서 참조

| 문서 | 내용 |
|------|------|
| `docs/claude/AGENTS.md` | 멀티 에이전트 시스템, 통신 프로토콜, 워크플로우 |
| `docs/claude/DEVELOPMENT.md` | 개발 프로세스, 기술 스택, 코드 표준, 배포 |
| `docs/claude/PROJECT_STRUCTURE.md` | 프로젝트 디렉토리 구조 상세 |
| `docs/plans/` | 작업 계획서 |
| `docs/flowcharts/` | Mermaid 순서도 |

---

**Last Updated**: 2026-04-07 | **Version**: v4.0.0
