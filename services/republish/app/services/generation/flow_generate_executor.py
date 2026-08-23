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
        force: bool = False,
        force_title_id: int = 0,
    ) -> Dict[str, Any]:
        """
        단일 블로그에 대해 생성 모듈 실행

        Args:
            module: prompt 타입 모듈
            blog: 대상 블로그
            stage_params: GP에서 결정된 스테이지 파라미터 (None이면 기본 임계값 사용)
            force: True면 재고 체크 없이 강제 생성 (수동 1회 실행용)
            force_title_id: 디스패치 시 결정된 MainTitle.id. 0이 아니면
                            random 선택을 우회하고 이 ID를 강제 사용한다.
                            큐 등록 → 워커 흐름의 결정성을 보장한다.

        Returns:
            dict: 실행 결과
        """
        blog_id = blog.id
        module_id = module.id

        logger.info(
            f"[FLOW_GEN] 시작 | module={module.name} | "
            f"blog={blog.name} (id={blog_id})"
            f"{' | force=True' if force else ''}"
            f"{f' | force_title_id={force_title_id}' if force_title_id else ''}"
        )

        try:
            module_settings = module.settings or {}
            module_settings = self._filter_categories_for_blog(
                module_settings, blog_id
            )
            # 모듈 통합형 자동 전환: adsense_auto 를 켠 모듈은 블로그의 애드센스
            # 상태에 따라 니치 강제·정보이득이 켜지고 꺼진다(계획서 3.2).
            from .adsense_auto_settings import resolve_for_blog
            module_settings = resolve_for_blog(module_settings, blog)

            # 디스패치 시점에 결정된 title_id가 있으면 그것을 강제 사용.
            # 재고 정책은 블로그별이므로 글로벌 status='used'는 차단하지 않고
            # archived(의도적 보관)와 이 블로그가 이미 만든 제목만 차단한다.
            if force_title_id:
                from app.models.title import MainTitle
                from ...models.crawled_post import CrawledPost
                from sqlalchemy import select as _select
                title = await self.db.get(MainTitle, force_title_id)
                if not title:
                    msg = (
                        f"디스패치 지정 제목(id={force_title_id})이 "
                        f"존재하지 않음"
                    )
                    logger.warning(f"[FLOW_GEN] {msg}")
                    return {
                        "success": True, "message": msg, "skipped": True,
                    }
                if title.status == "archived":
                    msg = (
                        f"디스패치 지정 제목(id={force_title_id})이 "
                        f"archived 상태로 사용 불가"
                    )
                    logger.warning(f"[FLOW_GEN] {msg}")
                    return {
                        "success": True, "message": msg, "skipped": True,
                    }
                # 이 블로그가 이미 만든 제목이면 중복 생성 방지
                dup_check = await self.db.execute(
                    _select(CrawledPost.id).where(
                        CrawledPost.blog_id == blog_id,
                        CrawledPost.source == "generated",
                        CrawledPost.matched_main_title_id == force_title_id,
                    ).limit(1)
                )
                if dup_check.scalar_one_or_none():
                    msg = (
                        f"디스패치 지정 제목(id={force_title_id})은 "
                        f"이 블로그가 이미 사용함 - 중복 생성 방지"
                    )
                    logger.warning(f"[FLOW_GEN] {msg}")
                    return {
                        "success": True, "message": msg, "skipped": True,
                    }
                title_id = title.id
                logger.info(
                    f"[FLOW_GEN] 디스패치 지정 제목 사용 | title_id={title_id} | "
                    f"status={title.status} | '{title.title[:30]}...'"
                )
            elif force:
                # 수동 실행: 재고 체크 없이 모듈 카테고리 기준으로 제목 선택
                title = await self.inventory_trigger._find_available_title(
                    blog_id, module_settings
                )
                if not title:
                    # 카테고리 정보를 스킵 메시지에 포함
                    cat_info = self._get_category_info(module_settings)
                    msg = (
                        f"모듈 카테고리({cat_info}) 일치 제목 없음 "
                        f"- 해당 카테고리의 제목 수집이 필요합니다"
                    )
                    logger.info(f"[FLOW_GEN] {msg} | blog_id={blog_id}")
                    return {
                        "success": True, "message": msg,
                        "skipped": True,
                    }
                title_id = title.id
                logger.info(
                    f"[FLOW_GEN] 강제 생성 | title_id={title_id} | "
                    f"'{title.title[:30]}...'"
                )
            else:
                # 자동 실행: 재고 확인 후 생성 여부 판단
                min_inventory = None
                growth_stage = "unknown"
                if stage_params:
                    min_inventory = stage_params.generate.min_inventory
                    growth_stage = stage_params.stage_name

                check_result = await self.inventory_trigger.check_inventory(
                    blog_id, min_inventory=min_inventory,
                    module_settings=module_settings,
                )
                logger.info(
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

            # 3. ContentGenerator로 글 생성
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

    def _filter_categories_for_blog(
        self, module_settings: dict, blog_id: int
    ) -> dict:
        """
        blog_category_map에서 해당 블로그의 카테고리만 필터링

        blog_category_map이 존재하면 해당 blog_id에 매핑된 카테고리만
        추출하여 module_settings["categories"]를 교체합니다.
        blog_category_map이 없는 레거시 모듈은 기존 categories를 유지합니다.

        Args:
            module_settings: 모듈 설정 딕셔너리
            blog_id: 대상 블로그 ID

        Returns:
            dict: 카테고리가 필터링된 module_settings (원본 변경 없음)
        """
        bcm = module_settings.get("blog_category_map")
        if not bcm:
            return module_settings  # 레거시 호환: 기존 categories 유지

        # 해당 블로그의 카테고리만 추출
        blog_cats = [
            {"topic_id": m["topic_id"], "subtopic_id": m.get("subtopic_id")}
            for m in bcm if m.get("blog_id") == blog_id
        ]

        if not blog_cats:
            return module_settings  # 매핑 없으면 원본 유지

        # 원본 변경 없이 복사 후 categories 교체
        filtered = {**module_settings, "categories": blog_cats}
        logger.debug(
            f"[FLOW_GEN] 블로그별 카테고리 필터 | blog_id={blog_id} | "
            f"카테고리 {len(blog_cats)}개 적용"
        )
        return filtered

    @staticmethod
    def _get_category_info(module_settings: dict) -> str:
        """
        모듈 설정에서 카테고리 정보를 사람이 읽을 수 있는 문자열로 변환

        Args:
            module_settings: 모듈 설정 딕셔너리

        Returns:
            str: "topic:4/subtopic:16,17" 형태의 카테고리 요약
        """
        categories = module_settings.get("categories", [])
        if not categories:
            return "카테고리 미설정"

        topic_ids = set()
        subtopic_ids = set()
        for cat in categories:
            if cat.get("subtopic_id"):
                subtopic_ids.add(cat["subtopic_id"])
            if cat.get("topic_id"):
                topic_ids.add(cat["topic_id"])

        parts = []
        if topic_ids:
            parts.append(f"topic:{','.join(map(str, sorted(topic_ids)))}")
        if subtopic_ids:
            parts.append(
                f"subtopic:{','.join(map(str, sorted(subtopic_ids)))}"
            )
        return "/".join(parts) if parts else "카테고리 미설정"

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
