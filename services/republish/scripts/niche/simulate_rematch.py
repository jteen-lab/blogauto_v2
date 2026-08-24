"""새 키워드로 기존 제목을 재분류하면 어떻게 되는지 시뮬레이션 — **읽기 전용**.

실제 재분류는 하지 않는다. 오분류·개선 규모만 미리 확인한다.
실행: python3 scripts/niche/simulate_rematch.py
"""
import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

from app.core.database import db_manager  # noqa: E402
from app.models.category import SubTopic, Topic  # noqa: E402
from app.models.title import MainTitle  # noqa: E402
from app.services.category_matcher_service import CategoryMatcherService  # noqa: E402

SAMPLE = 12


async def main() -> None:
    async with db_manager.get_session() as db:
        topics = {t.id: t.name for t in (await db.execute(
            select(Topic).where(Topic.is_deleted == False)  # noqa: E712
        )).scalars().all()}
        subs = {s.id: (s.name, topics.get(s.topic_id, "?")) for s in (await db.execute(
            select(SubTopic).where(SubTopic.is_deleted == False)  # noqa: E712
        )).scalars().all()}

        titles = (await db.execute(select(MainTitle))).scalars().all()
        matcher = CategoryMatcherService(db, user_id=1)

        moves = Counter()
        newly = Counter()
        unmatched = 0
        samples = []

        for t in titles:
            result = await matcher.match_category(t.title)
            before = subs.get(t.subtopic_id, ("(미분류)", "(미분류)"))
            if not result:
                unmatched += 1
                continue
            after = (result["subtopic_name"], result["topic_name"])
            if t.subtopic_id is None:
                newly[f"{after[1]} / {after[0]}"] += 1
                if len(samples) < SAMPLE:
                    samples.append(("신규", t.title[:38], "(미분류)", f"{after[1]}/{after[0]}"))
            elif after != before:
                moves[f"{before[1]}/{before[0]} → {after[1]}/{after[0]}"] += 1
                if len(samples) < SAMPLE:
                    samples.append(("이동", t.title[:38],
                                    f"{before[1]}/{before[0]}", f"{after[1]}/{after[0]}"))

        total = len(titles)
        changed = sum(moves.values())
        print("═" * 74)
        print(f"재분류 시뮬레이션 — 제목 {total}건")
        print("═" * 74)
        print(f"  분류 변경  : {changed}건 ({changed*100//max(total,1)}%)")
        print(f"  신규 분류  : {sum(newly.values())}건 (기존 미분류였던 것)")
        print(f"  매칭 실패  : {unmatched}건")
        print(f"  변화 없음  : {total - changed - sum(newly.values()) - unmatched}건")

        if moves:
            print("\n── 변경 상위 15 ──")
            for path, n in moves.most_common(15):
                print(f"  {n:5}건  {path}")
        if newly:
            print("\n── 신규 분류 상위 10 ──")
            for path, n in newly.most_common(10):
                print(f"  {n:5}건  {path}")
        if samples:
            print("\n── 샘플 ──")
            for kind, title, before, after in samples:
                print(f"  [{kind}] {title}\n         {before} → {after}")
        print("\n※ 실제 데이터는 변경하지 않았습니다(읽기 전용).")


if __name__ == "__main__":
    asyncio.run(main())
