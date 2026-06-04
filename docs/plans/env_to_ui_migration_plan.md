# .env → UI 설정 마이그레이션 계획서

> **버전**: v1.0.0 | **작성일**: 2026-04-22
> **목표**: 사용자가 `.env` 파일을 직접 수정하지 않고, UI에서 모든 설정을 관리할 수 있도록 전환

---

## 1. 현재 상태

### .env에 저장되는 변수 분류

| 분류 | 변수 | 현재 위치 | 사용자 변경 필요 |
|------|------|-----------|-----------------|
| 서버 보안 | `SECRET_KEY`, `ENCRYPTION_KEY`, `JWT_SECRET` | .env | 없음 (배포 시 1회) |
| DB 접속 | `POSTGRES_*`, `DATABASE_URL` | .env | 없음 (Docker 연동) |
| 외부 서비스 | `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET` | .env | **있음** |
| 시스템 플래그 | `USE_CELERY_*` (4개) | .env | 운영자만 |
| AI 제한 | `RATELIMIT_*` (6개) | .env | 운영자만 |

### 기존 UI 설정 (user_settings 테이블)

이미 DB에 저장되는 항목:
- AI API 키 (OpenAI, Claude, Gemini)
- Google Ads/Keyword Planner OAuth 정보
- Naver 검색광고/데이터랩/검색 API 정보
- Blogger 시간당 발행 제한

---

## 2. Phase별 구현 계획

### Phase 1: Blogger OAuth 자격증명 → UI 이동

> **목표**: `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`을 .env에서 제거하고 UI 설정에서 입력/DB 저장

#### 1-1. DB 모델 수정

**변경 대상**: `app/models/user_settings.py`

**추가 컬럼**:
```python
blogger_client_id = Column(String(255), nullable=True, comment="Google Blogger OAuth Client ID")
blogger_client_secret = Column(String(255), nullable=True, comment="Google Blogger OAuth Client Secret")
```

**DB 마이그레이션**: alembic 마이그레이션 파일 생성

#### 1-2. API 수정

**변경 대상**: `app/routers/settings.py`

- PUT `/settings` 엔드포인트에 `blogger_client_id`, `blogger_client_secret` 처리 추가
- 기존 API 키 저장 패턴과 동일 (마스킹 처리, 빈 문자열=삭제)

#### 1-3. OAuth 헬퍼 수정

**변경 대상**: `app/services/publishing/google_oauth_helper.py`

**조회 우선순위 변경**:
```
현재: settings(config.py) → 환경변수 → .env 파일
변경: DB(user_settings) → 환경변수 → .env 파일 (하위 호환)
```

```python
async def get_google_oauth_credentials() -> Tuple[str, str]:
    # 1순위: DB (user_settings)
    from app.core.database import db_manager
    async with db_manager.get_session() as db:
        settings = await db.get(UserSettings, ...)
        if settings and settings.blogger_client_id:
            return settings.blogger_client_id, settings.blogger_client_secret

    # 2순위: 환경변수 (.env 폴백)
    cid = os.environ.get("BLOGGER_CLIENT_ID", "")
    cse = os.environ.get("BLOGGER_CLIENT_SECRET", "")
    return cid, cse
```

**주의**: 이 함수는 Celery 워커에서도 호출됨. async 컨텍스트 처리 필요.

#### 1-4. UI 수정

**변경 대상**: `app/templates/settings/modal.html`

**API 설정 탭 내 "Google Blogger" 섹션에 추가**:
- OAuth Client ID 입력 필드
- OAuth Client Secret 입력 필드 (비밀번호 타입 + 토글)
- 연결 테스트 버튼 (refresh token 교환 테스트)

**변경 대상**: `app/static/js/settings.js`

- `form` 객체에 `blogger_client_id`, `blogger_client_secret` 추가
- `saveSettings()`에 해당 필드 포함
- `testBloggerConnection()` 메서드 추가

#### 1-5. .env 변경

- `BLOGGER_CLIENT_ID`, `BLOGGER_CLIENT_SECRET`을 `.env.required`에서 선택사항으로 격하 (주석 처리)
- 기존 .env에 값이 있으면 폴백으로 계속 동작 (하위 호환)

#### Phase 1 완료 기준
- [ ] UI 설정에서 Blogger Client ID/Secret 입력 가능
- [ ] DB에 저장된 값으로 토큰 교환 성공
- [ ] .env에 값 없어도 정상 동작
- [ ] .env에 값 있으면 폴백으로 동작 (하위 호환)

---

### Phase 2: 시스템 설정 (USE_CELERY_*, RATELIMIT_*) → DB + 관리자 UI

> **목표**: 시스템 운영 설정을 DB에 저장하고, 관리자 UI에서 Docker 재시작 없이 변경 가능

#### 2-1. system_settings 테이블 생성

**신규 파일**: `app/models/system_settings.py`

```python
class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, bool, int, float
    category = Column(String(50), nullable=False)  # celery, ratelimit, system
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

**Key-Value 방식 채택 이유**:
- 설정 항목이 자주 추가/삭제될 수 있음
- 카테고리별 그룹화로 UI에서 섹션 구분 가능
- 컬럼 추가 없이 새 설정 추가 가능

**초기 데이터**:

| key | value | value_type | category | description |
|-----|-------|------------|----------|-------------|
| `use_celery_generation` | `true` | bool | celery | 글 생성 워커 사용 |
| `use_celery_publish` | `true` | bool | celery | 발행 워커 사용 |
| `use_celery_image` | `true` | bool | celery | 이미지 생성 워커 사용 |
| `use_celery_utility` | `true` | bool | celery | 유틸리티 워커 사용 |
| `ratelimit_openai_rpm` | `60` | int | ratelimit | OpenAI 분당 요청 제한 |
| `ratelimit_openai_tpm` | `90000` | int | ratelimit | OpenAI 분당 토큰 제한 |
| `ratelimit_anthropic_rpm` | `50` | int | ratelimit | Anthropic 분당 요청 제한 |
| `ratelimit_anthropic_tpm` | `80000` | int | ratelimit | Anthropic 분당 토큰 제한 |
| `ratelimit_google_rpm` | `60` | int | ratelimit | Google 분당 요청 제한 |
| `ratelimit_google_tpm` | `120000` | int | ratelimit | Google 분당 토큰 제한 |

#### 2-2. 설정 조회 서비스

**신규 파일**: `app/services/system_settings_service.py`

```python
class SystemSettingsService:
    """시스템 설정 조회 서비스 (캐시 적용)"""

    _cache: dict = {}
    _cache_ttl: int = 60  # 60초 캐시

    @classmethod
    async def get(cls, key: str, default=None):
        """설정값 조회 (캐시 → DB → .env 폴백)"""

    @classmethod
    async def get_bool(cls, key: str, default: bool = False) -> bool:
        """bool 설정값 조회"""

    @classmethod
    async def get_int(cls, key: str, default: int = 0) -> int:
        """int 설정값 조회"""
```

**조회 우선순위**:
```
1순위: 메모리 캐시 (60초 TTL)
2순위: DB (system_settings 테이블)
3순위: .env 환경변수 (하위 호환)
4순위: 기본값
```

#### 2-3. 기존 코드 수정

**변경 대상**: `app/core/config.py`의 `use_celery_*` 사용처

```python
# 현재
from app.core.config import settings
if settings.use_celery_generation:

# 변경
from app.services.system_settings_service import SystemSettingsService
if await SystemSettingsService.get_bool("use_celery_generation", default=False):
```

**영향 범위**:
- `app/routers/flows_execute.py` (6곳)
- `app/scheduler/flow_scheduler.py` (6곳)
- `app/core/rate_limiter.py` (RATELIMIT_* 참조)

#### 2-4. 관리자 UI

**변경 대상**: 설정 모달에 "시스템 설정" 탭 추가

**Celery 설정 섹션**:
- 글 생성 워커: ON/OFF 토글
- 발행 워커: ON/OFF 토글
- 이미지 생성 워커: ON/OFF 토글
- 유틸리티 워커: ON/OFF 토글

**Rate Limit 설정 섹션**:
- OpenAI: RPM / TPM 입력
- Anthropic: RPM / TPM 입력
- Google: RPM / TPM 입력

**변경 즉시 반영** (Docker 재시작 불필요):
- 캐시 TTL(60초) 후 자동 반영
- 또는 "적용" 버튼 클릭 시 캐시 즉시 무효화

#### 2-5. .env 변경

- `USE_CELERY_*`를 `.env.required`에서 선택사항으로 격하
- `RATELIMIT_*`은 이미 선택사항 (변경 없음)
- DB에 값이 없을 때만 .env 폴백 동작

#### Phase 2 완료 기준
- [ ] system_settings 테이블 생성 및 초기 데이터 삽입
- [ ] 관리자 UI에서 Celery ON/OFF 토글 동작
- [ ] 관리자 UI에서 Rate Limit 값 변경 동작
- [ ] Docker 재시작 없이 설정 변경 즉시 반영
- [ ] .env에 값 없어도 DB 기본값으로 동작

---

### Phase 3: 배포 스크립트 자동화

> **목표**: 서버 배포 시 사용자가 `.env`를 직접 편집하지 않고, 스크립트 1줄로 완료

#### 3-1. 배포 스크립트 생성

**신규 파일**: `deploy.sh` (프로젝트 루트)

```bash
#!/bin/bash
# BlogAuto V2 배포 스크립트
# 사용법: ./deploy.sh

echo "🚀 BlogAuto V2 배포를 시작합니다..."

# 1. .env 파일 자동 생성 (없을 때만)
if [ ! -f services/republish/.env ]; then
    echo "📝 환경 설정 파일을 자동 생성합니다..."

    SECRET_KEY=$(openssl rand -hex 32)
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    JWT_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)

    cat > services/republish/.env << EOF
# BlogAuto V2 환경 설정 (자동 생성됨)
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}
POSTGRES_USER=blogauto
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=blogauto_v2
DATABASE_URL=postgresql://blogauto:${DB_PASSWORD}@db:5432/blogauto_v2
EOF
    echo "✅ 환경 설정 파일 생성 완료"
else
    echo "ℹ️ 기존 환경 설정 파일 사용"
fi

# 2. Docker 빌드 및 시작
echo "🐳 Docker 컨테이너를 시작합니다..."
cd services/republish
docker-compose up -d --build

# 3. DB 마이그레이션
echo "🗄️ 데이터베이스 마이그레이션..."
docker-compose exec -T app alembic upgrade head

# 4. 초기 관리자 계정 생성
echo "👤 초기 관리자 계정 생성..."
docker-compose exec -T app python3 -c "
from app.core.database import db_manager
# 초기 사용자 생성 로직
"

echo ""
echo "✅ BlogAuto V2 배포가 완료되었습니다!"
echo "🌐 접속 주소: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "⚠️ Blogger 사용 시: 설정 > API 설정에서 Google OAuth 정보를 입력하세요"
```

#### 3-2. .env 최소화

**Phase 1~2 완료 후 .env에 남는 변수**:

| 변수 | 용도 | 생성 방법 |
|------|------|-----------|
| `SECRET_KEY` | 앱 보안 키 | 자동 생성 |
| `ENCRYPTION_KEY` | DB 암호화 키 | 자동 생성 |
| `JWT_SECRET` | JWT 서명 키 | 자동 생성 |
| `POSTGRES_USER` | DB 사용자명 | 자동 생성 (고정값) |
| `POSTGRES_PASSWORD` | DB 비밀번호 | 자동 생성 |
| `POSTGRES_DB` | DB 이름 | 자동 생성 (고정값) |
| `DATABASE_URL` | DB 접속 URL | 자동 생성 |

**모두 자동 생성 가능** → 사용자가 `.env`를 편집할 필요 없음

#### 3-3. docker-compose.yml 수정

**환경변수 기본값 설정** (기존 .env 폴백 제거):

```yaml
# 현재
GOOGLE_CLIENT_ID=${BLOGGER_CLIENT_ID:-}

# 변경: 삭제 (DB에서 조회)
```

Celery 관련 환경변수도 docker-compose에서 제거 (DB에서 조회).

#### Phase 3 완료 기준
- [ ] `./deploy.sh` 실행 시 .env 자동 생성
- [ ] 사용자가 .env를 직접 편집할 필요 없음
- [ ] 모든 사용자 설정은 UI에서 관리
- [ ] .env에는 서버 인프라 키만 존재 (자동 생성)

---

## 3. 변경 파일 목록

### Phase 1
| 파일 | 변경 |
|------|------|
| `app/models/user_settings.py` | `blogger_client_id`, `blogger_client_secret` 컬럼 추가 |
| `app/routers/settings.py` | Blogger OAuth 저장/조회 처리 |
| `app/services/publishing/google_oauth_helper.py` | DB 우선 조회로 변경 |
| `app/templates/settings/modal.html` | Blogger OAuth 입력 필드 추가 |
| `app/static/js/settings.js` | Blogger 연결 테스트 추가 |
| `alembic/versions/0XX_add_blogger_oauth.py` | 마이그레이션 |
| `.env.required` | BLOGGER_CLIENT_* 선택사항으로 변경 |

### Phase 2
| 파일 | 변경 |
|------|------|
| `app/models/system_settings.py` | 신규 테이블 |
| `app/services/system_settings_service.py` | 설정 조회 서비스 (캐시) |
| `app/routers/settings.py` | 시스템 설정 CRUD API |
| `app/routers/flows_execute.py` | `settings.use_celery_*` → DB 조회 |
| `app/scheduler/flow_scheduler.py` | 동일 변경 |
| `app/core/rate_limiter.py` | RATELIMIT → DB 조회 |
| `app/templates/settings/modal.html` | 시스템 설정 탭 추가 |
| `app/static/js/settings.js` | 시스템 설정 저장/로드 |
| `alembic/versions/0XX_add_system_settings.py` | 마이그레이션 |

### Phase 3
| 파일 | 변경 |
|------|------|
| `deploy.sh` | 신규 배포 스크립트 |
| `docker-compose.yml` | 불필요한 환경변수 참조 제거 |
| `.env.required` | 최소화 (서버 인프라만) |

---

## 4. 작업 순서 및 의존성

| Phase | 작업 | 예상 규모 | 의존성 |
|-------|------|-----------|--------|
| 1 | Blogger OAuth → UI | 모델 2컬럼 + API/UI 수정 | 없음 |
| 2 | 시스템 설정 → DB + UI | 신규 테이블 + 서비스 + UI | Phase 1 |
| 3 | 배포 스크립트 | 스크립트 1개 + docker-compose 정리 | Phase 1, 2 |

---

**Last Updated**: 2026-04-22 | **Version**: v1.0.0
