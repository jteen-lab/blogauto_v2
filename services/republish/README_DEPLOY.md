# 🚀 BlogAuto V2 배포 가이드

**Phase 1-1: Docker + 오라클 클라우드 + 자동 배포 시스템**

---

## 📋 목차
1. [개요](#-개요)
2. [로컬 개발 환경](#-로컬-개발-환경)
3. [오라클 서버 설정](#-오라클-서버-설정)
4. [자동 배포 설정](#-자동-배포-설정)
5. [GitHub Webhook 설정](#-github-webhook-설정)
6. [트러블슈팅](#-트러블슈팅)
7. [유지보수](#-유지보수)

---

## 🎯 개요

BlogAuto V2의 자동 배포 시스템은 다음과 같이 동작합니다:

```
개발자 git push → GitHub → Webhook → 오라클 서버 → Docker 재배포 → 서비스 재시작
```

### 🏗️ 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   개발자 로컬    │    │     GitHub      │    │   오라클 서버    │
│                │    │                │    │                │
│ git push main   │───▶│ Webhook 트리거  │───▶│ deploy.sh 실행  │
│                │    │                │    │                │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
                               ┌─────────────────────────────────────┐
                               │        Docker 컨테이너들            │
                               │                                   │
                               │  ┌───────┐ ┌─────────┐ ┌────────┐ │
                               │  │ Nginx │ │FastAPI │ │PostgreSQL│ │
                               │  │  :80  │ │  :8000  │ │  :5432  │ │
                               │  └───────┘ └─────────┘ └────────┘ │
                               └─────────────────────────────────────┘
```

---

## 💻 로컬 개발 환경

### 1. 환경 설정

```bash
# 1. 프로젝트 클론
git clone <repository-url>
cd blogauto_v2/services/republish

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 개발용 설정 입력

# 3. Docker 실행
docker-compose up -d

# 4. 서비스 확인
curl http://localhost:8001/health
```

### 2. 개발 워크플로우

```bash
# 코드 수정 후
git add .
git commit -m "feat: 새로운 기능 추가"
git push origin main  # 자동 배포 트리거
```

---

## 🌐 오라클 서버 설정

### 1. 서버 준비

```bash
# 1. 서버 접속
ssh ubuntu@your-server-ip

# 2. Docker 설치
sudo apt update
sudo apt install docker.io docker-compose-plugin

# 3. Docker 권한 설정
sudo usermod -aG docker ubuntu
newgrp docker

# 4. 프로젝트 클론
git clone <repository-url>
cd blogauto_v2/services/republish
```

### 2. 환경 설정

```bash
# 1. 환경변수 설정
cp .env.example .env
nano .env  # 프로덕션 값으로 수정

# 예시 .env 내용:
# SECRET_KEY=prod_sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0
# POSTGRES_PASSWORD=Prod_PG_Pass_2024!@#
# JWT_SECRET=jwt_secret_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
# WEBHOOK_SECRET=webhook_secret_x1y2z3a4b5c6d7e8f9

# 2. 방화벽 설정
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 9000 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

### 3. 첫 배포

```bash
# 1. 프로덕션 배포
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 2. 서비스 확인
curl http://localhost/health
docker-compose logs
```

---

## 🔗 자동 배포 설정

### 1. Webhook 설치

```bash
# 오라클 서버에서 실행
cd /home/ubuntu/blogauto_v2/services/republish
chmod +x scripts/setup_webhook.sh
./scripts/setup_webhook.sh
```

### 2. 서비스 상태 확인

```bash
# Webhook 서비스 상태
sudo systemctl status webhook

# Docker 컨테이너 상태
docker-compose ps

# 로그 확인
tail -f logs/deploy.log
```

---

## 🔧 GitHub Webhook 설정

### 1. GitHub Repository 설정

1. **Repository → Settings → Webhooks → Add webhook**

2. **설정 값:**
   ```
   Payload URL: http://YOUR_SERVER_IP:9000/hooks/blogauto-deploy
   Content type: application/json
   Secret: (당신의 WEBHOOK_SECRET 값)
   Events: Just the push event
   ```

3. **저장 및 테스트**

### 2. 테스트

```bash
# 로컬에서 테스트 커밋
echo "test" >> test.txt
git add test.txt
git commit -m "test: 자동 배포 테스트"
git push origin main

# 서버에서 로그 확인
tail -f logs/deploy.log
```

---

## 📊 모니터링

### 1. 로그 파일 위치

```bash
/home/ubuntu/blogauto_v2/services/republish/logs/
├── app.log           # 애플리케이션 로그
├── auth.log          # 인증 관련 로그
├── error.log         # 에러 로그
├── deploy.log        # 배포 로그
├── nginx_access.log  # Nginx 접근 로그
└── nginx_error.log   # Nginx 에러 로그
```

### 2. 실시간 로그 모니터링

```bash
# 배포 로그 실시간 확인
tail -f logs/deploy.log

# 애플리케이션 로그 확인
tail -f logs/app.log

# Docker 로그 확인
docker-compose logs -f
```

### 3. 시스템 상태 확인

```bash
# 컨테이너 상태
docker-compose ps

# 시스템 리소스
htop
df -h

# 헬스체크
curl http://localhost/health
curl http://localhost:9000/hooks/blogauto-deploy  # Webhook 테스트
```

---

## 🔧 트러블슈팅

### 일반적인 문제들

#### 1. 배포 실패 시
```bash
# 로그 확인
tail -n 50 logs/deploy.log

# 컨테이너 로그 확인
docker-compose logs

# 수동 배포 시도
./scripts/deploy.sh
```

#### 2. Webhook 동작 안 함
```bash
# Webhook 서비스 상태 확인
sudo systemctl status webhook

# Webhook 서비스 재시작
sudo systemctl restart webhook

# 방화벽 확인
sudo iptables -L | grep 9000
```

#### 3. 데이터베이스 연결 오류
```bash
# PostgreSQL 컨테이너 상태 확인
docker-compose exec db pg_isready

# 데이터베이스 재시작
docker-compose restart db
```

#### 4. 메모리 부족 (오라클 무료 티어)
```bash
# 스왑 메모리 추가
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# /etc/fstab에 추가
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 롤백 방법

```bash
# 이전 커밋으로 롤백
git log --oneline  # 커밋 해시 확인
git checkout <이전-커밋-해시>
./scripts/deploy.sh
```

---

## 🔄 유지보수

### 정기 작업

#### 매주
```bash
# 로그 파일 정리 (1주일 이상된 파일)
find logs/ -name "*.log" -mtime +7 -delete

# 미사용 Docker 이미지 정리
docker system prune -f
```

#### 매월
```bash
# 시스템 업데이트
sudo apt update && sudo apt upgrade

# 보안 패치 적용
docker-compose pull
docker-compose up -d
```

#### 분기별
```bash
# 환경변수 보안 검토
# JWT_SECRET, WEBHOOK_SECRET 등 변경 고려
```

### 백업

#### 데이터베이스 백업
```bash
# 백업 생성
docker-compose exec db pg_dump -U blogauto blogauto_v2 > backup_$(date +%Y%m%d).sql

# 백업 복원
docker-compose exec -T db psql -U blogauto -d blogauto_v2 < backup_20241221.sql
```

#### 설정 파일 백업
```bash
# .env 파일 백업 (주의: 민감 정보 포함)
cp .env .env.backup.$(date +%Y%m%d)
```

---

## 📞 지원

### 추가 도움이 필요한 경우

1. **로그 수집:** `logs/` 디렉토리의 모든 파일
2. **시스템 정보:** `docker-compose ps`, `systemctl status webhook`
3. **에러 메시지:** 정확한 에러 메시지와 발생 시점

### 연락처

- **GitHub Issues:** [Repository Issues 페이지]
- **문서:** 이 README 파일과 CLAUDE.md 참조

---

## 🎯 다음 단계

**Phase 1-1 완료 후:**
- ✅ Docker 컨테이너로 서비스 운영
- ✅ git push → 자동 배포 파이프라인
- ✅ 로그 기반 모니터링 시스템

**Phase 2 예정:**
- 블로그 관리 시스템 (블로그 등록, 설정, 암호화)
- WordPress/Blogger API 연동 준비

---

**🚨 중요:** 이 문서의 모든 비밀번호와 시크릿은 프로덕션 환경에서 반드시 변경하세요!