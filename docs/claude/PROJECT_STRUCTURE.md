# 프로젝트 구조 상세

> CLAUDE.md에서 참조하는 상세 문서입니다.

## 디렉토리 구조 및 에이전트 담당 영역

```
blogauto_new/                    # LEGACY - DO NOT MODIFY
├── core/                        # @explorer-agent만 읽기 가능
├── static/
└── ...

blogauto_v2/                     # NEW PROJECT - WORK HERE
├── services/republish/          # 현재 작업 중인 서비스
│   ├── app/
│   │   ├── api/                 # @backend-agent 담당
│   │   ├── models/              # @backend-agent 담당
│   │   ├── services/            # @backend-agent 담당
│   │   ├── schemas/             # @backend-agent 담당
│   │   ├── templates/           # @frontend-agent 담당
│   │   └── static/              # @frontend-agent 담당
│   │
│   ├── tests/                   # @reviewer-agent 담당
│   ├── docs/                    # @reviewer-agent 담당
│   ├── .env                     # git 미추적 (개인정보)
│   └── .env.required            # git 추적 (필수 변수 목록)
│
├── docs/
│   ├── flowcharts/              # Mermaid 순서도
│   ├── plans/                   # 작업 계획서
│   └── claude/                  # Claude 상세 가이드
│       ├── AGENTS.md
│       ├── DEVELOPMENT.md
│       └── PROJECT_STRUCTURE.md
│
├── CLAUDE.md                    # 핵심 지침 (150줄)
└── README.md
```
