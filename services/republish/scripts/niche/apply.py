"""니치 카테고리 재설계 적용 — **DB 변경**.

드라이런(dryrun.py)에서 확인한 내용을 실제로 반영한다.
멱등: 이미 있는 주제·하위주제·키워드는 건너뛴다(재실행 안전).

실행 전 반드시 백업할 것.
실행: python3 scripts/niche/apply.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

import catalog_spec as SPEC  # noqa: E402
from app.core.database import db_manager  # noqa: E402
from app.models.category import Keyword, SubTopic, Topic  # noqa: E402

USER_ID = 1
stats = {"topic_new": 0, "sub_new": 0, "kw_new": 0,
         "sub_moved": 0, "kw_moved": 0, "kw_renamed": 0, "skipped": 0}


async def get_or_create_topic(db, name: str, description: str = "") -> Topic:
    row = await db.execute(
        select(Topic).where(
            Topic.name == name,
            Topic.user_id == USER_ID,
            Topic.is_deleted == False,  # noqa: E712
        )
    )
    topic = row.scalar_one_or_none()
    if topic:
        return topic
    topic = Topic(user_id=USER_ID, name=name, description=description or None)
    db.add(topic)
    await db.flush()
    stats["topic_new"] += 1
    print(f"  + 주제 생성: {name} (id={topic.id})")
    return topic


async def get_or_create_subtopic(db, topic: Topic, name: str) -> SubTopic:
    row = await db.execute(
        select(SubTopic).where(
            SubTopic.topic_id == topic.id,
            SubTopic.name == name,
            SubTopic.is_deleted == False,  # noqa: E712
        )
    )
    sub = row.scalar_one_or_none()
    if sub:
        return sub
    sub = SubTopic(topic_id=topic.id, name=name)
    db.add(sub)
    await db.flush()
    stats["sub_new"] += 1
    print(f"      + 하위주제: {topic.name} / {name} (id={sub.id})")
    return sub


async def add_keyword(db, sub: SubTopic, name: str, priority: int) -> None:
    """키워드 등록. 이미 존재하면(다른 하위주제 포함) 건너뛴다."""
    row = await db.execute(
        select(Keyword).where(
            Keyword.name == name,
            Keyword.is_deleted == False,  # noqa: E712
        )
    )
    if row.scalar_one_or_none():
        stats["skipped"] += 1
        return
    db.add(Keyword(subtopic_id=sub.id, name=name, priority=priority))
    stats["kw_new"] += 1


async def main() -> None:
    async with db_manager.get_session() as db:
        print("═" * 70)
        print("니치 카테고리 재설계 적용 시작")
        print("═" * 70)

        # ── 1. 신규 니치 (주제 → 하위주제 → 키워드) ──────────
        print("\n[1] 신규 니치 등록")
        for topic_name, spec in SPEC.NEW_NICHES.items():
            topic = await get_or_create_topic(db, topic_name, spec["description"])
            for sub_name, kws in spec["subtopics"].items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.NEW_NICHE_PRIORITY)

        # ── 2. 기존 주제 심화 ────────────────────────────────
        print("\n[2] 기존 주제 심화")
        for topic_name, sub_map in SPEC.EXPAND_SUBTOPICS.items():
            topic = await get_or_create_topic(db, topic_name)
            for sub_name, kws in sub_map.items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.NEW_NICHE_PRIORITY)

        # ── 3. 하위주제 이동 (주제 경계 정리) ────────────────
        print("\n[3] 하위주제 이동")
        for from_topic_name, sub_name, to_topic_name in SPEC.MOVE_SUBTOPICS:
            from_topic = (await db.execute(
                select(Topic).where(
                    Topic.name == from_topic_name,
                    Topic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not from_topic:
                continue
            sub = (await db.execute(
                select(SubTopic).where(
                    SubTopic.topic_id == from_topic.id,
                    SubTopic.name == sub_name,
                    SubTopic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not sub:
                print(f"  · {from_topic_name}/{sub_name} — 없음(건너뜀)")
                continue
            to_topic = await get_or_create_topic(db, to_topic_name)
            sub.topic_id = to_topic.id
            stats["sub_moved"] += 1
            print(f"  → [{sub.id}] {sub_name}: {from_topic_name} → {to_topic_name}")

        # ── 4. 충돌 키워드 이동 ──────────────────────────────
        print("\n[4] 기존 키워드 이동(충돌 해소)")
        for kw_name, topic_name, sub_name in SPEC.MOVE_KEYWORDS:
            kw = (await db.execute(
                select(Keyword).where(
                    Keyword.name == kw_name,
                    Keyword.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not kw:
                print(f"  · '{kw_name}' — 없음(건너뜀)")
                continue
            topic = await get_or_create_topic(db, topic_name)
            sub = await get_or_create_subtopic(db, topic, sub_name)
            if kw.subtopic_id == sub.id:
                continue
            kw.subtopic_id = sub.id
            kw.priority = SPEC.NEW_NICHE_PRIORITY
            stats["kw_moved"] += 1
            print(f"  → '{kw_name}' → {topic_name}/{sub_name}")

        # ── 5. 범용어 단독 키워드 교정 ───────────────────────
        print("\n[5] 범용어 단독 키워드 교정")
        for old_name, new_name in SPEC.RENAME_KEYWORDS:
            kw = (await db.execute(
                select(Keyword).where(
                    Keyword.name == old_name,
                    Keyword.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not kw:
                print(f"  · '{old_name}' — 없음(건너뜀)")
                continue
            kw.name = new_name
            stats["kw_renamed"] += 1
            print(f"  → '{old_name}' → '{new_name}'")

        # ── 6. 정부 정책 정보 → 정부지원금/복지 통합 ────────
        print("\n[6] 정부 정책 정보 통합")
        for from_topic_name, sub_name, to_topic_name, new_name in \
                SPEC.MERGE_SUBTOPIC_INTO_TOPIC:
            from_topic = (await db.execute(
                select(Topic).where(
                    Topic.name == from_topic_name,
                    Topic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not from_topic:
                continue
            sub = (await db.execute(
                select(SubTopic).where(
                    SubTopic.topic_id == from_topic.id,
                    SubTopic.name == sub_name,
                    SubTopic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not sub:
                print(f"  · {from_topic_name}/{sub_name} — 없음(건너뜀)")
                continue
            to_topic = await get_or_create_topic(db, to_topic_name)
            sub.topic_id = to_topic.id
            sub.name = new_name
            stats["sub_moved"] += 1
            print(f"  → [{sub.id}] {sub_name} → {to_topic_name}/{new_name} "
                  f"(제목·키워드 함께 이동)")

        # ── 7. 생활 정보 세분화 ──────────────────────────────
        print("\n[7] 생활 정보 세분화")
        for topic_name, sub_map in SPEC.SPLIT_LIVING_SUBTOPICS.items():
            topic = await get_or_create_topic(db, topic_name)
            for sub_name, kws in sub_map.items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.BROAD_NICHE_PRIORITY)

        # ── 8. 쇼핑/리뷰 키워드 보강 ─────────────────────────
        print("\n[8] 쇼핑/리뷰 키워드 보강(되돌아감 방지)")
        for topic_name, sub_map in SPEC.SHOPPING_KEYWORDS.items():
            topic = await get_or_create_topic(db, topic_name)
            for sub_name, kws in sub_map.items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.NEW_NICHE_PRIORITY)

        # ── 9. 기존 니치 세분화 ──────────────────────────────
        print("\n[9] 기존 니치 세분화")
        for topic_name, sub_map in SPEC.EXPAND_EXISTING.items():
            topic = await get_or_create_topic(db, topic_name)
            for sub_name, kws in sub_map.items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.NEW_NICHE_PRIORITY)

        # ── 10. 범용 조합 키워드 삭제 ────────────────────────
        print("\n[10] 범용 조합 키워드 삭제")
        for kw_name in SPEC.DELETE_GENERIC_KEYWORDS:
            kw = (await db.execute(
                select(Keyword).where(
                    Keyword.name == kw_name,
                    Keyword.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not kw:
                print(f"  · '{kw_name}' — 없음(건너뜀)")
                continue
            kw.soft_delete()
            stats["kw_deleted"] = stats.get("kw_deleted", 0) + 1
            print(f"  − '{kw_name}' 삭제(소프트)")

        # ── 11. 감사 정리: 그림자 키워드 삭제 ────────────────
        print("\n[11] 포함관계로 무력화된 키워드 삭제")
        for kw_name in SPEC.DELETE_SHADOWED_KEYWORDS:
            kw = (await db.execute(
                select(Keyword).where(
                    Keyword.name == kw_name,
                    Keyword.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not kw:
                continue
            kw.soft_delete()
            stats["kw_deleted"] = stats.get("kw_deleted", 0) + 1
            print(f"  − '{kw_name}'")

        # ── 12. 감사 정리: 광범위 키워드 교체 ────────────────
        print("\n[12] 범위가 넓은 키워드 교체")
        for old_name, new_name, topic_name, sub_name in SPEC.REPLACE_BROAD_KEYWORDS:
            kw = (await db.execute(
                select(Keyword).where(
                    Keyword.name == old_name,
                    Keyword.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not kw:
                continue
            topic = await get_or_create_topic(db, topic_name)
            sub = await get_or_create_subtopic(db, topic, sub_name)
            kw.name = new_name
            kw.subtopic_id = sub.id
            stats["kw_renamed"] += 1
            print(f"  → '{old_name}' → '{new_name}' ({topic_name}/{sub_name})")

        # ── 13. 감사 정리: 빈 껍데기 하위주제 삭제 ───────────
        print("\n[13] 빈 하위주제 삭제")
        for topic_name, sub_name in SPEC.DELETE_EMPTY_SUBTOPICS:
            topic = (await db.execute(
                select(Topic).where(
                    Topic.name == topic_name,
                    Topic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not topic:
                continue
            sub = (await db.execute(
                select(SubTopic).where(
                    SubTopic.topic_id == topic.id,
                    SubTopic.name == sub_name,
                    SubTopic.is_deleted == False,  # noqa: E712
                )
            )).scalar_one_or_none()
            if not sub:
                continue
            sub.soft_delete()
            stats["sub_deleted"] = stats.get("sub_deleted", 0) + 1
            print(f"  − {topic_name} / {sub_name}")

        # ── 14. 감사 정리: 부실 키워드 보강 ──────────────────
        print("\n[14] 부실 하위주제 키워드 보강")
        for topic_name, sub_map in SPEC.REINFORCE_KEYWORDS.items():
            topic = await get_or_create_topic(db, topic_name)
            for sub_name, kws in sub_map.items():
                sub = await get_or_create_subtopic(db, topic, sub_name)
                for kw in kws:
                    await add_keyword(db, sub, kw, SPEC.NEW_NICHE_PRIORITY)

        await db.commit()

        print("\n" + "═" * 70)
        print("적용 완료")
        print(f"  신규 주제 {stats['topic_new']} · 하위주제 {stats['sub_new']} "
              f"· 키워드 {stats['kw_new']}")
        print(f"  이동: 하위주제 {stats['sub_moved']} · 키워드 {stats['kw_moved']}")
        print(f"  이름 변경 {stats['kw_renamed']} · 삭제 {stats.get('kw_deleted', 0)} "
              f"· 중복 건너뜀 {stats['skipped']}")
        print(f"  하위주제 삭제 {stats.get('sub_deleted', 0)}")
        print("═" * 70)


if __name__ == "__main__":
    asyncio.run(main())
