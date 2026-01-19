"""
Alembic 환경 설정

동기 방식 마이그레이션을 위한 설정
(비동기 SQLAlchemy 모델과 호환)
"""
from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 모델 메타데이터 가져오기
from app.core.database import Base
from app.models import *  # noqa: F401, F403

target_metadata = Base.metadata


def get_url():
    """데이터베이스 URL 생성 (동기 드라이버 사용)"""
    # DATABASE_URL 환경변수 먼저 확인
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # asyncpg -> psycopg2 변환 (비동기 -> 동기)
        if "+asyncpg" in database_url:
            database_url = database_url.replace("+asyncpg", "")
        if "postgresql+asyncpg" in database_url:
            database_url = database_url.replace("postgresql+asyncpg", "postgresql")
        return database_url

    # 개별 환경변수에서 가져오기
    db_host = os.getenv("DB_HOST", "db")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "blogauto_v2")
    db_user = os.getenv("DB_USER", "blogauto")
    db_password = os.getenv("DB_PASSWORD", "blogauto123")

    # 동기 드라이버 (psycopg2) 사용
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def run_migrations_offline() -> None:
    """
    오프라인 모드에서 마이그레이션 실행

    데이터베이스에 연결하지 않고 SQL 스크립트만 생성
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    온라인 모드에서 마이그레이션 실행

    데이터베이스에 직접 연결하여 마이그레이션 적용
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
