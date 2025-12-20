#!/bin/bash
# Phase 1-1: BlogAuto V2 자동 배포 스크립트
# GitHub Webhook → 이 스크립트 실행 → Docker 재배포

set -e

# 설정 변수
PROJECT_DIR="/home/ubuntu/blogauto_v2/services/republish"
LOG_FILE="$PROJECT_DIR/logs/deploy.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
HEALTH_URL="http://localhost/health"

# 로그 함수
log_info() {
    echo "[$TIMESTAMP] 📝 INFO: $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$TIMESTAMP] ❌ ERROR: $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo "[$TIMESTAMP] ✅ SUCCESS: $1" | tee -a "$LOG_FILE"
}

# 배포 시작 로그
echo "" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
log_info "🚀 자동 배포 시작"
log_info "현재 디렉토리: $(pwd)"
log_info "프로젝트 디렉토리: $PROJECT_DIR"

# 프로젝트 디렉토리로 이동
cd "$PROJECT_DIR" || {
    log_error "프로젝트 디렉토리 이동 실패: $PROJECT_DIR"
    exit 1
}

# 1. Git 최신 코드 가져오기
log_info "Step 1: Git pull 실행..."
if git pull origin main >> "$LOG_FILE" 2>&1; then
    log_success "Git pull 완료"
else
    log_error "Git pull 실패"
    exit 1
fi

# 2. 기존 컨테이너 중지
log_info "Step 2: 기존 Docker 컨테이너 중지..."
if docker-compose -f docker-compose.yml -f docker-compose.prod.yml down >> "$LOG_FILE" 2>&1; then
    log_success "컨테이너 중지 완료"
else
    log_error "컨테이너 중지 실패"
    # 계속 진행 (컨테이너가 없을 수도 있음)
fi

# 3. Docker 이미지 빌드
log_info "Step 3: Docker 이미지 빌드..."
if docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache >> "$LOG_FILE" 2>&1; then
    log_success "Docker 빌드 완료"
else
    log_error "Docker 빌드 실패"
    exit 1
fi

# 4. 컨테이너 시작
log_info "Step 4: Docker 컨테이너 시작..."
if docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d >> "$LOG_FILE" 2>&1; then
    log_success "컨테이너 시작 완료"
else
    log_error "컨테이너 시작 실패"
    exit 1
fi

# 5. 헬스체크 (30초 대기 후)
log_info "Step 5: 헬스체크 대기 중 (30초)..."
sleep 30

for i in {1..5}; do
    log_info "헬스체크 시도 $i/5..."
    if curl -sf "$HEALTH_URL" > /dev/null; then
        log_success "헬스체크 통과 - 배포 성공!"
        echo "[$TIMESTAMP] 🎉 배포 완료 - 서비스가 정상 작동 중입니다" >> "$LOG_FILE"
        echo "========================================" >> "$LOG_FILE"
        exit 0
    else
        log_info "헬스체크 실패 - 5초 후 재시도..."
        sleep 5
    fi
done

# 헬스체크 최종 실패
log_error "헬스체크 실패 - 배포 실패!"
log_info "Docker 로그 확인:"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=20 >> "$LOG_FILE" 2>&1

echo "========================================" >> "$LOG_FILE"
exit 1