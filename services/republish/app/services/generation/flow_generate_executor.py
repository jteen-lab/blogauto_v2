"""
플로우-생성 모듈 실행 서비스

플로우 실행 시 prompt 타입 모듈을 처리합니다.
재고 확인 → 제목 선택 → ContentGenerator 호출 → 결과 반환

설계 문서: generation_module_workplan.md - Phase 4 - 4.2.2
"""
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.module import Module
from ...models.blog import Blog
from .inventory_trigger import InventoryTrigger
from .generator import ContentGenerator
from .flow_execution_context import StageParams

logger = logging.getLogger(__name__)


class FlowGenerateExecutor:
    """
    플로우 내 생성 모듈 실행기

    플로우 실행 시 prompt 타입 모듈에 대해:
    1. 블로그별 재고 확인 (InventoryTrigger)
    2. 사용 가능한 제목 선택
    3. 글 생성 파이프라인 실행 (ContentGenerator)
    """

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.inventory_trigger = InventoryTrigger(db)

    async def execute_for_blog(
        self,
        module: Module,
        blog: Blog,
        stage_params: Optional[StageParams] = None,
    ) -> Dict[str, Any]:
        """
        단일 블로그에 대해 생성 모듈 실행

        Args:
            module: prompt 타입 모듈
            blog: 대상 블로그
            stage_params: GP에서 결정된 스테이지 파라미터 (None이면 기본 임계값 사용)

        Returns:
            dict: 실행 결과
        """
        blog_id = blog.id
        module_id = module.id

        logger.info(
            f"[FLOW_GEN] 시작 | module={module.name} | "
            f"blog={blog.name} (id={blog_id})"
        )

        try:
            # 1. 재고 확인 (GP StageParams 기반)
            min_inventory = None
            growth_stage = "unknown"
            if stage_params:
                min_inventory = stage_params.generate.min_inventory
                growth_stage = stage_params.stage_name

            check_result = await self.inventory_trigger.check_inventory(
                blog_id, min_inventory=min_inventory,
            )
            logger.debug(
                f"[FLOW_GEN] 재고 확인 결과 | blog_id={blog_id} | "
                f"재고={check_result.current_inventory} | "
                f"기준={check_result.threshold} | "
                f"단계={check_result.growth_stage} | "
                f"생성필요={check_result.needs_generation}"
            )

            if not check_result.needs_generation:
                msg = (
                    f"생성 불필요 - 재고: {check_result.current_inventory}/"
                    f"{check_result.threshold} "
                    f"(단계: {check_result.growth_stage})"
                )
                logger.info(f"[FLOW_GEN] {msg}")
                return {
                    "success": True,
                    "message": msg,
                    "skipped": True,
                    "inventory": check_result.current_inventory,
                    "threshold": check_result.threshold,
                }

            # 2. 사용 가능한 제목 확인
            title_id = check_result.available_title_id
            if not title_id:
                msg = "사용 가능한 제목이 없습니다"
                logger.info(f"[FLOW_GEN] {msg}")
                return {
                    "success": True,
                    "message": msg,
                    "skipped": True,
                    "inventory": check_result.current_inventory,
                    "threshold": check_result.threshold,
                }

            logger.info(
                f"[FLOW_GEN] 생성 시작 | title_id={title_id} | "
                f"'{check_result.available_title_text[:30]}...'"
            )

            # 3. ContentGenerator로 글 생성
            module_settings = module.settings or {}
            text_replace_enabled = module_settings.get(
                "substitution", {}
            ).get("text_replace_enabled", True)

            generator = ContentGenerator(self.db, self.user_id)
            gen_result = await generator.generate(
                blog_id=blog_id,
                prompt_module_id=module_id,
                source_title_id=title_id,
                text_replace_enabled=text_replace_enabled,
            )

            if gen_result.success:
                msg = (
                    f"글 생성 완료 | 제목: {gen_result.recombined_title[:30]}... | "
                    f"참조: {gen_result.reference_count}건 | "
                    f"길이: {gen_result.content_length}자 | "
                    f"소요: {gen_result.generation_time_seconds}초"
                )
                logger.info(f"[FLOW_GEN] {msg}")
                return {
                    "success": True,
                    "message": msg,
                    "skipped": False,
                    "post_title": gen_result.recombined_title,
                    "crawling_post_id": gen_result.crawling_post_id,
                    "generation_history_id": gen_result.generation_history_id,
                    "reference_count": gen_result.reference_count,
                    "content_length": gen_result.content_length,
                    "generation_time_seconds": gen_result.generation_time_seconds,
                    "ai_model": gen_result.ai_model_content,
                }
            else:
                msg = f"글 생성 실패: {gen_result.error}"
                logger.warning(f"[FLOW_GEN] {msg}")
                return {
                    "success": False,
                    "message": msg,
                    "skipped": False,
                    "error": gen_result.error,
                }

        except Exception as e:
            msg = f"생성 모듈 실행 오류: {str(e)}"
            logger.error(f"[FLOW_GEN] {msg}")
            return {
                "success": False,
                "message": msg,
                "error": str(e),
            }

    async def execute_for_blogs(
        self,
        module: Module,
        blogs: List[Blog],
        blog_stage_map: Optional[Dict[int, StageParams]] = None,
    ) -> List[Dict[str, Any]]:
        """
        여러 블로그에 대해 순차적으로 생성 모듈 실행

        Args:
            module: prompt 타입 모듈
            blogs: 대상 블로그 목록
            blog_stage_map: {blog_id: StageParams} 매핑 (GP 컨텍스트)

        Returns:
            list: 블로그별 실행 결과 목록
        """
        results = []
        for blog in blogs:
            stage = blog_stage_map.get(blog.id) if blog_stage_map else None
            result = await self.execute_for_blog(
                module, blog, stage_params=stage
            )
            result["blog_id"] = blog.id
            result["blog_name"] = blog.name
            results.append(result)

        # 결과 요약 로그
        success = sum(
            1 for r in results
            if r.get("success") and not r.get("skipped")
        )
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if not r.get("success"))

        logger.info(
            f"[FLOW_GEN] 모듈 '{module.name}' 완료 | "
            f"블로그 {len(blogs)}개: "
            f"생성 {success} / 스킵 {skipped} / 실패 {failed}"
        )

        return results
