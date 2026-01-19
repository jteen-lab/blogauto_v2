"""
노드 3: 액션 스케줄러 모듈 (공용)

Features:
- 현재 시간과 활성 시간대 비교
- 마지막 발행 후 간격 검증
- 하루 목표 횟수 기반 간격 계산
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger("action_scheduler")


class ActionScheduler:
    """
    액션 스케줄러 노드

    발행 실행 여부를 시간 기반으로 판단합니다.
    - 현재 시간이 활성 시간대인지 확인
    - 마지막 발행 후 충분한 시간이 경과했는지 확인
    """

    def __init__(
        self,
        schedule_matrix: Optional[list[list[bool]]] = None,
        default_interval_minutes: int = 60
    ):
        """
        Args:
            schedule_matrix: 7일 x 24시간 스케줄 매트릭스
            default_interval_minutes: 기본 발행 간격 (분)
        """
        self.schedule_matrix = schedule_matrix
        self.default_interval_minutes = default_interval_minutes

    def execute(
        self,
        classified_blogs: list[dict[str, Any]],
        current_time: Optional[datetime] = None
    ) -> dict[str, Any]:
        """
        실행 대상 블로그 필터링

        Args:
            classified_blogs: 분류된 블로그 목록 (StatusClassifier 출력)
            current_time: 현재 시간 (테스트용, 기본: datetime.now())

        Returns:
            ActionSchedulerOutput 형식의 딕셔너리
        """
        if current_time is None:
            current_time = datetime.now()

        logger.info(f"[ACTION_SCHEDULER] 시작 | 블로그 수={len(classified_blogs)}")

        # 현재 시간이 활성 시간대인지 확인
        is_active_time = self._is_active_time(current_time)

        if not is_active_time:
            logger.info("[ACTION_SCHEDULER] 비활성 시간대 - 모든 블로그 건너뛰기")
            return self._create_skip_all_output(
                classified_blogs,
                is_active_time,
                skip_reason="비활성 시간대"
            )

        executable_blogs = []
        skipped_blogs = []

        for classified in classified_blogs:
            result = self._evaluate_blog(classified, current_time)

            if result["should_execute"]:
                executable_blogs.append(result)
            else:
                skipped_blogs.append(result)

        logger.info(
            f"[ACTION_SCHEDULER] 완료 | 실행={len(executable_blogs)}, "
            f"건너뛰기={len(skipped_blogs)}"
        )

        return {
            "executable_blogs": executable_blogs,
            "skipped_blogs": skipped_blogs,
            "is_active_time": is_active_time
        }

    def _is_active_time(self, current_time: datetime) -> bool:
        """현재 시간이 활성 시간대인지 확인"""
        if self.schedule_matrix is None:
            # 스케줄 매트릭스가 없으면 항상 활성
            return True

        # 요일 인덱스 (월=0, 일=6)
        day_idx = (current_time.weekday()) % 7
        hour = current_time.hour

        try:
            return self.schedule_matrix[day_idx][hour]
        except (IndexError, TypeError):
            logger.warning("[ACTION_SCHEDULER] 잘못된 스케줄 매트릭스 - 기본 활성 처리")
            return True

    def _evaluate_blog(
        self,
        classified: dict[str, Any],
        current_time: datetime
    ) -> dict[str, Any]:
        """개별 블로그 실행 여부 평가"""
        blog = classified.get("blog", {})
        profile = classified.get("profile", "unknown")
        interval_minutes = classified.get("interval_minutes", self.default_interval_minutes)
        is_eligible = classified.get("is_eligible", True)

        # 재발행 대상이 아닌 경우
        if not is_eligible:
            return self._create_blog_result(
                blog, profile,
                should_execute=False,
                skip_reason=classified.get("skip_reason", "재발행 대상 아님")
            )

        # 마지막 발행 시간 확인
        last_publish_at = blog.get("last_publish_at")
        if last_publish_at:
            if isinstance(last_publish_at, str):
                last_publish_at = datetime.fromisoformat(last_publish_at)

            # 타임존 정보 제거하여 비교 (naive datetime으로 통일)
            if hasattr(last_publish_at, 'tzinfo') and last_publish_at.tzinfo is not None:
                last_publish_at = last_publish_at.replace(tzinfo=None)
            compare_time = current_time.replace(tzinfo=None) if current_time.tzinfo else current_time

            elapsed_minutes = (compare_time - last_publish_at).total_seconds() / 60

            if elapsed_minutes < interval_minutes:
                next_execution = last_publish_at + timedelta(minutes=interval_minutes)
                return self._create_blog_result(
                    blog, profile,
                    should_execute=False,
                    skip_reason=f"간격 미충족 ({int(elapsed_minutes)}/{interval_minutes}분)",
                    next_execution_at=next_execution
                )

        # 실행 대상
        return self._create_blog_result(
            blog, profile,
            should_execute=True,
            next_execution_at=current_time + timedelta(minutes=interval_minutes)
        )

    def _create_blog_result(
        self,
        blog: dict[str, Any],
        profile: str,
        should_execute: bool,
        skip_reason: Optional[str] = None,
        next_execution_at: Optional[datetime] = None
    ) -> dict[str, Any]:
        """블로그 평가 결과 생성"""
        return {
            "blog": blog,
            "profile": profile,
            "should_execute": should_execute,
            "skip_reason": skip_reason,
            "next_execution_at": next_execution_at.isoformat() if next_execution_at else None
        }

    def _create_skip_all_output(
        self,
        classified_blogs: list[dict[str, Any]],
        is_active_time: bool,
        skip_reason: str
    ) -> dict[str, Any]:
        """모든 블로그 건너뛰기 결과 생성"""
        skipped = [
            self._create_blog_result(
                c.get("blog", {}),
                c.get("profile", "unknown"),
                should_execute=False,
                skip_reason=skip_reason
            )
            for c in classified_blogs
        ]

        return {
            "executable_blogs": [],
            "skipped_blogs": skipped,
            "is_active_time": is_active_time
        }

    def calculate_auto_interval(
        self,
        daily_target: int,
        active_hours_per_day: int = 12
    ) -> int:
        """
        일일 목표 횟수에서 간격 계산

        Args:
            daily_target: 하루 목표 발행 횟수
            active_hours_per_day: 하루 활성 시간 (기본: 12시간)

        Returns:
            발행 간격 (분), 최소 15분
        """
        if daily_target <= 0:
            return self.default_interval_minutes

        total_minutes = active_hours_per_day * 60
        interval = total_minutes // daily_target

        return max(15, interval)  # 최소 15분


def create_action_scheduler(
    schedule_matrix: Optional[list[list[bool]]] = None,
    default_interval_minutes: int = 60
) -> ActionScheduler:
    """
    ActionScheduler 인스턴스 생성 팩토리 함수

    Args:
        schedule_matrix: 7일 x 24시간 스케줄 매트릭스
        default_interval_minutes: 기본 발행 간격 (분)

    Returns:
        ActionScheduler 인스턴스
    """
    return ActionScheduler(schedule_matrix, default_interval_minutes)
