#!/bin/bash
# Phase 1-1: Webhook 설치 및 설정 스크립트 (오라클 서버용)

set -e

echo "🔧 Webhook 설치 및 설정 시작..."

# 1. Webhook 바이너리 다운로드 (ARM64 아키텍처용)
echo "📥 Webhook 바이너리 다운로드..."
cd /tmp
wget https://github.com/adnanh/webhook/releases/download/2.8.1/webhook-linux-arm64-2.8.1.tar.gz
tar -xzf webhook-linux-arm64-2.8.1.tar.gz

# 2. 바이너리를 /usr/local/bin으로 복사
echo "📦 Webhook 설치..."
sudo cp webhook-linux-arm64-2.8.1/webhook /usr/local/bin/
sudo chmod +x /usr/local/bin/webhook

# 3. 프로젝트 디렉토리 확인
PROJECT_DIR="/home/ubuntu/blogauto_v2/services/republish"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 프로젝트 디렉토리가 없습니다: $PROJECT_DIR"
    exit 1
fi

# 4. Webhook 시크릿을 .env 파일에서 읽기
if [ -f "$PROJECT_DIR/.env" ]; then
    WEBHOOK_SECRET=$(grep WEBHOOK_SECRET "$PROJECT_DIR/.env" | cut -d '=' -f2)
    if [ -z "$WEBHOOK_SECRET" ]; then
        echo "❌ .env 파일에 WEBHOOK_SECRET이 설정되지 않았습니다"
        exit 1
    fi
else
    echo "❌ .env 파일이 없습니다. 먼저 환경변수를 설정해주세요"
    exit 1
fi

# 5. hooks.json에 시크릿 적용
echo "🔑 Webhook 시크릿 설정..."
sed -i "s/WEBHOOK_SECRET_PLACEHOLDER/$WEBHOOK_SECRET/g" "$PROJECT_DIR/webhook/hooks.json"

# 6. systemd 서비스 파일 생성
echo "🚀 Webhook 시스템 서비스 설정..."
sudo tee /etc/systemd/system/webhook.service > /dev/null <<EOF
[Unit]
Description=Small server for creating HTTP endpoints (webhooks)
Documentation=https://github.com/adnanh/webhook/
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
ExecStart=/usr/local/bin/webhook -hooks $PROJECT_DIR/webhook/hooks.json -verbose -port 9000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 7. 방화벽 포트 열기
echo "🔥 방화벽 설정 (포트 9000)..."
sudo iptables -I INPUT -p tcp --dport 9000 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null

# 8. 서비스 활성화 및 시작
echo "🎯 Webhook 서비스 시작..."
sudo systemctl daemon-reload
sudo systemctl enable webhook
sudo systemctl start webhook

# 9. 서비스 상태 확인
echo "✅ Webhook 설치 및 설정 완료!"
echo ""
echo "📊 서비스 상태:"
sudo systemctl status webhook --no-pager

echo ""
echo "🔗 GitHub Webhook 설정 정보:"
echo "   URL: http://YOUR_SERVER_IP:9000/hooks/blogauto-deploy"
echo "   Content type: application/json"
echo "   Secret: (당신의 WEBHOOK_SECRET 값)"
echo "   Events: Just the push event"

echo ""
echo "🧪 테스트:"
echo "   curl -X POST http://localhost:9000/hooks/blogauto-deploy"