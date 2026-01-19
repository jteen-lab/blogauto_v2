"""
분기 실행 오케스트레이터 (Branching Orchestrator)

Features:
- Context Pool 기반 분기 실행
- 하나의 조회 결과를 여러 분류 모듈이 독립적으로 처리
- 모듈별 filtered_queue로 데이터 격리
- 병렬 분기 실행 지원
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .execution_context import (
    ExecutionContext,
    FilteredQueue,
    BlogData,
    create_execution_context
)

# 공용 노드
from shared.modules.blog_fetcher import BlogFetcher
from shared.modules.action_scheduler import ActionScheduler
from shared.modules.status_logger import StatusLogger

# 특화 노드
from .nodes.status_classifier import StatusClassifier
from .nodes.publish_executor import PublishExecutor

logger = logging.getLogger("branching_orchestrator")


class BranchingOrchestrator:
    """
    분기 실행 오케스트레이터

    하나의 BlogFetcher 결과를 여러 분류 모듈이 각자의 조건으로
    필터링하여 독립적인 경로로 실행합니다.

    실행 흐름:
    1. BlogFetcher: 전체 블로그 조회 → original_blog_pool 저장
    2. 각 분류 모듈: original_pool에서 조건에 맞는 블로그 복사
       → filtered_queue_{module_id} 생성
    3. 각 큐별로 독립적인 ActionScheduler → PublishExecutor → StatusLogger
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션
        """
        self.db = db
        self.blog_fetcher = BlogFetcher(db)
        self.status_logger = StatusLogger(db)

    async def execute(
        self,
        flow_id: int,
        user_id: int,
        classifier_modules: list[dict[str, Any]],
        parallel: bool = False
    ) -> dict[str, Any]:
        """
        분기 실행

        Args:
            flow_id: 플로우 ID
            user_id: 사용자 ID
            classifier_modules: 분류 모듈 설정 리스트
                [
                    {
                        "module_id": 1,
                        "module_type": "status_classifier",
                        "post_range_start": 1,
                        "post_range_end": 100,
                        "settings": {...}
                    },
                    ...
                ]
            parallel: 병렬 실행 여부 (기본: False)

        Returns:
            전체 실행 결과 요약
        """
        start_time = time.time()
        logger.info(
            f"[BRANCHING] 분기 실행 시작 | FlowID={flow_id} | "
            f"분류 모듈 수={len(classifier_modules)} | Parallel={parallel}"
        )

        # ExecutionContext 생성
        context = create_execution_context(flow_id, user_id)

        try:
            # ========================================
            # Step 1: 블로그 조회 (공통)
            # ========================================
            logger.info("[BRANCHING] Step 1: 블로그 조회")
            fetcher_output = await self.blog_fetcher.execute(
                flow_id=flow_id,
                user_id=user_id
            )
            blogs = fetcher_output.get("blogs", [])

            if not blogs:
                logger.warning("[BRANCHING] 조회된 블로그 없음")
                return self._create_empty_summary(context, start_time)

            # 원본 풀에 저장
            context.set_original_pool(blogs)

            # ========================================
            # Step 2: 분류 모듈별 큐 생성 및 채우기
            # ========================================
            logger.info("[BRANCHING] Step 2: 분류 모듈별 큐 생성")

            for module_config in classifier_modules:
                self._create_and_populate_queue(context, module_config)

            # ========================================
            # Step 3: 각 큐별 실행
            # ========================================
            logger.info("[BRANCHING] Step 3: 큐별 실행")

            if parallel:
                branch_results = await self._execute_branches_parallel(
                    context, classifier_modules
                )
            else:
                branch_results = await self._execute_branches_sequential(
                    context, classifier_modules
                )

            # 커밋
            await self.db.commit()

            return self._create_summary(
                context, start_time, branch_results
            )

        except Exception as e:
            logger.error(f"[BRANCHING] 실행 오류 | Error={e}")
            await self.db.rollback()
            raise

    def _create_and_populate_queue(
        self,
        context: ExecutionContext,
        module_config: dict[str, Any]
    ) -> FilteredQueue:
        """
        분류 모듈의 큐 생성 및 채우기

        원본 풀에서 조건에 맞는 블로그를 deep copy하여 독립적인 큐 생성
        """
        module_id = module_config["module_id"]
        module_type = module_config.get("module_type", "status_classifier")
        post_range_start = module_config.get("post_range_start")
        post_range_end = module_config.get("post_range_end")

        # 큐 생성
        queue = context.create_filtered_queue(
            module_id=module_id,
            module_type=module_type,
            post_range_start=post_range_start,
            post_range_end=post_range_end
        )

        # 범위 필터링하여 큐 채우기
        context.populate_filtered_queue(module_id)

        logger.info(
            f"[BRANCHING] 큐 생성 완료 | ModuleID={module_id} | "
            f"Range={post_range_start}-{post_range_end} | "
            f"블로그 수={queue.count}"
        )

        return queue

    async def _execute_branches_sequential(
        self,
        context: ExecutionContext,
        classifier_modules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """순차적 분기 실행"""
        results = []

        for module_config in classifier_modules:
            result = await self._execute_single_branch(context, module_config)
            results.append(result)

        return results

    async def _execute_branches_parallel(
        self,
        context: ExecutionContext,
        classifier_modules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """병렬 분기 실행"""
        tasks = [
            self._execute_single_branch(context, module_config)
            for module_config in classifier_modules
        ]
        return await asyncio.gather(*tasks)

    async def _execute_single_branch(
        self,
        context: ExecutionContext,
        module_config: dict[str, Any]
    ) -> dict[str, Any]:
        """
        단일 분기 실행

        1. StatusClassifier로 프로파일 분류
        2. ActionScheduler로 실행 대상 필터링
        3. PublishExecutor로 실행
        4. StatusLogger로 결과 기록
        """
        module_id = module_config["module_id"]
        settings = module_config.get("settings", {})

        branch_start = time.time()
        logger.info(f"[BRANCHING] 분기 실행 시작 | ModuleID={module_id}")

        queue = context.get_filtered_queue(module_id)
        if not queue or queue.count == 0:
            logger.info(f"[BRANCHING] 큐가 비어있음 | ModuleID={module_id}")
            return {
                "module_id": module_id,
                "queue_count": 0,
                "executed_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "results": []
            }

        # 노드 인스턴스 생성
        status_classifier = StatusClassifier()
        action_scheduler = ActionScheduler()
        publish_executor = PublishExecutor(self.db)

        # 모듈 설정 적용
        if settings.get("min_post_count"):
            status_classifier.min_post_count = settings["min_post_count"]
        if settings.get("schedule_matrix"):
            action_scheduler.schedule_matrix = settings["schedule_matrix"]

        results = []
        success_count = 0
        failed_count = 0
        skipped_count = 0

        # Step 1: 상태 분류
        blogs_dict = queue.get_blogs_as_dict()
        classifier_output = status_classifier.execute(
            blogs=blogs_dict,
            module_settings=settings
        )
        classified_blogs = classifier_output.get("classified_blogs", [])

        # Step 2: 액션 스케줄링
        scheduler_output = action_scheduler.execute(
            classified_blogs=classified_blogs
        )
        executable_blogs = scheduler_output.get("executable_blogs", [])
        skipped_blogs = scheduler_output.get("skipped_blogs", [])
        skipped_count = len(skipped_blogs)

        # Step 3 & 4: 발행 및 로깅
        for exec_blog in executable_blogs:
            blog = exec_blog.get("blog", {})
            profile = exec_blog.get("profile", "unknown")

            try:
                publish_result = await publish_executor.execute(
                    selected_post=blog,
                    profile=profile
                )

                await self.status_logger.execute(
                    result=publish_result,
                    flow_id=context.flow_id,
                    user_id=context.user_id,
                    module_id=module_id,
                    save_url_history=settings.get("save_url_history", False)
                )

                results.append(publish_result)

                if publish_result.get("status") == "success":
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(
                    f"[BRANCHING] 블로그 처리 오류 | "
                    f"ModuleID={module_id} | BlogID={blog.get('id')} | "
                    f"Error={e}"
                )
                failed_count += 1
                results.append({
                    "blog_id": blog.get("id"),
                    "blog_name": blog.get("name", "Unknown"),
                    "status": "failed",
                    "error_message": str(e),
                    "executed_at": datetime.now().isoformat()
                })

        # 큐 처리 완료 표시
        queue.processed = True

        branch_time_ms = int((time.time() - branch_start) * 1000)
        logger.info(
            f"[BRANCHING] 분기 실행 완료 | ModuleID={module_id} | "
            f"Success={success_count} | Failed={failed_count} | "
            f"Skipped={skipped_count} | Time={branch_time_ms}ms"
        )

        return {
            "module_id": module_id,
            "queue_count": queue.count,
            "executed_count": len(executable_blogs),
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "execution_time_ms": branch_time_ms,
            "results": results
        }

    def _create_summary(
        self,
        context: ExecutionContext,
        start_time: float,
        branch_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """실행 결과 요약 생성"""
        execution_time_ms = int((time.time() - start_time) * 1000)

        total_executed = sum(r.get("executed_count", 0) for r in branch_results)
        total_success = sum(r.get("success_count", 0) for r in branch_results)
        total_failed = sum(r.get("failed_count", 0) for r in branch_results)
        total_skipped = sum(r.get("skipped_count", 0) for r in branch_results)

        logger.info(
            f"[BRANCHING] 전체 실행 완료 | "
            f"ExecutionID={context.execution_id} | "
            f"Branches={len(branch_results)} | "
            f"Total={total_executed} | Success={total_success} | "
            f"Time={execution_time_ms}ms"
        )

        return {
            "execution_id": context.execution_id,
            "flow_id": context.flow_id,
            "executed_at": datetime.now().isoformat(),
            "original_pool_count": context.original_pool_count,
            "branch_count": len(branch_results),
            "total_executed": total_executed,
            "total_success": total_success,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "branches": branch_results,
            "execution_time_ms": execution_time_ms,
            "context_summary": context.get_summary()
        }

    def _create_empty_summary(
        self,
        context: ExecutionContext,
        start_time: float
    ) -> dict[str, Any]:
        """빈 결과 요약"""
        execution_time_ms = int((time.time() - start_time) * 1000)

        return {
            "execution_id": context.execution_id,
            "flow_id": context.flow_id,
            "executed_at": datetime.now().isoformat(),
            "original_pool_count": 0,
            "branch_count": 0,
            "total_executed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "branches": [],
            "execution_time_ms": execution_time_ms,
            "context_summary": context.get_summary()
        }


async def create_branching_orchestrator(
    db: AsyncSession
) -> BranchingOrchestrator:
    """
    BranchingOrchestrator 팩토리 함수

    Args:
        db: 데이터베이스 세션

    Returns:
        BranchingOrchestrator 인스턴스
    """
    return BranchingOrchestrator(db)


async def execute_branching_flow(
    db: AsyncSession,
    flow_id: int,
    user_id: int,
    classifier_modules: list[dict[str, Any]],
    parallel: bool = False
) -> dict[str, Any]:
    """
    분기 실행 플로우 실행 헬퍼 함수

    사용 예시:
    ```python
    result = await execute_branching_flow(
        db=db,
        flow_id=1,
        user_id=1,
        classifier_modules=[
            {
                "module_id": 101,
                "module_type": "status_classifier",
                "post_range_start": 1,
                "post_range_end": 100,
                "settings": {"min_post_count": 10}
            },
            {
                "module_id": 102,
                "module_type": "status_classifier",
                "post_range_start": 101,
                "post_range_end": 500,
                "settings": {"min_post_count": 10}
            }
        ],
        parallel=True
    )
    ```

    Args:
        db: 데이터베이스 세션
        flow_id: 플로우 ID
        user_id: 사용자 ID
        classifier_modules: 분류 모듈 설정 리스트
        parallel: 병렬 실행 여부

    Returns:
        실행 결과
    """
    orchestrator = await create_branching_orchestrator(db)
    return await orchestrator.execute(
        flow_id=flow_id,
        user_id=user_id,
        classifier_modules=classifier_modules,
        parallel=parallel
    )
