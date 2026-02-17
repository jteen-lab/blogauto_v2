"""
Celery 설정 모듈

설계 문서: generation_module_workplan.md - Phase 1 - 1.2.1

큐 구조:
- title_queue: 제목 재조합 (워커 1~2개)
- content_queue: 글 생성 (워커 3~5개)
- image_queue: 이미지 생성 (워커 2개)
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

# 큐 정의 (설계 문서 2.2 Celery 큐 구조)
celery_app.conf.task_queues = [
    Queue("title_queue"),
    Queue("content_queue"),
    Queue("image_queue"),
]

# 태스크 라우팅
celery_app.conf.task_routes = {
    "app.core.celery_tasks.recombine_title": {"queue": "title_queue"},
    "app.core.celery_tasks.generate_content": {"queue": "content_queue"},
    "app.core.celery_tasks.generate_image": {"queue": "image_queue"},
    "app.core.celery_tasks.on_generation_complete": {"queue": "content_queue"},
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
)
