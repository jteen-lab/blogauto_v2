#!/usr/bin/env bash
# ============================================================
# BlogAuto 원클릭 설치 스크립트
# Usage:
#   curl -fsSL https://[host]/install.sh | bash
#   curl -fsSL https://[host]/install.sh | bash -s -- --restore-from=URL
# ============================================================
set -euo pipefail

# ── 설정 (배포 시 GitHub Pages URL로 교체) ─────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/blogauto}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/jteen-lab/blogauto}"
IMAGE_TAG="${IMAGE_TAG:-stable}"
COMPOSE_URL="${COMPOSE_URL:-https://raw.githubusercontent.com/jteen-lab/blogauto-deploy/main/docker-compose.prod.yml}"
WRAPPER_URL="${WRAPPER_URL:-https://raw.githubusercontent.com/jteen-lab/blogauto-deploy/main/blogauto-cli.sh}"
MIN_RAM_MB=900
MIN_DISK_GB=5

# ── 인자 파싱 ──────────────────────────────────────────────
RESTORE_FROM=""
for arg in "$@"; do
    case "$arg" in
        --restore-from=*) RESTORE_FROM="${arg#--restore-from=}" ;;
        --dir=*) INSTALL_DIR="${arg#--dir=}" ;;
        --tag=*) IMAGE_TAG="${arg#--tag=}" ;;
        --help|-h)
            cat <<EOF
BlogAuto 설치 옵션:
  --dir=PATH         설치 디렉토리 (기본 /opt/blogauto)
  --tag=TAG          이미지 태그 (stable|beta, 기본 stable)
  --restore-from=URL 관리자 데이터 백업 URL (선택)
EOF
            exit 0
            ;;
    esac
done

# ── 색상 + 헬퍼 ────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()   { echo -e "${GREEN}✅${NC} $*"; }
warn() { echo -e "${YELLOW}⚠️${NC}  $*"; }
err()  { echo -e "${RED}❌${NC} $*" >&2; }
die()  { err "$*"; exit 1; }
hr()   { echo "────────────────────────────────────────────────"; }
banner() {
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo -e "${BOLD}🚀 BlogAuto 자동 설치 마법사${NC}"
    echo "═══════════════════════════════════════════════════"
}

prompt() {
    local msg="$1" varname="$2" default="${3:-}" silent="${4:-}"
    if [[ -n "$default" ]]; then
        msg="$msg [$default]"
    fi
    if [[ "$silent" == "silent" ]]; then
        read -rs -p "   ${msg}: " value && echo
    else
        read -r -p "   ${msg}: " value
    fi
    [[ -z "$value" && -n "$default" ]] && value="$default"
    eval "$varname=\"\$value\""
}

# ── 1. 권한 + 환경 점검 ────────────────────────────────────
check_prerequisites() {
    log "환경 점검 중..."

    if [[ $EUID -ne 0 ]]; then
        if ! command -v sudo >/dev/null 2>&1; then
            die "root 권한 또는 sudo 가 필요합니다."
        fi
        warn "sudo 권한이 필요합니다. 비밀번호를 요청할 수 있습니다."
        sudo -v || die "sudo 권한 획득 실패"
        SUDO="sudo"
    else
        SUDO=""
    fi

    # OS 확인
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        log "OS 감지: $PRETTY_NAME"
        case "$OS_ID" in
            ubuntu|debian|centos|rocky|almalinux|fedora) ok "지원되는 OS" ;;
            *)
                warn "공식 지원 OS가 아닙니다. 계속 진행할까요? [y/N]"
                read -r confirm
                [[ "$confirm" =~ ^[Yy]$ ]] || die "설치 취소"
                ;;
        esac
    else
        warn "OS를 감지할 수 없습니다. 계속 진행할까요? [y/N]"
        read -r confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || die "설치 취소"
    fi

    # 메모리 점검
    local mem_mb
    mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    if (( mem_mb < MIN_RAM_MB )); then
        warn "메모리 ${mem_mb}MB — 권장 ${MIN_RAM_MB}MB 이상. 그래도 진행할까요? [y/N]"
        read -r confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || die "설치 취소"
    else
        ok "메모리 ${mem_mb}MB"
    fi

    # 디스크 점검
    local disk_gb
    disk_gb=$(df -BG --output=avail "$(dirname "$INSTALL_DIR")" 2>/dev/null | tail -1 | tr -d 'G ' || echo 0)
    if (( disk_gb < MIN_DISK_GB )); then
        die "디스크 공간 부족 (${disk_gb}GB 사용 가능, 최소 ${MIN_DISK_GB}GB 필요)"
    fi
    ok "디스크 ${disk_gb}GB 사용 가능"

    # 포트 점검
    for port in 80 443 5432 6379 8000; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            warn "포트 ${port}이 이미 사용 중입니다."
        fi
    done
}

# ── 2. Docker 설치 ────────────────────────────────────────
install_docker() {
    if command -v docker >/dev/null 2>&1; then
        ok "Docker 이미 설치됨: $(docker --version)"
    else
        log "Docker 설치 중... (최대 3분)"
        curl -fsSL https://get.docker.com | $SUDO sh >/dev/null 2>&1 \
            || die "Docker 설치 실패. 수동 설치 후 다시 실행: https://docs.docker.com/engine/install/"
        ok "Docker 설치 완료"
    fi

    if ! docker compose version >/dev/null 2>&1; then
        log "docker compose v2 플러그인 설치 중..."
        $SUDO apt-get update -qq >/dev/null 2>&1 || true
        $SUDO apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 \
            || die "docker compose v2 설치 실패"
    fi
    ok "docker compose: $(docker compose version --short)"

    $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
    if [[ $EUID -ne 0 ]]; then
        $SUDO usermod -aG docker "$USER" 2>/dev/null || true
    fi
}

# ── 3. 설치 디렉토리 준비 ──────────────────────────────────
setup_directory() {
    if [[ -d "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/.env" ]]; then
        warn "기존 설치 발견: $INSTALL_DIR"
        echo -n "   덮어쓸까요? 기존 .env 는 .env.bak.$(date +%s) 로 백업됩니다 [y/N]: "
        read -r confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || die "설치 취소"
        $SUDO cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak.$(date +%s)"
    fi
    $SUDO mkdir -p "$INSTALL_DIR"/{data,media,backups,logs}
    ok "설치 디렉토리 준비: $INSTALL_DIR"
}

# ── 4. 대화형 마법사 ──────────────────────────────────────
run_wizard() {
    banner
    log "설치 위치: $INSTALL_DIR"
    log "이미지: $IMAGE_REGISTRY:$IMAGE_TAG"
    log "예상 시간: 5-10분. 중간 취소: Ctrl+C"
    echo ""
    hr

    echo -e "${BOLD}▶ 1/6: 이메일 발송용 Gmail 주소${NC}"
    log "가입 알림/시스템 알림 발신자로 사용됩니다"
    prompt "Gmail" SMTP_USER

    echo -e "${BOLD}▶ 2/6: Gmail 앱 비밀번호 (16자)${NC}"
    log "https://myaccount.google.com/apppasswords 에서 발급"
    log "2단계 인증 후 발급한 16자리 앱 비밀번호 (일반 비번 아님)"
    prompt "앱 비밀번호" SMTP_PASSWORD "" silent

    echo -e "${BOLD}▶ 3/6: 접속 도메인 (선택)${NC}"
    log "도메인이 있다면 입력 (HTTPS 자동 발급), 없으면 엔터"
    local public_ip
    public_ip=$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || echo "")
    [[ -n "$public_ip" ]] && log "감지된 공인 IP: $public_ip"
    prompt "도메인" DOMAIN

    echo -e "${BOLD}▶ 4/6: BlogAuto 관리자 이메일${NC}"
    log "이 이메일로 로그인합니다"
    prompt "관리자 이메일" ADMIN_EMAIL

    echo -e "${BOLD}▶ 5/6: 관리자 비밀번호 (8자 이상)${NC}"
    while true; do
        prompt "비밀번호" ADMIN_PASS "" silent
        if (( ${#ADMIN_PASS} < 8 )); then
            err "8자 이상이어야 합니다"
            continue
        fi
        prompt "비밀번호 확인" ADMIN_PASS_CONFIRM "" silent
        [[ "$ADMIN_PASS" == "$ADMIN_PASS_CONFIRM" ]] && break
        err "일치하지 않습니다. 다시 입력해주세요"
    done

    echo -e "${BOLD}▶ 6/6: 자동 업데이트 (1시간마다)${NC}"
    log "새 버전 자동 적용. 안전장치(롤백/백업) 자동 동작"
    prompt "활성화 [Y/n]" ENABLE_WATCHTOWER "Y"
    [[ "$ENABLE_WATCHTOWER" =~ ^[Yy]$ ]] && ENABLE_WATCHTOWER="true" || ENABLE_WATCHTOWER="false"

    hr
    ok "입력 완료. 설치를 시작합니다..."
    echo ""
}

# ── 5. .env 생성 ──────────────────────────────────────────
generate_env() {
    local secret_key encryption_key jwt_secret postgres_pass
    secret_key=$(openssl rand -hex 32)
    encryption_key=$(openssl rand -base64 32 | tr -d '/+=' | head -c 44)
    jwt_secret=$(openssl rand -hex 32)
    postgres_pass=$(openssl rand -hex 24)

    local public_host="${DOMAIN:-$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || echo localhost)}"

    $SUDO tee "$INSTALL_DIR/.env" >/dev/null <<EOF
# BlogAuto 환경설정 — 자동 생성 (수정 시 컨테이너 재시작 필요)
# 생성: $(date -Iseconds)

# 애플리케이션
SECRET_KEY=${secret_key}
ENCRYPTION_KEY=${encryption_key}
JWT_SECRET=${jwt_secret}
PUBLIC_HOST=${public_host}

# 데이터베이스
POSTGRES_USER=blogauto
POSTGRES_PASSWORD=${postgres_pass}
POSTGRES_DB=blogauto_v2
DATABASE_URL=postgresql+asyncpg://blogauto:${postgres_pass}@postgres:5432/blogauto_v2

# 이메일 (Gmail SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_FROM_NAME=BlogAuto

# 관리자 (초기 1회 자동 생성)
INITIAL_ADMIN_EMAIL=${ADMIN_EMAIL}
INITIAL_ADMIN_PASSWORD=${ADMIN_PASS}

# 이미지
BLOGAUTO_IMAGE=${IMAGE_REGISTRY}:${IMAGE_TAG}

# 자동 업데이트 (Watchtower)
ENABLE_WATCHTOWER=${ENABLE_WATCHTOWER}
WATCHTOWER_POLL_INTERVAL=3600

# 인증 후행 호환 자리 (Phase C에서 활성화)
CENTRAL_AUTH_ENABLED=false
CENTRAL_AUTH_URL=

# 시간대
TZ=Asia/Seoul
EOF
    $SUDO chmod 600 "$INSTALL_DIR/.env"
    ok ".env 생성 완료 (권한 600)"
}

# ── 6. docker-compose 다운로드 ────────────────────────────
fetch_compose() {
    log "docker-compose.yml 다운로드 중..."
    if ! $SUDO curl -fsSL "$COMPOSE_URL" -o "$INSTALL_DIR/docker-compose.yml"; then
        die "docker-compose.yml 다운로드 실패. 네트워크 확인 후 재시도: $COMPOSE_URL"
    fi
    ok "docker-compose.yml 준비"
}

# ── 7. 데이터 복원 (관리자 마이그레이션) ───────────────────
restore_data() {
    [[ -z "$RESTORE_FROM" ]] && return 0
    log "관리자 데이터 복원: $RESTORE_FROM"
    $SUDO curl -fsSL "$RESTORE_FROM" -o "$INSTALL_DIR/backups/restore.sql" \
        || die "백업 파일 다운로드 실패"
    ok "백업 파일 받음 ($(du -h "$INSTALL_DIR/backups/restore.sql" | cut -f1))"
    # postgres 시작 후 임포트는 start_services 다음 단계
}

# ── 8. 서비스 시작 ────────────────────────────────────────
start_services() {
    cd "$INSTALL_DIR"
    log "Docker 이미지 다운로드 중... (380MB 내외, 수 분 소요 가능)"
    $SUDO docker compose pull >/dev/null 2>&1 || warn "일부 이미지 pull 실패 (계속)"
    log "컨테이너 시작 중..."
    $SUDO docker compose up -d >/dev/null 2>&1 || die "컨테이너 시작 실패. 로그: $SUDO docker compose logs"

    # 데이터 복원 적용
    if [[ -n "$RESTORE_FROM" && -f "$INSTALL_DIR/backups/restore.sql" ]]; then
        log "DB 임포트 대기 (10초)..."
        sleep 10
        $SUDO docker compose exec -T postgres psql -U blogauto blogauto_v2 \
            < "$INSTALL_DIR/backups/restore.sql" >/dev/null 2>&1 \
            && ok "데이터 복원 완료" \
            || warn "데이터 복원 일부 실패 (수동 확인 필요)"
    fi

    # Health check
    log "서비스 정상 동작 대기 (최대 60초)..."
    local i=0
    while (( i < 60 )); do
        if curl -fsSL "http://localhost:8000/health" >/dev/null 2>&1; then
            ok "BlogAuto 정상 동작"
            return 0
        fi
        sleep 2; i=$((i+2))
    done
    warn "Health check 60초 내 응답 없음. 로그 확인: blogauto logs"
}

# ── 9. blogauto CLI wrapper 설치 ──────────────────────────
install_cli_wrapper() {
    log "blogauto CLI 명령 설치 중..."
    $SUDO curl -fsSL "$WRAPPER_URL" -o /usr/local/bin/blogauto 2>/dev/null \
        || $SUDO tee /usr/local/bin/blogauto >/dev/null <<EOF
#!/usr/bin/env bash
# BlogAuto CLI wrapper (자동 생성)
set -e
cd "$INSTALL_DIR"
case "\${1:-help}" in
    status)   docker compose ps ;;
    logs)     docker compose logs -f --tail 100 "\${2:-app}" ;;
    restart)  docker compose restart "\${2:-}" ;;
    stop)     docker compose down ;;
    start)    docker compose up -d ;;
    update)   docker compose pull && docker compose up -d ;;
    rollback) docker compose down && echo "롤백은 백업에서 복구 필요. /opt/blogauto/backups/ 참조" ;;
    backup)   docker compose exec postgres pg_dump -U blogauto blogauto_v2 > backups/manual_\$(date +%Y%m%d_%H%M%S).sql && echo "백업 완료" ;;
    uninstall) read -p "정말 삭제하시겠습니까? [y/N] " c && [[ "\$c" =~ ^[Yy]\$ ]] && docker compose down -v && rm -rf "$INSTALL_DIR" ;;
    *)
        echo "BlogAuto CLI 사용법:"
        echo "  blogauto status     상태 확인"
        echo "  blogauto logs       로그 보기"
        echo "  blogauto restart    재시작"
        echo "  blogauto update     수동 업데이트"
        echo "  blogauto backup     데이터 백업"
        echo "  blogauto rollback   이전 버전 복귀"
        echo "  blogauto uninstall  완전 제거"
        ;;
esac
EOF
    $SUDO chmod +x /usr/local/bin/blogauto
    ok "blogauto 명령 설치 완료"
}

# ── 10. 완료 안내 ─────────────────────────────────────────
print_summary() {
    local url
    if [[ -n "$DOMAIN" ]]; then
        url="https://$DOMAIN"
    else
        url="http://$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || echo localhost):8000"
    fi
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo -e "${BOLD}${GREEN}🎉 설치 완료!${NC}"
    echo "═══════════════════════════════════════════════════"
    echo ""
    echo "📌 접속 정보"
    echo "   URL:      ${url}"
    echo "   관리자:   ${ADMIN_EMAIL}"
    echo "   비밀번호: (입력하신 비밀번호)"
    echo ""
    echo "📌 관리 명령"
    echo "   blogauto status    — 상태 확인"
    echo "   blogauto logs      — 로그 보기"
    echo "   blogauto update    — 수동 업데이트"
    echo "   blogauto backup    — 데이터 백업"
    echo "   blogauto rollback  — 이전 버전 복귀"
    echo ""
    echo "📚 도움말: https://github.com/jteen-lab/blogauto/wiki"
    echo "📂 설치 위치: $INSTALL_DIR"
    echo "🔒 환경설정: $INSTALL_DIR/.env (권한 600 — 외부 노출 금지)"
    if [[ "$ENABLE_WATCHTOWER" == "true" ]]; then
        echo "🔄 자동 업데이트: 활성화 (1시간마다 새 버전 확인)"
    fi
    echo "═══════════════════════════════════════════════════"
}

# ── 메인 ──────────────────────────────────────────────────
main() {
    banner
    check_prerequisites
    install_docker
    setup_directory
    run_wizard
    generate_env
    fetch_compose
    restore_data
    start_services
    install_cli_wrapper
    print_summary
}

main "$@"
