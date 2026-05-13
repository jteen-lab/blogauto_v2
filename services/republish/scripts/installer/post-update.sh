#!/usr/bin/env bash
# Watchtower post-update hook
# 새 컨테이너 시작 + health check 후 자동 실행
set -euo pipefail

cd /opt/blogauto

echo "[$(date -Iseconds)] post-update 시작" >> logs/update.log

# 1. Health check 90초 대기
HEALTHY=false
for i in {1..45}; do
    if curl -fsSL http://localhost:8000/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 2
done

if [[ "$HEALTHY" != "true" ]]; then
    echo "[$(date -Iseconds)] health check 실패 — 자동 롤백 시도" >> logs/update.log
    # 이전 이미지로 롤백 (Watchtower가 이전 이미지를 보존하므로)
    LAST_IMAGE=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "blogauto" | grep -v "<none>" | sed -n '2p')
    if [[ -n "$LAST_IMAGE" ]]; then
        export BLOGAUTO_IMAGE="$LAST_IMAGE"
        docker compose up -d app
        echo "[$(date -Iseconds)] 롤백 완료 → $LAST_IMAGE" >> logs/update.log
    fi
fi

# 2. 점검 모드 OFF
rm -f /opt/blogauto/maintenance 2>/dev/null || true

# 3. 관리자 알림 (이메일/텔레그램 — 환경변수에 토큰 있으면)
if [[ -n "${ADMIN_NOTIFY_EMAIL:-}" ]]; then
    # SMTP 발송은 앱에 위임 (간단히 로그만)
    echo "[$(date -Iseconds)] 업데이트 완료 알림 대상: $ADMIN_NOTIFY_EMAIL" >> logs/update.log
fi

echo "[$(date -Iseconds)] post-update 완료 (healthy=$HEALTHY)" >> logs/update.log
