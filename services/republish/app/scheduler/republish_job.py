"""
재발행 메인 Job

Features:
- 플로우차트 기반 재발행 로직
- 프로파일별 스케줄 관리
- 자동/수동 비중 전략 적용
- 오류 처리 및 재시도
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db_session
from ..models import Blog, Post, PublishProfile, BlogProfileLink
from ..services.publish_service import PublishService
from ..services.platform_limiter import PlatformLimiter
from ..core.logger import get_logger
from .jitter import calculate_next_run_time

logger = get_logger("republish_job", "republish.log")


async def republish_job():
    """
    메인 재발행 Job

    플로우차트 로직:
    1. DB에서 활성 프로파일-블로그 링크 로드
    2. 각 링크별로 실행 시간 체크
    3. 발행 vs 재발행 결정 (전략 서비스)
    4. 포스트 선택 및 발행/재발행 실행
    5. 다음 실행 시간 업데이트
    """
    async for db in get_db_session():
        try:
            logger.info("[JOB] 재발행 Job 시작")

            # 1. 활성 프로파일-블로그 링크 로드
            active_links = await _load_active_links(db)

            if not active_links:
                logger.info("[JOB] 활성 링크가 없습니다")
                return

            logger.info(f"[JOB] {len(active_links)}개 활성 링크 발견")

            # 2. 각 링크별 처리
            for link in active_links:
                try:
                    await _process_link(db, link)
                except Exception as e:
                    logger.error(f"[JOB] 링크 처리 실패 | 링크ID={link.id} | 오류={e}")

            logger.info("[JOB] 재발행 Job 완료")

        except Exception as e:
            logger.error(f"[JOB] 재발행 Job 전체 실패: {e}")
            raise


async def _load_active_links(db: AsyncSession) -> List[BlogProfileLink]:
    """활성 프로파일-블로그 링크 로드"""
    try:
        current_time = datetime.now()

        query = select(BlogProfileLink).options(
            selectinload(BlogProfileLink.profile),
            selectinload(BlogProfileLink.blog)
        ).where(
            and_(
                BlogProfileLink.is_active == True,
                BlogProfileLink.profile.has(PublishProfile.is_active == True),
                BlogProfileLink.blog.has(Blog.is_active == True),
                # 다음 실행 시간이 현재 시간 이전인 것들
                BlogProfileLink.next_scheduled_at <= current_time
            )
        )

        result = await db.execute(query)
        links = result.scalars().all()

        logger.info(f"[LOAD] {len(links)}개 활성 링크 로드됨")
        return links

    except Exception as e:
        logger.error(f"[LOAD] 활성 링크 로드 실패: {e}")
        raise


async def _process_link(db: AsyncSession, link: BlogProfileLink):
    """개별 링크 처리"""
    try:
        blog = link.blog
        profile = link.profile

        logger.info(f"[PROCESS] 링크 처리 시작 | 블로그={blog.name} | 프로파일={profile.name}")

        # 서비스 초기화
        publish_service = PublishService(db)
        platform_limiter = PlatformLimiter(db)

        # 플랫폼 제한 확인
        can_publish, limit_msg = await platform_limiter.can_publish(
            blog.id, blog.platform.value
        )

        if not can_publish:
            logger.warning(f"[PROCESS] 플랫폼 제한 | 블로그={blog.id} | {limit_msg}")
            # 다음 실행 시간 업데이트 (1시간 후 재시도)
            await _update_next_run_time(db, link, 60)
            return

        # 발행 vs 재발행 결정
        # 현재는 재발행 전용 (발행 프로파일 추가 시 분기 로직 구현 예정)
        action, reason = "republish", "재발행 프로파일"

        logger.info(f"[PROCESS] 전략 결정 | 액션={action} | 이유={reason}")

        # 포스트 선택
        post = await _select_post(db, blog, profile, action)

        if not post:
            logger.warning(f"[PROCESS] 포스트 없음 | 블로그={blog.id} | 액션={action}")
            # 다음 실행 시간 업데이트 (1시간 후 재시도)
            await _update_next_run_time(db, link, 60)
            return

        # 발행/재발행 실행
        if action == "publish":
            result = await publish_service.publish_post(
                blog.user, blog, post, profile.id
            )
        else:  # republish
            result = await publish_service.republish_post(
                blog.user, blog, post, profile.id
            )

        # 실행 결과 기록
        await _record_execution_result(db, link, result)

        # 다음 실행 시간 업데이트
        interval_minutes = profile.calculated_interval_minutes
        await _update_next_run_time(db, link, interval_minutes)

        logger.info(f"[PROCESS] 링크 처리 완료 | 성공={result['success']}")

    except Exception as e:
        logger.error(f"[PROCESS] 링크 처리 실패 | 링크ID={link.id} | 오류={e}")
        # 실패 시에도 다음 실행 시간 업데이트 (30분 후 재시도)
        await _update_next_run_time(db, link, 30)
        raise


async def _select_post(
    db: AsyncSession,
    blog: Blog,
    profile: PublishProfile,
    action: str
) -> Optional[Post]:
    """프로파일 범위에서 포스트 선택"""
    try:
        # 기본 필터
        base_filters = [
            Post.blog_id == blog.id,
            Post.is_deleted == False
        ]

        # 포스트 범위 필터
        if profile.post_range_start:
            base_filters.append(Post.id >= profile.post_range_start)
        if profile.post_range_end:
            base_filters.append(Post.id <= profile.post_range_end)

        if action == "publish":
            # 신규 발행: generated 상태의 포스트
            base_filters.append(Post.status == "generated")

            query = select(Post).where(and_(*base_filters)).limit(1)

        else:  # republish
            # 재발행: published 상태 + 쿨다운 시간 체크
            base_filters.extend([
                Post.status == "published",
                Post.remote_id.isnot(None)
            ])

            # 쿨다운 시간 체크
            if profile.republish_cooldown_hours > 0:
                cooldown_time = datetime.now() - timedelta(
                    hours=profile.republish_cooldown_hours
                )
                base_filters.append(Post.last_published_at <= cooldown_time)

            # 무작위 선택을 위해 ORDER BY RANDOM()
            query = select(Post).where(and_(*base_filters)).order_by(
                Post.random()  # PostgreSQL: random(), SQLite: random()
            ).limit(1)

        result = await db.execute(query)
        post = result.scalar_one_or_none()

        if post:
            logger.info(f"[SELECT] 포스트 선택됨 | ID={post.id} | 제목={post.title[:30]}")
        else:
            logger.warning(f"[SELECT] 선택 가능한 포스트 없음 | 액션={action}")

        return post

    except Exception as e:
        logger.error(f"[SELECT] 포스트 선택 실패: {e}")
        raise


async def _record_execution_result(
    db: AsyncSession,
    link: BlogProfileLink,
    result: Dict[str, Any]
):
    """실행 결과 기록"""
    try:
        link.last_executed_at = datetime.now()

        if result["success"]:
            link.success_count += 1

        link.execution_count += 1

        # 성공률 업데이트 (property로 자동 계산됨)

        await db.commit()

        logger.info(
            f"[RECORD] 실행 결과 기록됨 | 링크ID={link.id} | "
            f"성공률={link.success_rate:.1f}%"
        )

    except Exception as e:
        logger.error(f"[RECORD] 실행 결과 기록 실패: {e}")
        raise


async def _update_next_run_time(
    db: AsyncSession,
    link: BlogProfileLink,
    interval_minutes: int
):
    """다음 실행 시간 업데이트"""
    try:
        profile = link.profile

        # Jitter 적용한 다음 실행 시간 계산
        next_run_time = calculate_next_run_time(
            interval_minutes=interval_minutes,
            jitter_enabled=profile.jitter_enabled,
            jitter_min_percent=profile.jitter_min_percent,
            jitter_max_percent=profile.jitter_max_percent,
            active_start_time=profile.active_start_time,
            active_end_time=profile.active_end_time
        )

        link.next_scheduled_at = next_run_time
        await db.commit()

        logger.info(
            f"[UPDATE] 다음 실행 시간 업데이트됨 | 링크ID={link.id} | "
            f"다음실행={next_run_time}"
        )

    except Exception as e:
        logger.error(f"[UPDATE] 다음 실행 시간 업데이트 실패: {e}")
        raise