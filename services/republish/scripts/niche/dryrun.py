"""니치 카테고리 재설계 드라이런 — **읽기 전용**.

실제 DB를 조회해 무엇이 삭제·병합·이동·추가되는지 미리 보여준다.
쓰기 작업은 일절 하지 않는다.

실행: python3 scripts/niche/dryrun.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, select  # noqa: E402

import catalog_spec as SPEC  # noqa: E402
from app.core.database import db_manager  # noqa: E402
from app.models.category import Keyword, SubTopic, Topic  # noqa: E402
from app.models.title import MainTitle  # noqa: E402


def head(title: str) -> None:
    print(f"\n{'─' * 72}\n▌ {title}\n{'─' * 72}")


async def main() -> None:
    async with db_manager.get_session() as db:
        topics = (await db.execute(
            select(Topic).where(Topic.is_deleted == False)  # noqa: E712
        )).scalars().all()
        topic_by_name = {t.name: t for t in topics}

        subs = (await db.execute(
            select(SubTopic).where(SubTopic.is_deleted == False)  # noqa: E712
        )).scalars().all()

        title_counts = dict((await db.execute(
            select(MainTitle.subtopic_id, func.count(MainTitle.id))
            .group_by(MainTitle.subtopic_id)
        )).all())
        kw_counts = dict((await db.execute(
            select(Keyword.subtopic_id, func.count(Keyword.id))
            .where(Keyword.is_deleted == False)  # noqa: E712
            .group_by(Keyword.subtopic_id)
        )).all())

        # ── 1. 삭제 ───────────────────────────────────────────
        head("1. 삭제 대상")
        del_subs = [s for s in subs if s.name in SPEC.DELETE_SUBTOPIC_NAMES]
        blocked = []
        for s in del_subs:
            tc = title_counts.get(s.id, 0)
            topic_name = next(
                (t.name for t in topics if t.id == s.topic_id), "?"
            )
            mark = "⚠️ 제목 있음" if tc else "안전"
            if tc:
                blocked.append(s)
            print(f"  하위주제 [{s.id:3}] {s.name:16} ({topic_name}) "
                  f"제목 {tc}건 · 키워드 {kw_counts.get(s.id, 0)}건 → {mark}")

        del_topics = [t for t in topics if t.name in SPEC.DELETE_TOPIC_NAMES]
        for t in del_topics:
            child = [s for s in subs if s.topic_id == t.id]
            tc = sum(title_counts.get(s.id, 0) for s in child)
            mark = "⚠️ 제목 있음" if tc else "안전"
            print(f"  주제     [{t.id:3}] {t.name:16} "
                  f"하위 {len(child)}개 · 제목 {tc}건 → {mark}")
        print(f"\n  합계: 하위주제 {len(del_subs)}개 · 주제 {len(del_topics)}개 삭제")
        if blocked:
            print(f"  ⚠️ 제목이 연결된 항목 {len(blocked)}개는 적용 시 건너뜁니다")

        # ── 2. 병합 ───────────────────────────────────────────
        head("2. 병합 대상 (제목·키워드를 대상 하위주제로 옮김)")
        for topic_name, from_name, to_name in SPEC.MERGE_SUBTOPICS:
            t = topic_by_name.get(topic_name)
            if not t:
                print(f"  ⚠️ 주제 없음: {topic_name}")
                continue
            cands = [s for s in subs if s.topic_id == t.id
                     and s.name in (from_name, to_name)]
            if len(cands) < 2:
                print(f"  · {topic_name}: '{from_name}' → '{to_name}' "
                      f"— 대상 {len(cands)}개뿐, 병합 불필요")
                continue
            cands.sort(key=lambda s: title_counts.get(s.id, 0), reverse=True)
            keep, *drop = cands
            for d in drop:
                print(f"  · {topic_name}: [{d.id}] {d.name}(제목 {title_counts.get(d.id,0)}) "
                      f"→ [{keep.id}] {keep.name}(제목 {title_counts.get(keep.id,0)})")

        # ── 3. 이동 ───────────────────────────────────────────
        head("3. 이동 대상 (주제 경계 정리)")
        for from_topic, sub_name, to_topic in SPEC.MOVE_SUBTOPICS:
            ft = topic_by_name.get(from_topic)
            s = next((x for x in subs if ft and x.topic_id == ft.id
                      and x.name == sub_name), None)
            if not s:
                print(f"  · {from_topic} / {sub_name} — 없음(건너뜀)")
                continue
            exists = "기존" if to_topic in topic_by_name else "신규 생성"
            print(f"  · [{s.id}] {sub_name}: {from_topic} → {to_topic}({exists}) "
                  f"· 제목 {title_counts.get(s.id,0)}건 이동")

        # ── 4. 신규 니치 ──────────────────────────────────────
        head("4. 신규 니치 등록")
        new_t = new_s = new_k = 0
        for name, spec in SPEC.NEW_NICHES.items():
            exists = name in topic_by_name
            if not exists:
                new_t += 1
            marks = []
            for sub, kws in spec["subtopics"].items():
                new_s += 1
                new_k += len(kws)
                marks.append(f"{sub}({len(kws)})")
            state = "기존 주제에 추가" if exists else "신규"
            body = ", ".join(marks) if marks else "(이동으로 채움)"
            print(f"  · {name} [{state}]: {body}")

        head("5. 기존 주제 심화 (하위주제 분할)")
        for topic_name, subtopics in SPEC.EXPAND_SUBTOPICS.items():
            t = topic_by_name.get(topic_name)
            cur = [s for s in subs if t and s.topic_id == t.id]
            cur_titles = sum(title_counts.get(s.id, 0) for s in cur)
            print(f"  · {topic_name}: 현재 하위주제 {len(cur)}개(제목 {cur_titles}건) "
                  f"→ {len(subtopics)}개 추가")
            for sub, kws in subtopics.items():
                new_s += 1
                new_k += len(kws)
                print(f"      + {sub} (키워드 {len(kws)}개)")

        # ── 6. 키워드 충돌 검사 ───────────────────────────────
        head("6. 키워드 충돌 검사 (기존과 중복되는 신규 키워드)")
        existing_kw = {
            k.name.strip().lower(): k
            for k in (await db.execute(
                select(Keyword).where(Keyword.is_deleted == False)  # noqa: E712
            )).scalars().all()
        }
        sub_name_by_id = {s.id: s.name for s in subs}
        conflicts = []
        for spec_map in (
            {n: v["subtopics"] for n, v in SPEC.NEW_NICHES.items()},
            SPEC.EXPAND_SUBTOPICS,
        ):
            for topic_name, sub_map in spec_map.items():
                for sub, kws in sub_map.items():
                    for kw in kws:
                        hit = existing_kw.get(kw.strip().lower())
                        if hit:
                            conflicts.append(
                                (kw, topic_name, sub,
                                 sub_name_by_id.get(hit.subtopic_id, "?"))
                            )
        if conflicts:
            for kw, tn, sub, old in conflicts:
                print(f"  ⚠️ '{kw}' — 신규({tn}/{sub}) vs 기존({old})")
            print(f"\n  충돌 {len(conflicts)}건: 적용 시 기존 것을 그대로 두고 건너뜁니다")
        else:
            print("  충돌 없음")

        # ── 7. 범용어 단독 키워드 점검 ────────────────────────
        head("7. 기존 범용어 단독 키워드 (니치 제목을 흡수할 위험)")
        GENERIC = {"방법", "정보", "신청", "조건", "비용", "가격", "후기",
                   "종류", "기준", "안내", "정리", "추천", "순위", "차이"}
        risky = [
            k for k in existing_kw.values()
            if "+" not in k.name and k.name.strip() in GENERIC
        ]
        if risky:
            for k in risky:
                print(f"  ⚠️ [{k.id}] '{k.name}' "
                      f"(현재 {sub_name_by_id.get(k.subtopic_id,'?')}, "
                      f"priority={k.priority})")
            print(f"\n  {len(risky)}건 — 조합 형태로 바꾸거나 우선순위를 낮춰야 합니다")
        else:
            print("  범용어 단독 키워드 없음")

        # ── 요약 ──────────────────────────────────────────────
        head("요약")
        print(f"  삭제  : 하위주제 {len(del_subs)}개 · 주제 {len(del_topics)}개")
        print(f"  병합  : {len(SPEC.MERGE_SUBTOPICS)}쌍")
        print(f"  이동  : {len(SPEC.MOVE_SUBTOPICS)}건")
        print(f"  신규  : 주제 {new_t}개 · 하위주제 {new_s}개 · 키워드 {new_k}개")
        print(f"  충돌  : 키워드 {len(conflicts)}건 · 범용어 위험 {len(risky)}건")
        print("\n  ※ 이 스크립트는 아무것도 변경하지 않았습니다(읽기 전용).")
        print("  ※ 다음 단계: 승인 → 적용 → 제목 수집 → 재고 확인 → 블로그 배정")


if __name__ == "__main__":
    asyncio.run(main())
