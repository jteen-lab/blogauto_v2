#!/bin/bash
# ============================================================
# BlogAuto V2 배포 스크립트
# 사용법: ./deploy.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/services/republish/.env"
COMPOSE_DIR="$SCRIPT_DIR/services/republish"

echo ""
echo "=========================================="
echo "  BlogAuto V2 배포"
echo "=========================================="
echo ""

# 1. .env 파일 자동 생성 (없을 때만)
if [ ! -f "$ENV_FILE" ]; then
    echo "[1/4] 환경 설정 파일을 자동 생성합니다..."

    # 보안 키 자동 생성
    SECRET_KEY=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)

    # ENCRYPTION_KEY 생성 (Python Fernet)
    if command -v python3 &> /dev/null; then
        ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")
    fi
    if [ -z "$ENCRYPTION_KEY" ]; then
        ENCRYPTION_KEY=$(openssl rand -base64 32 | tr -d '\n')
    fi

    cat > "$ENV_FILE" << EOF
# ========================================
# BlogAuto V2 환경 설정 (자동 생성)
# ========================================
# 이 파일은 deploy.sh에 의해 자동 생성되었습니다.
# 서버 인프라 키만 포함되며, 나머지 설정은 UI에서 관리합니다.

# 애플리케이션 보안
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}

# 데이터베이스
POSTGRES_USER=blogauto
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=blogauto_v2
DATABASE_URL=postgresql://blogauto:${DB_PASSWORD}@db:5432/blogauto_v2
EOF

    echo "  환경 설정 파일 생성 완료: $ENV_FILE"
else
    echo "[1/4] 기존 환경 설정 파일 사용"
fi

# 2. Docker 빌드 및 시작
echo "[2/4] Docker 컨테이너를 시작합니다..."
cd "$COMPOSE_DIR"
docker-compose down 2>/dev/null || true
docker-compose build --no-cache
docker-compose up -d

# 3. 컨테이너 준비 대기
echo "[3/4] 서비스 준비 대기..."
for i in $(seq 1 30); do
    if docker-compose exec -T app curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  서비스 준비 완료"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  경고: 서비스 시작 타임아웃 (30초). 로그를 확인하세요:"
        echo "  docker-compose logs app --tail 20"
    fi
    sleep 1
done

# 4. 시스템 설정 초기화
echo "[4/4] 시스템 설정 초기화..."
docker-compose exec -T app python3 -c "
import asyncio
from app.core.database import db_manager
from app.services.system_settings_service import SystemSettingsService

async def init():
    await db_manager.initialize()
    async with db_manager.get_session() as db:
        await SystemSettingsService.ensure_defaults(db)

asyncio.run(init())
" 2>/dev/null && echo "  시스템 설정 초기화 완료" || echo "  시스템 설정 초기화 스킵 (수동 확인 필요)"

# 완료
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo "=========================================="
echo "  BlogAuto V2 배포 완료!"
echo "=========================================="
echo ""
echo "  접속 주소: http://${SERVER_IP}:8000"
echo ""
echo "  다음 단계:"
echo "  1. 위 주소로 접속하여 관리자 계정으로 로그인"
echo "  2. 설정 > API 설정에서 AI API 키 입력"
echo "  3. 설정 > API 설정 > Google Blogger에서 OAuth 정보 입력 (Blogger 사용 시)"
echo "  4. 설정 > 시스템 설정에서 워커 ON/OFF 설정"
echo ""
