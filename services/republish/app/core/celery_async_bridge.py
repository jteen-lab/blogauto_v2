"""Celery 비동기 브릿지 및 공통 예외 클래스.

Celery prefork 워커에서 async 코루틴을 안전하게 실행합니다.
NullPool을 사용하여 이벤트 루프 간 커넥션 충돌을 방지합니다.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class TaskSkipped(Exception):
    """의도적 스킵을 나타내는 예외."""
    pass


def run_async(coro):
    """비동기 코루틴을 동기 Celery 태스크에서 실행."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@asynccontextmanager
async def celery_db_session():
    """Celery 전용 DB 세션 (NullPool로 이벤트 루프 충돌 방지).

    매 호출 시 새 엔진을 생성하고 사용 후 즉시 폐기합니다.
    NullPool은 커넥션 풀을 유지하지 않으므로 이벤트 루프 바인딩 문제가 없습니다.
    """
    from sqlalchemy.ext.asyncio import (
        create_async_engine, AsyncSession,
    )
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.config import settings

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    session_factory = sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False,
    )

    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        await engine.dispose()
