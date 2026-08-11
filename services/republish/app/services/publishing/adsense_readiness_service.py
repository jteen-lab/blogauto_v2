"""애드센스 준비도 감사 (F9, 최소 구현).

작업계획서(docs/plans/adsense_approval_features_plan.md) F9의 최소 구현.
필수 페이지(F1)/저자 프로필(F2)/연락 채널 노출 방식 등 이미 DB에 저장된
신호를 모아 블로그별 요약을 반환한다. 승인 A/B 테스트에서 블로그가 어느
버킷(필수페이지 O/X, E-E-A-T O/X)에 속하는지 한눈에 확인하는 용도로도
쓰인다.

thin content 비율·중복 비율·니치 이탈 여부 등 정량 지표는 별도 집계 로직이
필요해 이번 스코프에서 제외한다(계획서 §3 Phase 3, 수동 체크리스트로 대체
가능 — docs/plans/adsense_prompt_and_growth_profile_proposal.md §3.3).
"""
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.post import Post

PUBLISHED_STATUSES = ("published", "republished")
READY_POST_COUNT = 20


class AdsenseReadinessService:
    """블로그의 애드센스 승인 준비도를 점검한다(F9)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def audit(self, blog: Blog) -> Dict[str, Any]:
        """필수 페이지/저자 프로필/연락 채널/발행량 신호를 모아 반환한다."""
        profile = blog.author_profile or {}
        author_profile_configured = bool(profile.get("name"))
        contact_form_configured = bool(profile.get("contact_form_url"))
        post_count = await self._published_post_count(blog.id)

        checklist = {
            "required_pages": blog.required_pages_status == "complete",
            "author_profile": author_profile_configured,
            "contact_form": contact_form_configured,
            "post_count_20plus": post_count >= READY_POST_COUNT,
        }
        return {
            "blog_id": blog.id,
            "blog_name": blog.name,
            "required_pages_status": blog.required_pages_status,
            "author_profile_configured": author_profile_configured,
            "contact_channel": "form" if contact_form_configured else "email",
            "post_count": post_count,
            "checklist": checklist,
            "checklist_score": sum(1 for ok in checklist.values() if ok),
            "checklist_total": len(checklist),
        }

    async def _published_post_count(self, blog_id: int) -> int:
        """발행 완료(published/republished) 상태 포스트 수."""
        result = await self.db.execute(
            select(func.count(Post.id)).where(
                Post.blog_id == blog_id,
                Post.status.in_(PUBLISHED_STATUSES),
            )
        )
        return result.scalar_one()
