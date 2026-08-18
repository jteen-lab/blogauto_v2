"""문의 수신함 동기화 서비스 (F10 대시보드).

Tally 제출 조회 API(GET /forms/{id}/submissions)를 폴링해 blogauto DB에 저장한다.
blogauto가 바레 IP/HTTP라 webhook 인바운드가 부적합해 폴링을 주 수집 방식으로 채택
(HTTPS 도메인 확보 시 webhook 추가 가능). 순서도 계획서
docs/plans/adsense_inquiry_dashboard_plan.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.contact_submission import ContactSubmission
from .tally_forms_service import TALLY_API_BASE, get_tally_api_key

logger = get_logger("contact_inbox_service", "app.log")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return None


def _resolve_fields(
    questions: Dict[str, str], responses: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """responses(questionId→answer)를 라벨-값 목록으로 변환."""
    out: List[Dict[str, Any]] = []
    for r in responses or []:
        qid = r.get("questionId")
        out.append({
            "label": questions.get(qid, qid or "항목"),
            "value": r.get("answer"),
        })
    return out


async def _fetch_form_submissions(
    client: httpx.AsyncClient, headers: Dict[str, str], form_id: str
) -> List[Dict[str, Any]]:
    """폼의 전체 제출을 (페이지네이션 포함) 파싱해 반환."""
    parsed: List[Dict[str, Any]] = []
    page = 1
    while True:
        resp = await client.get(
            f"{TALLY_API_BASE}/forms/{form_id}/submissions",
            headers=headers, params={"page": page},
        )
        if resp.status_code >= 400:
            logger.error("[F10] 제출 조회 오류 %s | form=%s | %s",
                         resp.status_code, form_id, resp.text[:300])
            break
        data = resp.json()
        questions = {q["id"]: q.get("title", "") for q in data.get("questions", [])}
        for sub in data.get("submissions", []):
            parsed.append({
                "submission_id": sub.get("id"),
                "submitted_at": _parse_dt(sub.get("submittedAt") or sub.get("createdAt")),
                "fields": _resolve_fields(questions, sub.get("responses", [])),
            })
        if not data.get("hasMore"):
            break
        page += 1
        if page > 50:  # 안전 상한
            break
    return parsed


async def sync_blog(db: AsyncSession, blog: Blog, api_key: str) -> int:
    """한 블로그의 새 제출을 저장. 반환: 신규 저장 건수."""
    profile = blog.author_profile or {}
    form_id = profile.get("contact_form_id")
    if not form_id:
        return 0
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        subs = await _fetch_form_submissions(client, headers, form_id)
    if not subs:
        return 0

    ids = [s["submission_id"] for s in subs if s["submission_id"]]
    existing = set((await db.execute(
        select(ContactSubmission.submission_id)
        .where(ContactSubmission.submission_id.in_(ids))
    )).scalars().all())

    new_count = 0
    form_name = f"{blog.name} 문의"
    for s in subs:
        sid = s["submission_id"]
        if not sid or sid in existing:
            continue
        db.add(ContactSubmission(
            blog_id=blog.id, form_id=form_id, submission_id=sid,
            form_name=form_name, submitted_at=s["submitted_at"], fields=s["fields"],
        ))
        new_count += 1
    if new_count:
        await db.commit()
        logger.info("[F10] 문의 동기화 | blog=%s | 신규=%d", blog.name, new_count)
    return new_count


async def sync_all(db: AsyncSession) -> Dict[str, Any]:
    """contact_form_id가 있는 모든 블로그의 제출을 동기화."""
    api_key = await get_tally_api_key(db)
    if not api_key:
        return {"success": False, "message": "Tally API 키 미설정", "new": 0}
    blogs = (await db.execute(select(Blog))).scalars().all()
    targets = [b for b in blogs if (b.author_profile or {}).get("contact_form_id")]
    total_new = 0
    for blog in targets:
        try:
            total_new += await sync_blog(db, blog, api_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("[F10] 동기화 실패 | blog=%s | %s", blog.name, exc)
    return {"success": True, "blogs": len(targets), "new": total_new}
