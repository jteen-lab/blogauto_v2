# Phase 1-1: BlogAuto V2 Republish Service Dockerfile
# FastAPI + SQLAlchemy + PostgreSQL

FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
# default-jre-headless: KoNLPy(Okt 형태소 분석)에서 JVM 필요
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 및 종속성 설치
COPY services/republish/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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