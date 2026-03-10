"""전체 파이프라인 통합 테스트 서비스

PipelineTester의 개별 단계를 순차 실행하여
전체 파이프라인 결과를 조합합니다.
"""
import time
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .pipeline_tester import PipelineTester
from .generator import ContentGenerator

logger = logging.getLogger(__name__)


class FullPipelineTester:
    """전체 파이프라인 통합 테스트 (7단계 순차 실행)"""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self.tester = PipelineTester(db, user_id)

    async def test_full_pipeline(
        self, blog_id: int, module_id: int, dry_run: bool = True,
    ) -> dict:
        """전체 파이프라인 테스트 (7단계)"""
        start = time.time()
        steps = {}

        # Step 1: 제목 선택
        step1 = await self.tester.test_select_title(blog_id, module_id)
        steps["1_select_title"] = self._summarize(step1)
        if not step1["success"]:
            return self._pipeline_result(steps, start, dry_run)

        title_id = step1["result"]["selected_title"]["id"]
        original_title = step1["result"]["selected_title"]["title"]

        # Step 2: 제목 재조합
        step2 = await self.tester.test_recombine_title(
            module_id, blog_id=blog_id, title_id=title_id,
        )
        steps["2_recombine"] = self._summarize(step2)
        working_title = (
            step2["result"]["recombined_title"]
            if step2["success"] else original_title
        )

        # Step 3: 참조자료 수집
        step3 = await self.tester.test_collect_references(
            module_id, working_title, blog_id=blog_id,
        )
        steps["3_references"] = self._summarize(step3)
        ref_text = (
            step3["result"].get("reference_injection", "")
            if step3["success"] else ""
        )

        # Step 4: AI 글 생성 (마크다운)
        step4 = await self.tester.test_generate_content(
            module_id, blog_id, working_title, ref_text,
        )
        steps["4_generate"] = self._summarize(step4)
        content_md = (
            step4["result"].get("content_markdown", "")
            if step4["success"] else ""
        )

        # Step 5: 내부링크 삽입
        if content_md:
            step5 = await self.tester.test_add_internal_links(
                blog_id, module_id, working_title, content_md,
            )
            steps["5_internal_links"] = self._summarize(step5)
            content_with_links = (
                step5["result"].get("content_with_links", content_md)
                if step5["success"] else content_md
            )
        else:
            content_with_links = ""

        # Step 6: 이미지 생성
        step6 = await self.tester.test_generate_image(
            module_id, blog_id, working_title,
        )
        steps["6_image"] = self._summarize(step6)

        # Step 7: 치환 처리 + HTML 변환
        if content_with_links:
            step7 = await self.tester.test_substitution_html(
                blog_id, content_with_links,
            )
            steps["7_substitution"] = self._summarize(step7)

        # dry_run=False면 실제 저장
        saved = False
        if not dry_run and step4["success"]:
            try:
                gen = ContentGenerator(self.db, self.user_id)
                await gen.generate(
                    blog_id=blog_id,
                    prompt_module_id=module_id,
                    source_title_id=title_id,
                )
                saved = True
            except Exception as e:
                logger.error(f"[PIPELINE_TEST] 저장 실패: {e}")

        return self._pipeline_result(steps, start, dry_run, saved)

    def _summarize(self, step_result: dict) -> dict:
        """Step 결과를 전체 파이프라인용으로 축약"""
        summary = {"success": step_result["success"]}
        if not step_result["success"]:
            summary["error"] = step_result.get("error", "실패")
            return summary
        r = step_result.get("result", {})
        step = step_result.get("step", "")
        if step == "select_title":
            sel = r.get("selected_title", {})
            summary.update(
                title_id=sel.get("id"), title=sel.get("title"),
                candidates=r.get("total_candidates", 0),
            )
        elif step == "recombine_title":
            summary.update(
                title=r.get("recombined_title"),
                is_modified=r.get("is_modified"),
            )
        elif step == "collect_references":
            summary["count"] = r.get("total_collected", 0)
        elif step == "generate_content":
            summary.update(
                length=r.get("content_length", 0),
                provider=r.get("ai_provider"),
            )
        elif step == "add_internal_links":
            summary["length"] = r.get("content_length", 0)
        elif step == "generate_image":
            summary.update(
                url=r.get("image_url"), mode=r.get("image_mode"),
            )
        elif step == "substitution_html":
            summary["html_length"] = r.get("html_length", 0)
        return summary

    def _pipeline_result(
        self, steps: dict, start: float,
        dry_run: bool, saved: bool = False,
    ) -> dict:
        """전체 파이프라인 결과 생성"""
        elapsed = int(time.time() - start)
        all_success = all(s.get("success") for s in steps.values())
        return {
            "step": "full_pipeline",
            "success": all_success,
            "dry_run": dry_run,
            "steps": steps,
            "total_time_seconds": elapsed,
            "saved": saved,
        }
