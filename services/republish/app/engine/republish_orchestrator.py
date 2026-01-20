"""
재발행 오케스트레이터

Features:
- 5개 노드를 순차적으로 실행
- 노드 간 데이터 전달 관리
- 전체 실행 흐름 제어
- 기존 RepublishAction 대체
"""
import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

# 공용 노드 (shared/modules)
from shared.modules.blog_fetcher import BlogFetcher
from shared.modules.action_scheduler import ActionScheduler
from shared.modules.status_logger import StatusLogger

# 특화 노드 (engine/nodes)
from .nodes.status_classifier import StatusClassifier
from .nodes.publish_executor import PublishExecutor

logger = logging.getLogger("republish_orchestrator")


class RepublishOrchestrator:
    """
    재발행 오케스트레이터

    5개 노드를 순차적으로 실행하여 재발행 플로우를 완성합니다.

    노드 실행 순서:
    1. BlogFetcher: 블로그 목록 조회
    2. StatusClassifier: 프로파일 분류
    3. ActionScheduler: 실행 대상 필터링
    4. PublishExecutor: 재발행 실행
    5. StatusLogger: 결과 기록
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션
        """
        self.db = db

        # 노드 초기화
        self.blog_fetcher = BlogFetcher(db)
        self.status_classifier = StatusClassifier()
        self.action_scheduler = ActionScheduler()
        self.publish_executor = PublishExecutor(db)
        self.status_logger = StatusLogger(db)

    async def execute(
        self,
        flow_id: int,
        user_id: int,
        module_id: Optional[int] = None,
        module_settings: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        재발행 플로우 실행

        Args:
            flow_id: 플로우 ID
            user_id: 사용자 ID
            module_id: 모듈 ID (선택)
            module_settings: 모듈 설정 (선택)

        Returns:
            RepublishExecutionSummary 형식의 딕셔너리
        """
        start_time = time.time()
        logger.info(
            f"[ORCHESTRATOR] 재발행 플로우 시작 | "
            f"FlowID={flow_id}, UserID={user_id}"
        )

        results = []
        success_count = 0
        failed_count = 0
        skipped_count = 0

        try:
            # ========================================
            # 노드 1: 블로그 조회
            # ========================================
            logger.info("[ORCHESTRATOR] 노드 1: 블로그 조회 시작")

            # 모듈 설정에서 포스트 범위 추출
            post_range_start = None
            post_range_end = None
            if module_settings:
                post_range_start = module_settings.get("post_range_start")
                post_range_end = module_settings.get("post_range_end")
                logger.info(
                    f"[ORCHESTRATOR] 포스트 범위 필터: "
                    f"{post_range_start}~{post_range_end if post_range_end else '무제한'}"
                )

            fetcher_output = await self.blog_fetcher.execute(
                flow_id=flow_id,
                user_id=user_id,
                module_id=module_id,
                post_range_start=post_range_start,
                post_range_end=post_range_end
            )
            blogs = fetcher_output.get("blogs", [])

            if not blogs:
                logger.warning("[ORCHESTRATOR] 조회된 블로그 없음")
                return self._create_summary(
                    flow_id, start_time, 0, 0, 0, 0, []
                )

            # ========================================
            # 노드 2: 상태 분류
            # ========================================
            logger.info("[ORCHESTRATOR] 노드 2: 상태 분류 시작")

            # 모듈 설정 적용
            if module_settings:
                self.status_classifier.min_post_count = module_settings.get(
                    "min_post_count", 10
                )

            classifier_output = self.status_classifier.execute(
                blogs=blogs,
                module_settings=module_settings
            )
            classified_blogs = classifier_output.get("classified_blogs", [])

            # ========================================
            # 노드 3: 액션 스케줄러
            # ========================================
            logger.info("[ORCHESTRATOR] 노드 3: 액션 스케줄러 시작")

            # 스케줄 매트릭스 설정
            if module_settings and module_settings.get("schedule_matrix"):
                self.action_scheduler.schedule_matrix = module_settings["schedule_matrix"]

            scheduler_output = self.action_scheduler.execute(
                classified_blogs=classified_blogs
            )

            executable_blogs = scheduler_output.get("executable_blogs", [])
            skipped_blogs = scheduler_output.get("skipped_blogs", [])
            skipped_count = len(skipped_blogs)

            if not executable_blogs:
                logger.info("[ORCHESTRATOR] 실행 대상 블로그 없음")
                return self._create_summary(
                    flow_id, start_time, len(blogs), 0, 0, skipped_count, []
                )

            # ========================================
            # 노드 4 & 5: 발행 실행 및 기록 (블로그별)
            # ========================================
            for exec_blog in executable_blogs:
                blog = exec_blog.get("blog", {})
                profile = exec_blog.get("profile", "unknown")

                try:
                    # 노드 4: 발행 실행
                    logger.info(f"[ORCHESTRATOR] 노드 4: 발행 실행 | BlogID={blog.get('id')}")
                    publish_result = await self.publish_executor.execute(
                        blog=blog,
                        profile=profile
                    )

                    # 노드 5: 상태 기록
                    logger.info(f"[ORCHESTRATOR] 노드 5: 상태 기록 | BlogID={blog.get('id')}")
                    await self.status_logger.execute(
                        result=publish_result,
                        flow_id=flow_id,
                        user_id=user_id,
                        module_id=module_id,
                        save_url_history=module_settings.get("save_url_history", False) if module_settings else False
                    )

                    results.append(publish_result)

                    if publish_result.get("status") == "success":
                        success_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(
                        f"[ORCHESTRATOR] 블로그 처리 오류 | "
                        f"BlogID={blog.get('id')} | Error={e}"
                    )
                    failed_count += 1
                    results.append({
                        "blog_id": blog.get("id"),
                        "blog_name": blog.get("name", "Unknown"),
                        "status": "failed",
                        "error_message": str(e),
                        "executed_at": datetime.now().isoformat()
                    })

            # 커밋
            await self.db.commit()

            return self._create_summary(
                flow_id, start_time, len(blogs),
                len(executable_blogs), success_count, failed_count + skipped_count, results
            )

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] 플로우 실행 오류 | FlowID={flow_id} | Error={e}")
            await self.db.rollback()
            raise

    def _create_summary(
        self,
        flow_id: int,
        start_time: float,
        total_blogs: int,
        executed_count: int,
        success_count: int,
        skipped_count: int,
        results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """실행 요약 생성"""
        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"[ORCHESTRATOR] 플로우 완료 | FlowID={flow_id} | "
            f"Total={total_blogs}, Executed={executed_count}, "
            f"Success={success_count}, Skipped={skipped_count}, "
            f"Time={execution_time_ms}ms"
        )

        return {
            "flow_id": flow_id,
            "executed_at": datetime.now().isoformat(),
            "total_blogs": total_blogs,
            "executed_count": executed_count,
            "success_count": success_count,
            "failed_count": executed_count - success_count,
            "skipped_count": skipped_count,
            "results": results,
            "execution_time_ms": execution_time_ms
        }


async def create_republish_orchestrator(db: AsyncSession) -> RepublishOrchestrator:
    """
    RepublishOrchestrator 인스턴스 생성 팩토리 함수

    Args:
        db: 데이터베이스 세션

    Returns:
        RepublishOrchestrator 인스턴스
    """
    return RepublishOrchestrator(db)
