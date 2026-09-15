"""반영 — 화면에서 고른 결과를 실제 데이터에 넣는다.

**재실행이 아니다.** 반영 단계에서 실행기를 다시 돌리면 AI 가 다른 결과를
만든다. 화면에서 확인한 **바로 그 내용**을 저장한다(계획서 §7).

반영은 올린 것에 따라 갈린다.

    키워드 → 키워드 풀에 채택
    제목   → 제목 재고에 투입(필터·분류 관문을 그대로 태운다)
    글     → 발행대기글 저장, 원하면 즉시 발행까지

계획서: docs/plans/test_workbench_plan.md §7, §9-3
순서도: docs/flowcharts/test_workbench.md §4
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.crawled_post import CrawledPost
from ...models.generation_history import GenerationHistory
from ...models.keyword_candidate import KeywordCandidate

logger = get_logger("workbench_apply", "app.log")

# 발행 기본값은 저장이다. 즉시 발행은 명시로만(계획서 §9-3).
PUBLISH_SAVE = "save"
PUBLISH_NOW = "now"


async def apply_keywords(db: AsyncSession, user_id: int,
                         keywords: List[str],
                         blog_id: Optional[int] = None) -> Dict[str, Any]:
    """고른 키워드를 채택 상태로 풀에 넣는다."""
    added = 0
    for word in keywords or []:
        text = (word or "").strip()
        if not text:
            continue
        db.add(KeywordCandidate(
            user_id=user_id, keyword=text, blog_id=blog_id,
            verdict="adopt", verdict_reason="작업대 반영"))
        added += 1
    await db.commit()
    logger.info("[WORKBENCH] 키워드 반영 %d건", added)
    return {"success": True, "applied": added,
            "message": f"키워드 {added}건을 풀에 채택했습니다"}


async def apply_titles(db: AsyncSession, user_id: int,
                       titles: List[str]) -> Dict[str, Any]:
    """고른 제목을 재고 관문(필터→분류→그룹)에 태워 투입한다.

    관문을 건너뛰고 바로 넣으면 금지어·중복이 그대로 재고가 된다.
    실제 경로가 쓰는 관문을 같은 인자로 부른다.
    """
    from ..keyword_lab.title_gate import TitleGate

    texts = [t.strip() for t in (titles or []) if t and t.strip()]
    if not texts:
        return {"success": False, "message": "반영할 제목이 없습니다"}

    # 분류 실패 시 물려줄 값이 없다는 뜻의 빈 폴백
    fallback = SimpleNamespace(topic_id=None, subtopic_id=None)
    outcome = await TitleGate(db, user_id).admit(texts, fallback,
                                                dry_run=False)
    await db.commit()
    logger.info("[WORKBENCH] 제목 반영 | 투입 %s · 차단 %s · 미분류 %s",
                outcome.get("admitted"), outcome.get("blocked"),
                outcome.get("queued"))
    return {"success": True, **outcome,
            "message": (f"재고 {outcome.get('admitted', 0)}건 투입, "
                        f"차단 {outcome.get('blocked', 0)}건, "
                        f"미분류 {outcome.get('queued', 0)}건")}


async def apply_post(db: AsyncSession, blog_id: int, title: str, html: str,
                     image_url: Optional[str] = None,
                     module_id: Optional[int] = None,
                     mode: str = PUBLISH_SAVE,
                     link_id: Optional[int] = None) -> Dict[str, Any]:
    """확인한 글을 발행대기글로 저장한다. mode="now" 면 발행까지 건다.

    저장 모양은 생성기의 저장부(generator.py 7·8단계)와 같게 맞춘다 —
    source="generated" · published_at 없음이 발행 대상 조건이다.
    """
    text = (title or "").strip()
    body = (html or "").strip()
    if not text or not body:
        return {"success": False, "message": "제목과 본문이 있어야 합니다"}

    history = GenerationHistory(
        blog_id=blog_id, prompt_module_id=module_id,
        recombined_title=text, image_url=image_url,
        content_html=body, content_length=len(body))
    db.add(history)
    await db.flush()

    post = CrawledPost(
        blog_id=blog_id, title=text, source="generated",
        generation_history_id=history.id, match_status="matched",
        match_score=100.0, image_url=image_url, content_html=body)
    db.add(post)
    await db.flush()
    history.crawling_post_id = post.id

    # 추적값은 글 번호가 나온 뒤에야 만들 수 있다. 저장 직후 한 번 갈아
    # 끼운다 — 오퍼와 이어진 링크에만 해당한다.
    body = await _retrack(db, body, link_id, post.id, blog_id)
    post.content_html = body
    history.content_html = body

    await db.commit()

    result: Dict[str, Any] = {
        "success": True, "post_id": post.id,
        "message": "발행대기글로 저장했습니다"}

    if mode == PUBLISH_NOW:
        result.update(await _publish_now(blog_id, post.id))
    logger.info("[WORKBENCH] 글 반영 | blog=%s post=%s mode=%s",
                blog_id, post.id, mode)
    return result


async def _retrack(db: AsyncSession, html: str, link_id: Optional[int],
                   post_id: int, blog_id: int) -> str:
    """버튼 주소에 글 번호를 넣는다. 오퍼가 없으면 그대로 둔다."""
    if not link_id:
        return html
    try:
        from ..promo import link_service

        link = await link_service.load(db, link_id)
        if link is None or not link.cpa_offer_id:
            return html
        url = await link_service.tracked_url(
            db, link, post_id=post_id, blog_id=blog_id)
        if url and link.url and link.url in html:
            return html.replace(link.url, url)
    except Exception as e:  # noqa: BLE001
        logger.warning("[WORKBENCH] 추적값 갱신 실패 | %s", e)
    return html


async def _publish_now(blog_id: int, post_id: int) -> Dict[str, Any]:
    """즉시 발행 — 기존 발행 대기열에 그대로 건다.

    발행 자체는 평소 자동 발행과 같은 길(워커)을 탄다. 여기서 따로
    구현하지 않는다 — 두 길이 생기면 또 갈라진다.
    """
    try:
        from ...core.task_dispatcher import PRIORITY_HIGH, get_dispatcher

        task_id = get_dispatcher().dispatch_publish(
            blog_id, post_id, priority=PRIORITY_HIGH)
        return {"published": "queued", "task_id": task_id,
                "message": "발행 대기열에 올렸습니다 — 잠시 뒤 발행됩니다"}
    except Exception as e:  # noqa: BLE001
        logger.warning("[WORKBENCH] 즉시 발행 실패 | %s", e)
        return {"published": "failed",
                "message": f"저장은 됐지만 발행 대기열 등록 실패: {e}"}
