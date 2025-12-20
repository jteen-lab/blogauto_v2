# BlogAuto V2 - Phase 1: 인증 시스템

> **구현 완료**: 기반 시스템 + 인증 + 파일 기반 로깅
> **버전**: v2.0.0
> **날짜**: 2025-12-21

## 🎯 Phase 1 개요

BlogAuto V2의 첫 번째 단계로 **기반 시스템**과 **인증 시스템**, 그리고 **파일 기반 로깅**을 구현했습니다.

### ✅ 구현된 기능

- **🔐 JWT 기반 인증 시스템**: 회원가입, 로그인, 로그아웃
- **📝 파일 기반 로깅**: app.log, auth.log, error.log 분리 관리
- **🛡️ 보안 시스템**: bcrypt 해싱, Fernet 암호화, 토큰 블랙리스트
- **🎨 웹 UI**: 반응형 로그인/대시보드 페이지 (Tailwind CSS + Alpine.js)
- **📊 데이터베이스**: SQLAlchemy async + PostgreSQL 지원
- **🧪 테스트**: 포괄적인 단위 테스트 포함

## 📐 시스템 아키텍처

```mermaid
graph TD
    User[사용자] --> Login[로그인 페이지]
    Login --> Auth[인증 API]
    Auth --> JWT[JWT 토큰]
    JWT --> Dashboard[대시보드]

    Auth --> DB[(PostgreSQL)]
    Auth --> Log[로그 파일]

    subgraph "로그 파일"
        AppLog[app.log]
        AuthLog[auth.log]
        ErrorLog[error.log]
    end

    subgraph "보안 계층"
        BCrypt[bcrypt 해싱]
        Fernet[Fernet 암호화]
        TokenMgmt[토큰 관리]
    end
```

## 📁 프로젝트 구조

```
services/republish/
├── app/
│   ├── core/                   # 핵심 시스템
│   │   ├── config.py          # 환경 설정
│   │   ├── database.py        # DB 연결 관리
│   │   ├── logger.py          # 로깅 시스템
│   │   ├── password.py        # 비밀번호 해싱
│   │   ├── jwt.py            # JWT 토큰 관리
│   │   └── security.py       # 암호화 유틸
│   │
│   ├── models/                # 데이터 모델
│   │   └── user.py           # 사용자 모델
│   │
│   ├── schemas/               # API 스키마
│   │   └── auth.py           # 인증 스키마
│   │
│   ├── services/              # 비즈니스 로직
│   │   └── auth_service.py   # 인증 서비스
│   │
│   ├── routers/               # API 라우터
│   │   └── auth.py           # 인증 엔드포인트
│   │
│   ├── middleware/            # 미들웨어
│   │   └── logging_middleware.py  # 요청 로깅
│   │
│   ├── templates/             # HTML 템플릿
│   │   ├── base.html         # 기본 레이아웃
│   │   ├── login.html        # 로그인 페이지
│   │   ├── dashboard.html    # 대시보드
│   │   └── error.html        # 에러 페이지
│   │
│   └── main.py               # FastAPI 애플리케이션
│
├── logs/                     # 📝 로그 파일 저장소
│   ├── app.log              # 일반 애플리케이션 로그
│   ├── auth.log             # 인증 관련 로그
│   ├── error.log            # 에러 전용 로그
│   └── request.log          # HTTP 요청 로그
│
├── tests/                   # 테스트 코드
│   └── test_auth.py         # 인증 시스템 테스트
│
├── requirements.txt         # 패키지 의존성
├── .env.example            # 환경변수 예시
└── README.md               # 이 파일
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
# 환경변수 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env
```

**중요한 환경변수:**
```bash
SECRET_KEY="your-super-secret-key-32-chars-minimum"
DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/blogauto_v2"
ENCRYPTION_KEY=""  # 선택적 (API 키 암호화용)
```

### 3. 데이터베이스 설정

```bash
# PostgreSQL 데이터베이스 생성
createdb blogauto_v2

# 또는 SQLite 사용 (개발환경)
# DATABASE_URL="sqlite+aiosqlite:///./blogauto_v2.db"
```

### 4. 애플리케이션 실행

```bash
# 개발 서버 시작 (로그 파일로 출력됨)
cd services/republish
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 웹 브라우저 접속

```bash
# 브라우저에서 접속
http://localhost:8000

# API 문서 (개발환경에서만)
http://localhost:8000/docs
```

## 📝 로깅 시스템

### 로그 파일 구조

| 파일 | 용도 | 포맷 |
|------|------|------|
| `logs/app.log` | 일반 애플리케이션 로그 | INFO, DEBUG 메시지 |
| `logs/auth.log` | 인증 관련 전용 로그 | 로그인/로그아웃 기록 |
| `logs/error.log` | 에러 전용 로그 | ERROR, CRITICAL 메시지 |
| `logs/request.log` | HTTP 요청 로그 | 모든 API 요청/응답 |

### 로그 포맷

```
2025-12-21 10:30:45 | INFO | auth_service | login_attempt | user=test@email.com | ip=192.168.1.1
```

### 로그 확인

```bash
# 실시간 로그 모니터링
tail -f logs/app.log
tail -f logs/auth.log
tail -f logs/error.log

# 특정 키워드 검색
grep "로그인" logs/auth.log
grep "ERROR" logs/error.log
```

## 🔐 API 사용 방법

### 1. 회원가입

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123",
    "full_name": "홍길동"
  }'
```

### 2. 로그인

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123"
  }'
```

### 3. 사용자 정보 조회

```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 4. 로그아웃

```bash
curl -X POST "http://localhost:8000/api/v1/auth/logout" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## 🧪 테스트 실행

```bash
# 전체 테스트 실행
pytest tests/ -v

# 특정 테스트 파일
pytest tests/test_auth.py -v

# 커버리지 포함 테스트
pytest tests/ --cov=app --cov-report=html
```

### 테스트 커버리지

- ✅ 사용자 회원가입 (정상/중복이메일/약한비밀번호)
- ✅ 사용자 로그인 (정상/잘못된이메일/잘못된비밀번호)
- ✅ JWT 토큰 검증 (정상/만료/잘못된토큰)
- ✅ 사용자 정보 조회
- ✅ 로그아웃 및 토큰 무효화
- ✅ 비밀번호 변경

## 🔒 보안 기능

### 1. 비밀번호 보안

- **bcrypt 해싱**: 12 라운드 솔트 해싱
- **강도 검증**: 대소문자, 숫자, 8자 이상 필수
- **타이밍 공격 방지**: 일정한 검증 시간 유지

### 2. JWT 토큰 보안

- **HS256 알고리즘**: HMAC SHA-256 서명
- **만료 시간 관리**: 7일 기본 만료 시간
- **토큰 블랙리스트**: 로그아웃된 토큰 무효화
- **HttpOnly 쿠키**: XSS 공격 방지

### 3. 데이터 암호화

- **Fernet 암호화**: 대칭키 기반 API 키 암호화
- **환경변수 보호**: 민감한 정보 별도 관리

## 🛠️ 개발 도구

### 코드 포맷팅

```bash
# 코드 포맷팅
black app/
isort app/

# 린트 검사
flake8 app/
```

### 파일 크기 확인

```bash
# 모든 Python 파일 크기 확인 (500줄 제한)
find app/ -name "*.py" -exec wc -l {} + | sort -n

# 특정 파일 크기
wc -l app/services/auth_service.py
```

## 📊 성능 최적화

### 1. 데이터베이스

- **비동기 SQLAlchemy**: 높은 동시성 처리
- **연결 풀링**: 5개 기본 연결, 10개 오버플로우
- **쿼리 최적화**: 인덱스 활용 및 N+1 방지

### 2. 로깅 최적화

- **로그 로테이션**: 10MB 초과시 자동 로테이션
- **비동기 로깅**: 블로킹 없는 로그 기록
- **레벨별 분리**: 필요한 로그만 기록

## 🔜 다음 단계 (Phase 2)

### 예정된 기능

1. **재발행 서비스**: 24시간 자동 블로그 포스트 재발행
2. **제목 관리 시스템**: 블로그 제목 수집 및 관리
3. **워드프레스 연동**: API 기반 포스트 발행
4. **스케줄링**: APScheduler 기반 작업 관리

### 예상 구조

```
services/
├── republish/     # ✅ Phase 1 (완료)
├── title_mgmt/    # 🔄 Phase 2 (예정)
├── content_gen/   # 🔄 Phase 3 (예정)
└── shared/        # 🔄 공통 라이브러리
```

## 🐛 문제 해결

### 일반적인 문제

**1. 데이터베이스 연결 실패**
```bash
# PostgreSQL 서비스 확인
sudo systemctl status postgresql

# 연결 테스트
psql -h localhost -U postgres -d blogauto_v2
```

**2. 로그 파일이 생성되지 않음**
```bash
# 디렉토리 권한 확인
ls -la logs/

# 디렉토리 생성
mkdir -p logs
chmod 755 logs
```

**3. JWT 토큰 오류**
```bash
# SECRET_KEY 확인
grep SECRET_KEY .env

# 최소 32자 이상인지 확인
```

### 로그 레벨별 디버깅

```bash
# DEBUG 로그 확인
grep "DEBUG" logs/app.log

# ERROR 로그만 확인
grep "ERROR" logs/error.log

# 특정 사용자 인증 로그
grep "user=test@example.com" logs/auth.log
```

## 📞 지원

### 문의사항

- **이슈 리포팅**: GitHub Issues
- **기능 제안**: GitHub Discussions
- **보안 취약점**: 비공개 이메일로 연락

### 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다.

---

## ✨ 특징 요약

> **🎯 안정적인 기반 시스템**: FastAPI + SQLAlchemy + PostgreSQL
> **🔐 강화된 보안**: bcrypt + JWT + Fernet 암호화
> **📝 체계적인 로깅**: 파일 분리 + 로테이션 + 구조화
> **🎨 현대적인 UI**: Tailwind CSS + Alpine.js
> **🧪 포괄적인 테스트**: 단위 테스트 + 통합 테스트
> **📏 코드 품질**: 500줄 제한 + 타입 힌트 + Docstring

**BlogAuto V2 Phase 1이 성공적으로 완료되었습니다! 🚀**