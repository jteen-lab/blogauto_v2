# Phase 1-1: BlogAuto V2 Republish Service Dockerfile
# FastAPI + SQLAlchemy + PostgreSQL

FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
# default-jre-headless: KoNLPy(Okt 형태소 분석)에서 JVM 필요
# lib*/fonts-liberation: Playwright Chromium 헤드리스 실행에 필요한 런타임 라이브러리
#   (Debian slim은 Playwright --with-deps가 Ubuntu 패키지명을 써 실패하므로 직접 설치)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    default-jre-headless \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libglib2.0-0 libxshmfence1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 및 종속성 설치
COPY services/republish/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 브라우저 바이너리 설치 (런타임 라이브러리는 위 apt 단계에서 설치됨).
# --with-deps 대신 브라우저만 받아 Debian 미지원 OS 감지 오류를 회피.
# PLAYWRIGHT_BROWSERS_PATH: 공용 경로에 설치해 비특권 사용자(appuser)도 접근 가능.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# 애플리케이션 코드 복사 (build context = 레포 루트)
COPY services/republish/app/ app/
COPY services/republish/alembic/ alembic/
COPY services/republish/alembic.ini .

# shared/ 폴더 복사 (위 코드들이 sys.path 로 사용)
COPY shared/ shared/

# 로그 디렉토리 생성 (런타임에 로그 쓰기용 — git에 빈 폴더 안 올라가도 OK)
RUN mkdir -p logs && chmod 755 logs

# 비특권 사용자 생성 및 전환
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# 포트 노출
EXPOSE 8000

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 애플리케이션 실행
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]