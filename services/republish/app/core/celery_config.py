"""
Celery 설정 모듈

큐 구조 (5큐 체계):
- generation_queue: 글 생성 전체 파이프라인 (제목 재조합 + 본문 생성)
- publish_queue: 발행/재발행
- image_queue: 이미지 생성/업로드
- utility_queue: 수집/데이터 처리
- callback_queue: 완료 후처리
"""
import logging
import os

from celery import Celery
from kombu import Queue

# Redis URL (config.py의 redis_url 또는 환경변수)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Celery 앱 생성
celery_app = Celery(
    "blogauto",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# 큐 정의 (5큐 체계)
celery_app.conf.task_queues = (
    Queue("generation_queue"),     # 글 생성 전체 파이프라인
    Queue("publish_queue"),        # 발행/재발행
    Queue("image_queue"),          # 이미지 생성/업로드
    Queue("utility_queue"),        # 수집/데이터 처리
    Queue("callback_queue"),       # 완료 후처리
)

# 태스크 라우팅
celery_app.conf.task_routes = {
    # 글 생성 파이프라인
    "tasks.generate_content": {"queue": "generation_queue"},
    "tasks.recombine_title": {"queue": "generation_queue"},
    # 발행/재발행
    "tasks.publish_post": {"queue": "publish_queue"},
    "tasks.publish_batch": {"queue": "publish_queue"},
    "tasks.republish_post": {"queue": "publish_queue"},
    # 이미지 처리
    "tasks.generate_image": {"queue": "image_queue"},
    "tasks.upload_image": {"queue": "image_queue"},
    # 수집/데이터 처리
    "tasks.collect_keywords": {"queue": "utility_queue"},
    "tasks.transfer_titles": {"queue": "utility_queue"},
    "tasks.collect_references": {"queue": "utility_queue"},
    # 완료 후처리
    "tasks.on_generation_complete": {"queue": "callback_queue"},
    "tasks.on_publish_complete": {"queue": "callback_queue"},
    "tasks.handle_dead_letter": {"queue": "callback_queue"},
}

# 기본 설정
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # 워커 안정성 (메모리 누수 방지)
    worker_max_tasks_per_child=100,       # 기본 100개 태스크 후 워커 프로세스 재시작
    worker_max_memory_per_child=200_000,  # 200MB 초과 시 워커 프로세스 재시작 (KB 단위)

    # 결과 만료
    result_expires=86400,  # 24시간 후 결과 자동 삭제

    # 브로커 연결 안정성
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    # 태스크 실행 안전장치
    task_reject_on_worker_lost=True,      # 워커 비정상 종료 시 태스크 거부 (재큐잉)
    task_default_rate_limit=None,          # Rate Limit은 AIRateLimiter에서 관리
)

# 태스크 모듈 명시적 import (워커가 태스크를 인식하도록)
# celery_config가 로드될 때 모든 태스크 모듈이 함께 import되어
# @celery_app.task 데코레이터가 실행되고 celery_app에 등록됨
# flake8: noqa: E402,F401
from app.core import celery_tasks  # noqa
from app.core import celery_publish_tasks  # noqa
from app.core import celery_utility_tasks  # noqa


# ── SQLAlchemy mapper 사전 초기화 (부모 프로세스에서 1회, fork 이전) ──
# task 실행 중 mapper 가 lazy 초기화되면, soft time limit 초과 시 초기화가
# 중단되어 mapper 가 half-initialized 상태로 캐시되고, 이후 모든 task 가
# "One or more mappers failed to initialize" 로 연쇄 실패한다.
#
# 주의: 이 작업(import app.models + configure_mappers)은 1GB RAM 환경에서
# swap 때문에 십수 초가 걸린다. worker_process_init(prefork child 마다 호출)에
# 두면 4 워커 × N child 가 동시에 실행해 메모리 경쟁으로 부팅이 마비된다.
# 따라서 celery_config 모듈 로드 시점(워커 부모 프로세스, prefork 이전)에
# 1회만 수행하고, child 들은 fork 로 이미 초기화된 mapper 를 상속한다.
try:
    import app.models  # noqa: F401 — 전체 모델 등록 (mapper 대상 확보)
    from sqlalchemy.orm import configure_mappers as _configure_mappers

    _configure_mappers()
    logging.getLogger("celery_config").info(
        "[WORKER_INIT] SQLAlchemy mapper 사전 초기화 완료 (부모 1회)"
    )
except Exception as _e:  # noqa: BLE001 — 부팅 차단 방지
    logging.getLogger("celery_config").warning(
        "[WORKER_INIT] mapper 사전 초기화 실패(무시하고 계속): %s", _e
    )
