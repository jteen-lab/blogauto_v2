"""
데이터베이스 연결 및 세션 관리

Features:
- SQLAlchemy async 엔진
- 연결 풀링
- 자동 재시도
- 트랜잭션 관리
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import event
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import asyncio

from .config import settings
from .logger import get_logger

logger = get_logger("database")

Base = declarative_base()

class DatabaseManager:
    """데이터베이스 연결 관리자"""

    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._is_initialized = False

    async def initialize(self) -> None:
        """데이터베이스 엔진 초기화"""
        if self._is_initialized:
            return

        logger.info("데이터베이스 연결 초기화 시작")

        try:
            # 비동기 엔진 생성
            self.engine = create_async_engine(
                settings.database_url,
                echo=settings.db_echo,
                pool_pre_ping=True,
                pool_recycle=3600,  # 1시간
                pool_size=5,
                max_overflow=10,
                poolclass=NullPool if settings.is_testing else None
            )

            # 세션 팩토리 생성
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )

            # 연결 테스트
            await self._test_connection()

            self._is_initialized = True
            logger.info("데이터베이스 연결 초기화 완료")

        except Exception as e:
            logger.error(f"데이터베이스 연결 실패: {e}")
            raise

    async def _test_connection(self) -> None:
        """연결 테스트"""
        try:
            async with self.engine.begin() as conn:
                await conn.execute("SELECT 1")
            logger.info("데이터베이스 연결 테스트 성공")
        except Exception as e:
            logger.error(f"데이터베이스 연결 테스트 실패: {e}")
            raise

    async def close(self) -> None:
        """연결 종료"""
        if self.engine:
            await self.engine.dispose()
            logger.info("데이터베이스 연결 종료")
            self._is_initialized = False

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """세션 컨텍스트 매니저"""
        if not self._is_initialized:
            await self.initialize()

        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self) -> None:
        """테이블 생성"""
        if not self._is_initialized:
            await self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("데이터베이스 테이블 생성 완료")

    async def drop_tables(self) -> None:
        """테이블 삭제 (테스트용)"""
        if not self._is_initialized:
            await self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            logger.info("데이터베이스 테이블 삭제 완료")


# 전역 데이터베이스 매니저
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """의존성 주입용 세션 제공자"""
    async with db_manager.get_session() as session:
        yield session


async def init_database() -> None:
    """애플리케이션 시작시 데이터베이스 초기화"""
    await db_manager.initialize()


async def close_database() -> None:
    """애플리케이션 종료시 데이터베이스 정리"""
    await db_manager.close()


# SQLAlchemy 이벤트 리스너
@event.listens_for(AsyncEngine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """SQLite 설정 (개발환경용)"""
    if "sqlite" in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()