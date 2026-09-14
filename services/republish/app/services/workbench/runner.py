"""작업대 실행기 — 실제 발행 길을 그대로 태우고, 반영 전에는 남기지 않는다.

**실제 경로와의 동치**: 오토런 스케줄러의 각 모듈 실행은 아래 서비스로
위임하는 한 줄짜리 메서드다(스케줄러 주석: "수동 화면·플로우와 **같은
실행기**"). 작업대는 그 동일한 서비스를 같은 인자로 부른다. 스케줄러가
얹는 것은 실행 로그·상태 카운터뿐인데, 그건 계획서 §9-1 이 "남기지
않는다"고 정한 것들이다.

    keyword   → KeywordModuleRunner.run          (스케줄러 2251행과 동일)
    title_gen → TitleWorkbench.run_for_module    (스케줄러 2344행과 동일)
    generate  → FlowGenerateExecutor.execute_for_blog (2597행 경유와 동일)
    data      → 스케줄러 인스턴스의 데이터 실행을 그대로 호출

**휘발은 세션이 담당한다**: 모든 실행은 RehearsalSession 위에서 돈다.
실행기 안의 commit 은 flush 로 보류되고, keep=False 면 마지막에 전부
되돌린다. 실행 코드에는 분기가 없다 — 그래서 "테스트는 됐는데 실제는
다르다"가 원리적으로 안 생긴다.

계획서: docs/plans/test_workbench_plan.md §9-1, §10 단계1
순서도: docs/flowcharts/test_workbench.md §2
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.module import Module
from ...models.title import MainTitle
from ..modules.settings_merge import merge as merge_settings
from . import capture
from .session_guard import RehearsalSession, rehearse

logger = get_logger("workbench_runner", "app.log")

SUPPORTED = ("keyword", "title_gen", "generate", "prompt", "data")

# 되돌릴 수 없는 외부 반영 — 작업대가 부르지 않는다(계획서 §9-2)
EXCLUDED = ("contact_form", "republish")

# 체인으로 넘어온 제목으로 생성할 때 회차당 상한. AI 비용 통제.
MAX_CHAIN_POSTS = 3


@dataclass
class RunOutcome:
    """한 번 돌린 결과 — 화면이 그대로 그린다."""

    module_type: str
    success: bool
    message: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)
    captured: Dict[str, Any] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    kept: bool = False
    pending_commits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_type": self.module_type, "success": self.success,
            "message": self.message, "summary": self.summary,
            "captured": self.captured, "counts": self.counts,
            "kept": self.kept, "pending_commits": self.pending_commits,
        }


class WorkbenchRunner:
    """모듈 하나를 리허설로 돌린다."""

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id

    async def run(self, module_type: str, module_id: int,
                  blog_id: Optional[int] = None,
                  settings_override: Optional[dict] = None,
                  title_texts: Optional[List[str]] = None,
                  chain_keywords: Optional[List[str]] = None,
                  keep: bool = False) -> RunOutcome:
        """모듈을 한 번 돌린다.

        Args:
            module_type: keyword | title_gen | generate | prompt | data
            module_id: 불러온 기존 모듈. 그 설정으로 돈다
            blog_id: 대상 블로그(생성은 필수)
            settings_override: 화면에서 켠 기능(최상위 키 단위로 덮음)
            title_texts: 체인·직접 입력 제목 — 있으면 이걸로 생성
            chain_keywords: 앞 단계에서 고른 키워드 — 제목 생성이 이걸
                채택 키워드처럼 쓴다(리허설이라 되돌리면 같이 사라진다)
            keep: True 면 되돌리지 않고 실제 저장(반영 단계가 쓴다)

        Returns:
            RunOutcome — 전량 목록과 집계 포함
        """
        if module_type in EXCLUDED:
            return RunOutcome(module_type, False,
                              message="되돌릴 수 없는 모듈이라 작업대에서 "
                                      "지원하지 않습니다")
        if module_type not in SUPPORTED:
            return RunOutcome(module_type, False,
                              message=f"지원하지 않는 모듈: {module_type}")

        module = await self.db.get(Module, module_id)
        if module is None:
            return RunOutcome(module_type, False,
                              message=f"모듈을 찾을 수 없습니다: {module_id}")
        blog = await self.db.get(Blog, blog_id) if blog_id else None

        settings = merge_settings(module.settings or {},
                                  settings_override or {})
        since = datetime.now(timezone.utc)
        rs = rehearse(self.db)

        try:
            if chain_keywords:
                await self._seed_keywords(rs, chain_keywords, blog)
            outcome = await self._dispatch(
                rs, module_type, module, settings, blog, title_texts, since)
        except Exception as e:  # noqa: BLE001
            logger.error("[WORKBENCH] 실행 오류 | %s | %s", module_type, e)
            await rs.discard()
            return RunOutcome(module_type, False, message=str(e))

        outcome.pending_commits = rs.commit_calls
        if keep:
            await self.db.commit()
            outcome.kept = True
            logger.info("[WORKBENCH] 반영 저장 | %s | 보류분 %d건 확정",
                        module_type, outcome.pending_commits)
        else:
            await rs.discard()
        return outcome

    async def _seed_keywords(self, rs: RehearsalSession,
                             keywords: List[str],
                             blog: Optional[Blog]) -> None:
        """고른 키워드를 채택 상태로 심는다 — 제목 생성이 바로 쓴다.

        리허설 세션에만 있으므로 폐기하면 같이 사라지고, 반영(keep)이면
        실제 풀에 남는다. "골라서 다음 단계로"의 구현이다(계획서 §6).
        """
        from ...models.keyword_candidate import KeywordCandidate

        for word in keywords:
            text = (word or "").strip()
            if not text:
                continue
            rs.add(KeywordCandidate(
                user_id=self.user_id, keyword=text,
                blog_id=blog.id if blog else None,
                verdict="adopt", verdict_reason="작업대 선택"))
        await rs.flush()

    async def _dispatch(self, rs: RehearsalSession, module_type: str,
                        module: Module, settings: dict, blog: Optional[Blog],
                        title_texts: Optional[List[str]],
                        since: datetime) -> RunOutcome:
        """타입별로 실제 실행기를 부른다."""
        if module_type == "keyword":
            from ..keyword_lab.runner import KeywordModuleRunner

            summary = await KeywordModuleRunner(rs, self.user_id).run(
                settings, blog.id if blog else None, force=True)
            captured = await capture.capture_keywords(rs, self.user_id, since)
            return self._outcome(module_type, summary, captured)

        if module_type == "title_gen":
            from ..title_collect.workbench import TitleWorkbench

            # force — 재고 충분 스킵을 우회한다. 작업대는 "돌면 어떻게
            # 되는지"를 보러 오는 자리라 스킵되면 확인할 게 없다.
            summary = await TitleWorkbench(rs, self.user_id).run_for_module(
                settings, [blog] if blog else [], force=True)
            captured = await capture.capture_titles(rs, since)
            return self._outcome(module_type, summary, captured)

        if module_type == "data":
            scheduler = self._scheduler()
            if scheduler is None:
                return RunOutcome(module_type, False,
                                  message="스케줄러가 아직 준비되지 않았습니다")
            probe = Module(id=module.id, name=module.name,
                           user_id=module.user_id, settings=settings)
            summary = await scheduler._execute_data_module(probe, rs)
            captured = await capture.capture_titles(rs, since)
            return self._outcome(module_type, summary, captured)

        # generate / prompt — 글 생성
        if blog is None:
            return RunOutcome(module_type, False,
                              message="글 생성은 블로그를 골라야 합니다")
        return await self._run_generate(rs, module, settings, blog,
                                        title_texts, since)

    async def _run_generate(self, rs: RehearsalSession, module: Module,
                            settings: dict, blog: Blog,
                            title_texts: Optional[List[str]],
                            since: datetime) -> RunOutcome:
        """실제 발행 길(FlowGenerateExecutor)로 글을 만든다.

        체인 제목이 있으면 리허설 세션에 재고 제목으로 넣고 그 id 를 강제
        지정한다 — 되돌리면 제목도 같이 사라진다.
        """
        from ..generation.flow_generate_executor import FlowGenerateExecutor

        probe = Module(id=module.id, name=module.name,
                       user_id=module.user_id, settings=settings)
        executor = FlowGenerateExecutor(rs, self.user_id)
        items: List[dict] = []
        summaries: List[dict] = []

        force_ids: List[int] = [0]
        if title_texts:
            force_ids = []
            for text in title_texts[:MAX_CHAIN_POSTS]:
                row = MainTitle(title=text.strip(), status="available",
                                source="manual")
                rs.add(row)
                await rs.flush()
                force_ids.append(row.id)

        for fid in force_ids:
            summary = await executor.execute_for_blog(
                probe, blog, force=True, force_title_id=fid)
            summaries.append(summary)
            items.append(await self._post_item(rs, summary))

        captured = {"total": len(items), "items": items, "clipped": 0}
        ok = any(s.get("success") for s in summaries)
        return RunOutcome(
            "generate", ok,
            message=summaries[-1].get("message", "") if summaries else "",
            summary={"runs": summaries}, captured=captured,
            counts=capture.summarize(captured))

    async def _post_item(self, rs: RehearsalSession,
                         summary: Dict[str, Any]) -> dict:
        """생성 1건을 화면 항목으로. 본문은 보류 저장분에서 읽는다."""
        item = {
            "kind": "post",
            "text": summary.get("post_title") or "",
            "html": "", "image_url": None,
            "reference_count": summary.get("reference_count", 0),
            "body_chars": summary.get("body_chars", 0),
            "crawling_post_id": summary.get("crawling_post_id"),
            "excluded": not summary.get("success", False),
            "reason": summary.get("error") or (
                summary.get("message") if not summary.get("success") else ""),
        }
        post_id = summary.get("crawling_post_id")
        if post_id:
            from ...models.crawled_post import CrawledPost

            post = await rs.get(CrawledPost, post_id)
            if post is not None:
                item["html"] = post.content_html or ""
                item["image_url"] = post.image_url
        return item

    def _outcome(self, module_type: str, summary: Dict[str, Any],
                 captured: Dict[str, Any]) -> RunOutcome:
        return RunOutcome(
            module_type, bool(summary.get("success")),
            message=summary.get("message") or summary.get("error") or "",
            summary=summary, captured=captured,
            counts=capture.summarize(captured))

    @staticmethod
    def _scheduler():
        from ...scheduler.flow_scheduler import get_flow_scheduler

        return get_flow_scheduler()
