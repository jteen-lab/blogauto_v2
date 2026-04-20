"""
Celery 설정 모듈

큐 구조 (5큐 체계):
- generation_queue: 글 생성 전체 파이프라인 (제목 재조합 + 본문 생성)
- publish_queue: 발행/재발행
- image_queue: 이미지 생성/업로드
- utility_queue: 수집/데이터 처리
- callback_queue: 완료 후처리
"""
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
