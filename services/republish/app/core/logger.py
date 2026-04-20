"""
고급 파일 기반 로깅 시스템

주요 기능:
- 로그 파일 분리 (app.log, auth.log, error.log)
- 로그 로테이션 (10MB 또는 일별)
- 구조화된 로그 포맷
- 모듈별 로거 관리
- 성능 최적화
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager


class LoggerConfig:
    """로깅 설정 관리"""

    LOG_DIR = "logs"
    LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s | %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5

    LOGGERS = {
        "app": "app.log",
        "auth": "auth.log",
        "error": "error.log",
        "request": "request.log"
    }


class BlogAutoLogger:
    """BlogAuto 전용 로거 매니저"""

    _instance: Optional['BlogAutoLogger'] = None
    _loggers: Dict[str, logging.Logger] = {}

    def __new__(cls) -> 'BlogAutoLogger':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._setup_log_directory()
            self.initialized = True

    def _setup_log_directory(self) -> None:
        """로그 디렉토리 생성"""
        log_path = Path(LoggerConfig.LOG_DIR)
        log_path.mkdir(exist_ok=True)

    def get_logger(self, name: str, log_file: Optional[str] = None) -> logging.Logger:
        """
        모듈별 로거 반환

        Args:
            name: 로거 이름 (모듈명)
            log_file: 로그 파일명 (미지정시 app.log)

        Returns:
            설정된 로거 객체
        """
        if name in self._loggers:
            return self._loggers[name]

        # 로그 파일 결정
        if log_file is None:
            log_file = LoggerConfig.LOGGERS.get(name, "app.log")

        logger = self._create_logger(name, log_file)
        self._loggers[name] = logger
        return logger

    def _create_logger(self, name: str, log_file: str) -> logging.Logger:
        """새 로거 생성"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        # 중복 핸들러 방지
        if logger.handlers:
            return logger

        # 파일 핸들러 설정
        file_handler = self._create_file_handler(log_file)
        logger.addHandler(file_handler)

        # 에러 레벨은 error.log에도 기록
        if log_file != "error.log":
            error_handler = self._create_file_handler("error.log", logging.ERROR)
            logger.addHandler(error_handler)

        # 콘솔(stdout) 핸들러 (docker-compose logs에서 확인 가능)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            LoggerConfig.LOG_FORMAT, LoggerConfig.DATE_FORMAT
        ))
        logger.addHandler(console_handler)

        return logger

    def _create_file_handler(self, log_file: str, level: int = logging.INFO) -> RotatingFileHandler:
        """파일 핸들러 생성"""
        log_path = Path(LoggerConfig.LOG_DIR) / log_file

        handler = RotatingFileHandler(
            log_path,
            maxBytes=LoggerConfig.MAX_BYTES,
            backupCount=LoggerConfig.BACKUP_COUNT,
            encoding='utf-8'
        )

        formatter = logging.Formatter(
            LoggerConfig.LOG_FORMAT,
            datefmt=LoggerConfig.DATE_FORMAT
        )

        handler.setFormatter(formatter)
        handler.setLevel(level)

        return handler


# 전역 로거 매니저
logger_manager = BlogAutoLogger()


def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """편의 함수: 로거 반환"""
    return logger_manager.get_logger(name, log_file)


@contextmanager
def log_execution_time(logger: logging.Logger, operation: str):
    """실행 시간 로깅 컨텍스트 매니저"""
    start_time = datetime.now()
    logger.info(f"시작 | {operation}")

    try:
        yield
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"완료 | {operation} | 소요시간={duration:.3f}초")
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"실패 | {operation} | 소요시간={duration:.3f}초 | 오류={str(e)}")
        raise


def log_request_info(logger: logging.Logger, method: str, url: str,
                    ip: str, user_agent: Optional[str] = None) -> None:
    """요청 정보 로깅"""
    logger.info(f"요청 | {method} {url} | IP={ip} | UA={user_agent or 'Unknown'}")


def log_auth_attempt(logger: logging.Logger, email: str, ip: str,
                    success: bool, reason: Optional[str] = None) -> None:
    """인증 시도 로깅"""
    status = "성공" if success else "실패"
    message = f"인증시도 | {status} | 사용자={email} | IP={ip}"

    if not success and reason:
        message += f" | 실패사유={reason}"

    if success:
        logger.info(message)
    else:
        logger.warning(message)


def log_security_event(logger: logging.Logger, event_type: str,
                      details: Dict[str, Any]) -> None:
    """보안 이벤트 로깅"""
    detail_str = " | ".join([f"{k}={v}" for k, v in details.items()])
    logger.warning(f"보안이벤트 | {event_type} | {detail_str}")