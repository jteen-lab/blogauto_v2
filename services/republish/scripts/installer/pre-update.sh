#!/usr/bin/env bash
# Watchtower pre-update hook
# 새 이미지로 컨테이너 교체 직전 자동 실행
# 위치: /opt/blogauto/pre-update.sh (install.sh가 배치)
set -euo pipefail

cd /opt/blogauto

BACKUP_DIR="/opt/blogauto/backups"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] pre-update 시작" >> logs/update.log

# 1. .env 백업
cp .env "$BACKUP_DIR/.env.bak.$TS" 2>/dev/null || true

# 2. DB 자동 백업 (실패해도 업데이트는 진행)
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-blogauto}" \
    "${POSTGRES_DB:-blogauto_v2}" > "$BACKUP_DIR/db_$TS.sql" 2>>logs/update.log \
    || echo "[$(date -Iseconds)] DB 백업 실패 (계속)" >> logs/update.log

# 3. 점검 모드 ON
touch /opt/blogauto/maintenance 2>/dev/null || true

# 4. 백업 보관 정책 — 최근 14개만 유지
ls -t "$BACKUP_DIR"/db_*.sql 2>/dev/null | tail -n +15 | xargs -r rm
ls -t "$BACKUP_DIR"/.env.bak.* 2>/dev/null | tail -n +15 | xargs -r rm

echo "[$(date -Iseconds)] pre-update 완료" >> logs/update.log
