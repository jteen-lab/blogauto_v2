"""기존 오그룹(핵심어/식별자 발산) AI-in-the-loop 정리 스크립트.

2개 이상 멤버 그룹을 순회하며 DF 식별자 발산 게이트로 '후보'를 뽑고,
회색지대 AI(similarity_ai_*)가 '다른 주제'로 확인한 멤버만 그룹에서
해제한다. AI가 '같은 주제'라고 하면 유지(형태소변이/별칭/상위어 공유 등
DF 오탐 구제). AI 비활성/실패 시엔 보수적으로 유지(해제 안 함).

- 후보 기준: _diverged(svc, member, representative) == True (DF 게이트)
- 최종 해제: 후보 && AI가 '다름' 확인
- 해제 동작: 앱의 remove_titles_from_group과 동일
  (group_id/similarity_score/grouped_at=NULL, 대표 플래그 해제, member_count 갱신)

사용:
  python -m scripts.cleanup_divergent_groups            # DRY-RUN(변경 없음)
  python -m scripts.cleanup_divergent_groups --apply    # 실제 적용
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# shared 모듈 경로 추가(Docker/로컬 모두 지원) — services.* 임포트용
for _p in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
        break

from services.similarity_service import SimilarityService  # noqa: E402

_UNGROUP_SQL = text(
    "UPDATE main_titles SET group_id = NULL, similarity_score = NULL, "
    "grouped_at = NULL, is_group_representative = false WHERE id = :id"
)
_RECOUNT_SQL = text(
    "UPDATE title_groups SET member_count = "
    "(SELECT count(*) FROM main_titles WHERE group_id = :gid) WHERE id = :gid"
)


def _diverged(svc, a: str, b: str) -> bool:
    """DF 식별자 발산 게이트(주어 발산 우선, 없으면 핵심어 발산 폴백)."""
    sd = svc._subject_divergence(a, b)
    return sd if sd is not None else svc._core_divergence(a, b)


async def _ai_says_different(db, a: str, b: str, cfg: dict, cache: dict) -> bool:
    """AI가 '다른 주제'라고 하면 True. 실패/판단불가 시 False(보수적 유지)."""
    key = tuple(sorted((a.strip(), b.strip())))
    if key in cache:
        return cache[key]
    diff = False
    try:
        from app.services.ai.ai_service import AIService
        prompt = (
            "두 블로그 글 제목이 사실상 같은 주제·내용을 다루면 '예', "
            "다르면 '아니오'로만 답하세요.\n"
            f"제목1: {a}\n제목2: {b}\n답:"
        )
        ai = AIService(db, user_id=1)
        res = await ai.generate(
            prompt=prompt, provider=(cfg["provider"] or None),
            model=(cfg["model"] or None), max_tokens=8, temperature=0.0,
        )
        txt = ((res or {}).get("content") or "").strip().lower()
        same = txt.startswith(("예", "네", "yes", "y", "true", "1"))
        diff = not same
    except Exception as e:  # noqa: BLE001
        print(f"    ! AI 실패(유지): {e}")
        diff = False
    cache[key] = diff
    return diff


async def _process_group(s, gid, svc, cfg, ai_on, cache, dry_run) -> tuple:
    """한 그룹 처리. Returns (해제수, AI유지수)."""
    rows = (await s.execute(text(
        "SELECT id, title, is_group_representative FROM main_titles "
        "WHERE group_id = :gid ORDER BY is_group_representative DESC, id"
    ), {"gid": gid})).fetchall()
    if len(rows) < 2:
        return 0, 0
    rep = next((x for x in rows if x.is_group_representative), rows[0])

    ungrouped, ai_kept = [], 0
    for m in rows:
        if m.id == rep.id or not _diverged(svc, m.title, rep.title):
            continue
        if ai_on and not await _ai_says_different(s, rep.title, m.title, cfg, cache):
            ai_kept += 1
            print(f"  [그룹 {gid}] ~ AI유지: {m.title[:44]}")
            continue
        ungrouped.append(m)

    if ungrouped:
        print(f"[그룹 {gid}] 대표='{rep.title[:30]}' | 해제 {len(ungrouped)}/{len(rows)}")
        for m in ungrouped:
            print(f"    - {m.title[:46]}")
            if not dry_run:
                await s.execute(_UNGROUP_SQL, {"id": m.id})
        if not dry_run:
            await s.execute(_RECOUNT_SQL, {"gid": gid})
    return len(ungrouped), ai_kept


async def run(dry_run: bool) -> None:
    """오그룹 AI-in-the-loop 정리 실행."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    svc = SimilarityService()
    cache: dict = {}
    ungrouped_total = affected = ai_kept_total = 0

    async with async_session() as s:
        from app.services.token_df_service import TokenDFService
        from app.services.system_settings_service import SystemSettingsService
        await TokenDFService.inject(svc, s)
        ai_on = await SystemSettingsService.get_bool("similarity_ai_enabled", s, False)
        cfg = {
            "provider": (await SystemSettingsService.get("similarity_ai_provider", s, "")) or "",
            "model": (await SystemSettingsService.get("similarity_ai_model", s, "")) or "",
        }
        print(f"[CFG] AI확인={ai_on} provider={cfg['provider']} model={cfg['model']}")

        rows = await s.execute(text(
            "SELECT g.id FROM title_groups g JOIN (SELECT group_id, count(*) c "
            "FROM main_titles WHERE group_id IS NOT NULL GROUP BY group_id "
            "HAVING count(*) >= 2) m ON m.group_id = g.id ORDER BY g.id"
        ))
        group_ids = [r.id for r in rows.fetchall()]
        print(f"[SCAN] 2개+ 멤버 그룹 {len(group_ids)}개 검사")

        for gid in group_ids:
            n_ung, n_kept = await _process_group(s, gid, svc, cfg, ai_on, cache, dry_run)
            ungrouped_total += n_ung
            ai_kept_total += n_kept
            if n_ung:
                affected += 1

        if not dry_run:
            await s.commit()

    await engine.dispose()
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{'=' * 48}")
    print(f"[{mode}] 영향 그룹 {affected}개 | 해제 {ungrouped_total}개 | "
          f"AI유지(오탐구제) {ai_kept_total}개")
    if dry_run:
        print("실제 적용하려면 --apply 옵션을 사용하세요.")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="식별자 발산 오그룹 AI 정리")
    parser.add_argument("--apply", action="store_true", help="실제 적용(기본 DRY-RUN)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=not args.apply))


if __name__ == "__main__":
    main()
