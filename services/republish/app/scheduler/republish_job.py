"""
재발행 메인 Job
TODO: 모듈 시스템으로 전환 후 재구현 필요
"""
from ..core.logger import get_logger

logger = get_logger("republish_job", "republish.log")

async def republish_job():
    """
    메인 재발행 Job - 임시 비활성화 (모듈 시스템으로 전환 중)
    TODO: 프로파일 시스템에서 모듈 시스템으로 업데이트 필요
    """
    logger.info("[JOB] 재발행 Job - 모듈 시스템으로 전환 중으로 임시 비활성화")
    return