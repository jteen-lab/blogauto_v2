"""Celery 비동기 브릿지 및 공통 예외 클래스.

모든 Celery 태스크 파일에서 공통으로 사용하는 async-to-sync 브릿지와
태스크 상태 구분을 위한 예외 클래스를 제공합니다.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskSkipped(Exception):
    """의도적 스킵을 나타내는 예외.

    제목 없음, 발행 대상 없음 등 정상적인 스킵 상황에서 발생합니다.
    Celery는 이를 FAILURE로 기록하지만, 로그와 에러 메시지로
    실제 에러와 구분할 수 있습니다.
    """
    pass


def run_async(coro):
    """비동기 코루틴을 동기 Celery 태스크에서 실행.

    항상 새 이벤트 루프를 생성하여 Celery prefork 워커에서
    안전하게 동작합니다.

    Args:
        coro: 실행할 비동기 코루틴

    Returns:
        코루틴의 반환값
    """
    return asyncio.run(coro)
