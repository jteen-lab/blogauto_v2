# 자동 업데이트 흐름

> **버전**: v1.0 / **작성일**: 2026-05-13 / **단계**: Phase A-1

---

## 1. 전체 흐름

```mermaid
flowchart LR
    Dev[개발자: git push] --> GHA[GitHub Actions]
    GHA --> Test[테스트 실행]
    Test --> Build[Docker 이미지 빌드]
    Build --> Push[ghcr.io 이미지 push]
    Push --> Tag[태그 :stable / :latest]

    Tag --> User1[사용자 A 서버]
    Tag --> User2[사용자 B 서버]
    Tag --> User3[사용자 C 서버]

    User1 --> WT[Watchtower 1시간마다 폴링]
    User2 --> WT
    User3 --> WT
```

---

## 2. 개발자 측 - GitHub Actions 빌드/배포

```mermaid
flowchart TD
    Push[git push main] --> Workflow{워크플로 분기}
    Workflow --> Lint[린트/타입체크]
    Workflow --> UnitTest[단위 테스트]
    Workflow --> IntegTest[통합 테스트]

    Lint --> Gate{모두 통과?}
    UnitTest --> Gate
    IntegTest --> Gate

    Gate -->|No| Fail[빌드 실패 알림<br/>+ Slack/Discord 알림]
    Gate -->|Yes| Build[Docker 이미지 빌드<br/>multi-arch: amd64/arm64]

    Build --> Tag1{브랜치}
    Tag1 -->|main| Stable[ghcr.io/jteen-lab/blogauto:stable<br/>+ :latest<br/>+ :v1.2.3 시맨틱 버전]
    Tag1 -->|develop| Beta[ghcr.io/jteen-lab/blogauto:beta]

    Stable --> Notify[릴리스 노트 자동 생성]
    Beta --> Notify
    Notify --> Done([배포 완료 / 사용자 서버 대기])
```

---

## 3. 사용자 서버 측 - Watchtower 자동 업데이트

```mermaid
flowchart TD
    Timer[Watchtower: 1시간 타이머] --> Check[ghcr.io 이미지 digest 비교]
    Check --> Same{변경?}

    Same -->|No| Wait[다음 타이머까지 대기]
    Wait --> Timer

    Same -->|Yes| Pull[새 이미지 pull]
    Pull --> PreCheck[업데이트 전 자동 작업]

    PreCheck --> Backup1[.env 백업: .env.bak.YYYYMMDD_HHMMSS]
    Backup1 --> Backup2[DB 자동 백업: postgres pg_dump]
    Backup2 --> Maintenance[유지보수 페이지 ON<br/>nginx returns 503]

    Maintenance --> Stop[기존 app 컨테이너 정지]
    Stop --> Migration[새 컨테이너 시작<br/>alembic upgrade head 자동 실행]
    Migration --> HealthCheck[Health Check 60초 대기]

    HealthCheck --> Health{정상?}
    Health -->|Yes| Success[유지보수 페이지 OFF<br/>이전 컨테이너 제거<br/>이전 이미지 7일간 보존]
    Health -->|No| Rollback[자동 롤백<br/>이전 이미지로 복귀<br/>관리자 알림]

    Success --> Log[업데이트 로그 기록]
    Rollback --> Log
    Log --> Notify2[사용자 대시보드 알림<br/>'v1.2.3 업데이트 완료']
    Notify2 --> Wait
```

---

## 4. 자동 업데이트 안전장치 (Defense in Depth)

| 장치 | 동작 | 트리거 |
|------|------|--------|
| **이미지 digest 검증** | pull한 이미지 SHA256이 ghcr.io의 공식 digest와 일치하는지 | 변조 차단 |
| **백업 자동화** | `.env` + DB 덤프를 update 전 자동 보관 | 매 업데이트 |
| **유지보수 페이지** | 업데이트 중 사용자에게 "잠시 후 다시 시도" | 컨테이너 교체 동안 |
| **Health Check** | `/health` 엔드포인트 60초 대기 | 새 컨테이너 시작 후 |
| **자동 롤백** | health 실패 시 즉시 이전 이미지 복귀 | health check 실패 |
| **이전 이미지 보존** | 최근 3개 버전을 로컬 디스크에 유지 | 항상 |
| **관리자 알림** | 롤백 발생 시 Slack/이메일로 즉시 통지 | 롤백 발생 |
| **수동 일시정지** | `blogauto pause-updates` 명령으로 자동 업데이트 중단 가능 | 사용자 선택 |

---

## 5. 롤백 흐름 (자동/수동)

```mermaid
flowchart TD
    Trigger{롤백 트리거} --> Auto[자동: Health check 실패]
    Trigger --> Manual[수동: blogauto rollback]

    Auto --> Reason[로그에 사유 기록]
    Manual --> Reason

    Reason --> Stop[현재 컨테이너 정지]
    Stop --> SelectImg{롤백 대상 선택}

    SelectImg --> PrevAuto[자동: 직전 이미지]
    SelectImg --> PrevManual[수동: 사용자가 버전 선택<br/>최근 3개 중]

    PrevAuto --> RestoreEnv[.env 복원: .env.bak.* 중 직전]
    PrevManual --> RestoreEnv

    RestoreEnv --> RestoreDB{DB 스키마 호환?}
    RestoreDB -->|No| MigrateBack[alembic downgrade]
    RestoreDB -->|Yes| Skip
    MigrateBack --> Start
    Skip --> Start[이전 이미지 컨테이너 시작]

    Start --> Verify[Health Check 재확인]
    Verify --> Done([롤백 완료])
```

---

## 6. 베타/정식 채널 분리 (사용자 30명+에서 활성화)

```mermaid
flowchart LR
    PR[Pull Request 머지] --> Branch{브랜치}
    Branch -->|develop| BetaImg[ghcr.io/.../blogauto:beta]
    Branch -->|main| StableImg[ghcr.io/.../blogauto:stable]

    BetaImg --> BetaUsers[베타 사용자<br/>WATCHTOWER_REPO_BLACKLIST 미사용]
    StableImg --> Allusers[모든 사용자]

    BetaUsers --> Feedback[베타 사용자 피드백]
    Feedback --> Merge{문제 없음?}
    Merge -->|Yes| Promote[develop → main 머지]
    Promote --> StableImg
    Merge -->|No| Hotfix[hotfix → develop]
```

채널 전환은 `.env`에서 한 줄:
```env
# 안정 채널 (기본)
BLOGAUTO_IMAGE_TAG=stable

# 베타 채널 (베타 테스터만)
BLOGAUTO_IMAGE_TAG=beta
```

---

## 7. 업데이트 주기 옵션

| 주기 | 적합한 상황 | 환경변수 |
|------|----------|---------|
| 1시간 (권장) | 활발한 개발 단계, 빠른 버그 수정 반영 | `WATCHTOWER_POLL_INTERVAL=3600` |
| 6시간 | 균형 (안정성 + 비교적 빠름) | `WATCHTOWER_POLL_INTERVAL=21600` |
| 24시간 | 안정 운영, 큰 변경 적음 | `WATCHTOWER_POLL_INTERVAL=86400` |
| 수동 | 자동 업데이트 끄기 | `WATCHTOWER_DISABLE=true` |

---

**문서 끝**.
