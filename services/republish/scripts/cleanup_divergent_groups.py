"""기존 오그룹(핵심어 발산) 일회성 정리 스크립트.

2개 이상 멤버 그룹을 순회하며, 배포된 v3 게이트와 동일 기준(주어 발산:
DF 기반 희소 핵심어 비겹침, DF 없으면 핵심어 발산 폴백)으로 발산 멤버를
그룹에서 해제(group_id=NULL)한다. 지명·주어 케이스를 함께 정리.

- 기준: _diverged(svc, member, representative) == True
- 해제 동작: 앱의 remove_titles_from_group과 동일
  (group_id/similarity_score/grouped_at=NULL, 대표 플래그 해제, member_count 갱신)
- 대표는 유지. 해제된 멤버는 '미그룹'(group_id=NULL)이 되어 이후 재매칭 대상.

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


def _diverged(svc, a: str, b: str) -> bool:
    """배포된 v3 게이트와 동일 판정: 주어 발산 우선, DF 없으면 핵심어 발산 폴백."""
    sd = svc._subject_divergence(a, b)
    return sd if sd is not None else svc._core_divergence(a, b)


async def run(dry_run: bool) -> None:
    """오그룹 정리 실행."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    svc = SimilarityService()

    affected_groups = 0
    ungrouped_total = 0

    async with async_session() as s:
        # 주어 발산 게이트용 코퍼스 DF 주입(배포된 v3 로직과 동일 기준).
        from app.services.token_df_service import TokenDFService
        await TokenDFService.inject(svc, s)

        rows = await s.execute(text(
            """
            SELECT g.id
            FROM title_groups g
            JOIN (
                SELECT group_id, count(*) c FROM main_titles
                WHERE group_id IS NOT NULL GROUP BY group_id HAVING count(*) >= 2
            ) m ON m.group_id = g.id
            ORDER BY g.id
            """
        ))
        group_ids = [r.id for r in rows.fetchall()]
        print(f"[SCAN] 2개+ 멤버 그룹 {len(group_ids)}개 검사")

        for gid in group_ids:
            mem = await s.execute(text(
                """
                SELECT id, title, is_group_representative
                FROM main_titles WHERE group_id = :gid
                ORDER BY is_group_representative DESC, id
                """
            ), {"gid": gid})
            members = mem.fetchall()
            if len(members) < 2:
                continue
            rep = next((x for x in members if x.is_group_representative), members[0])

            to_ungroup = [
                m for m in members
                if m.id != rep.id and _diverged(svc, m.title, rep.title)
            ]
            if not to_ungroup:
                continue

            affected_groups += 1
            print(f"\n[그룹 {gid}] 대표='{rep.title[:34]}' | 해제 {len(to_ungroup)}/{len(members)}")
            for m in to_ungroup:
                print(f"    - {m.title[:46]}")
                if not dry_run:
                    await s.execute(text(
                        """
                        UPDATE main_titles
                        SET group_id = NULL, similarity_score = NULL,
                            grouped_at = NULL, is_group_representative = false
                        WHERE id = :id
                        """
                    ), {"id": m.id})
                ungrouped_total += 1

            if not dry_run:
                await s.execute(text(
                    """
                    UPDATE title_groups
                    SET member_count = (
                        SELECT count(*) FROM main_titles WHERE group_id = :gid
                    )
                    WHERE id = :gid
                    """
                ), {"gid": gid})

        if not dry_run:
            await s.commit()

    await engine.dispose()
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{'=' * 48}")
    print(f"[{mode}] 영향 그룹 {affected_groups}개 | 해제 제목 {ungrouped_total}개")
    if dry_run:
        print("실제 적용하려면 --apply 옵션을 사용하세요.")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="핵심어 발산 오그룹 일회성 정리")
    parser.add_argument("--apply", action="store_true", help="실제 적용(기본 DRY-RUN)")
    args = parser.parse_args()
    asyncio.run(run(dry_run=not args.apply))


if __name__ == "__main__":
    main()
