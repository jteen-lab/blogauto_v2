# CLAUDE.md

> **BlogAuto v2** | **버전**: v4.1.0 | **날짜**: 2026-05-26

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

## 운영 모드 워크플로우 (2026-05-26 추가)

> 현재 옛 오라클 서버(144.24.82.130, E2.1.Micro)에서 **실 운영 중**. 사용자는 실제 블로그에 글/이미지 생성·발행하면서 운영 중 문제를 발견·보고한다. A1.Flex 마이그레이션은 capacity 확보 대기 중.

### 수정 요청 처리 표준 절차 (사용자 개입 없음, 직접 마무리)

사용자가 "서버에서 X가 안 된다", "이 오류 고쳐줘" 등 운영 중 문제를 보고하면:

1. **로컬에서 수정** — 서버 코드 직접 수정 금지(회귀 위험·SHA 불일치 발생). 모든 수정은 `~/blogauto_v2`(로컬)에서만.
2. **로컬 자체 테스트** — 데이터 영향이 큰 변경(마이그레이션, 모델 변경, 데이터 마이그레이션 스크립트 등)은 로컬에서 먼저 검증. UI/회귀 fix는 서버 배포 후 사용자 검증으로 갈음 가능.
3. **파일별 개별 `git commit`** + **`git push origin main`** — push가 GitHub Actions를 트리거해 `ghcr.io/jteen-lab/blogauto:stable` 이미지를 자동 빌드한다.
4. **GitHub Actions 빌드 완료 대기** — 약 3~7분. 빌드 완료 전에는 서버 pull 무의미.
5. **서버에 데이터 보존 업데이트 배포** — SSH 접속 후 다음 패턴:
   ```bash
   ssh -i ~/.ssh/blogauto-oracle.key ubuntu@144.24.82.130
   cd ~/blogauto_v2/services/republish     # 또는 실제 배포 디렉토리
   sudo docker compose pull                 # 새 이미지만 받아옴
   sudo docker compose up -d                # 컨테이너만 교체 (volume 보존)
   sudo docker image prune -f               # 교체로 dangling된 옛 이미지 정리(안전: 태그없는 미사용만)
   ```
   > 옛 `:stable` 이미지는 교체 시 dangling(태그없음)으로 남아 누적됨(배포당 ~1.7GB).
   > `docker image prune -f`는 dangling 이미지만 삭제하며 volume/실행이미지/DB는 건드리지 않음.
   > 서버에 주간 cron(`0 4 * * 0 docker image prune -f`)도 설치돼 있으나, 배포마다 함께 정리 권장.
   > ⚠️ `docker system prune -a --volumes` 절대 금지(볼륨 삭제=데이터 손실).
6. **검증** — 두 SHA가 일치하는지 확인:
   - 로컬: `git rev-parse origin/main`
   - 서버: `sudo docker inspect blogauto-app-1 --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'`
   - 두 값이 같아야 배포 성공.
7. **사용자에게 결과 보고** — 무엇을 고쳤는지, 서버 배포·검증까지 완료됐는지 명시.

### 절대 금지 (데이터 손상 방지)

- ❌ `docker compose down -v` — `-v`는 named volume 삭제. PostgreSQL DB / 생성 이미지 / 사용자 업로드 데이터가 날아간다.
- ❌ `docker volume rm`, `docker system prune --volumes` — 같은 이유로 금지.
- ❌ 서버에서 직접 코드 편집 (`vim`, `nano` 등) — 로컬과 SHA 불일치 발생, 다음 배포 시 덮어써짐.
- ❌ 서버에서 `alembic downgrade` — 데이터 손실 가능. 마이그레이션은 항상 upgrade 방향.

### 마이그레이션 동반 배포

새 alembic 마이그레이션이 포함된 경우 서버 배포 시 자동 실행되는지 확인. 자동 실행 안 되면 5번 절차에 추가:
```bash
sudo docker compose exec app alembic upgrade head
```

### 불일치 발생 시 (`git status`에 미커밋 변경, push 안 된 커밋 등)

서버에 반영 안 되어 사용자가 보고한 문제가 안 고쳐진 것처럼 보일 수 있다. 사용자 보고를 받으면 항상 먼저:
1. `git status` — 미커밋 변경 있는지
2. `git log origin/main..HEAD` — push 안 된 로컬 커밋 있는지
3. 서버 SHA — 운영 중인 실제 코드 버전

세 값이 모두 일치하는 게 정상 상태.

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
- **작업 후 반드시 커밋** — 코드 수정이든 문서(작업계획서 등) 작성이든, 한 작업이 끝나면 곧바로 커밋한다. 미완성이면 `wip:` 로 임시 커밋을 남긴다. **커밋하지 않은 작업은 다른 세션(체셔캣 포함)이 이어받지 못한다** — 파일로는 보여도 "마지막 작업"으로 인식되지 않는다.

### 배포 전 체크리스트
```
- [ ] 모든 파일 < 500줄, 함수 < 50줄
- [ ] 타입 힌트 + Docstring 작성
- [ ] 테스트 통과
- [ ] .env.required 업데이트 (새 환경변수 시)
- [ ] 런타임 의존 데이터 파일은 git 추적됨 (`git check-ignore` 출력 없음) — 로컬 볼륨마운트로만 동작 ≠ 서버 이미지 포함
- [ ] 배포 후 이미지 내 필수 자산 존재 확인 (`docker exec <app> ls <경로>`)
```

> **로컬-서버 비대칭 주의**: 로컬은 볼륨마운트, 서버는 빌드 이미지만 사용. "로컬에서 됨"이 서버를 보장하지 않음. 상세 §`docs/claude/REGRESSION_PREVENTION.md` 7장.

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
11. 운영 수정은 로컬 → push → 서버 데이터 보존 배포까지 직접 마무리
12. 수정 후 로컬 HEAD = origin/main = 서버 image revision SHA (3값 동일)
13. 작업(코드·문서) 끝나면 반드시 커밋 — 미완성은 wip 커밋. 커밋 안 하면 다른 세션이 못 이어받음
```

---

## 상세 문서 참조

| 문서 | 내용 |
|------|------|
| `docs/claude/AGENTS.md` | 멀티 에이전트 시스템, 통신 프로토콜, 워크플로우 |
| `docs/claude/DEVELOPMENT.md` | 개발 프로세스, 기술 스택, 코드 표준, 배포 |
| `docs/claude/PROJECT_STRUCTURE.md` | 프로젝트 디렉토리 구조 상세 |
| `docs/claude/REGRESSION_PREVENTION.md` | **회귀 방지 규칙**, 수정 시 영향 범위 분석, 테스트 필수 항목 |
| `docs/plans/` | 작업 계획서 |
| `docs/flowcharts/` | Mermaid 순서도 |

---

**Last Updated**: 2026-05-26 | **Version**: v4.1.0
