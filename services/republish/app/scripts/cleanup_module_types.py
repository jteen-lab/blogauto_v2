"""
모듈 타입 정리 스크립트

사용자 요청에 따라:
1. 유지할 5개 모듈만 남기고 나머지 삭제
2. "발행 집행" → "발행" 이름 변경
3. 카테고리를 5대 섹션으로 업데이트

유지할 모듈 (5개):
- republish_blog_fetch: 블로그 조회 (collect)
- republish_status_classify: 상태 분류 (utility)
- republish_action_schedule: 액션 스케줄러 (control)
- republish_publish_execute: 발행 (deploy) - 이름 변경
- republish_status_log: 상태 기록 (deploy)
"""
import asyncio
import sys
import os

sys.path.insert(0, '/app')

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://blogauto:blogauto123@db:5432/blogauto_v2"
)

# 유지할 모듈 코드 목록
KEEP_MODULES = [
    "republish_blog_fetch",
    "republish_status_classify",
    "republish_action_schedule",
    "republish_publish_execute",
    "republish_status_log",
]

# 카테고리 매핑
CATEGORY_MAPPING = {
    "republish_blog_fetch": "collect",
    "republish_status_classify": "utility",
    "republish_action_schedule": "control",
    "republish_publish_execute": "deploy",
    "republish_status_log": "deploy",
}

# 이름 변경 매핑
NAME_CHANGES = {
    "republish_publish_execute": "발행",  # "발행 집행" → "발행"
}

# display_order 매핑
DISPLAY_ORDER = {
    "republish_blog_fetch": 1,
    "republish_status_classify": 1,
    "republish_action_schedule": 1,
    "republish_publish_execute": 1,
    "republish_status_log": 2,
}


async def cleanup_module_types():
    """모듈 타입 정리 실행"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, delete

    from app.models.module_type import ModuleType

    print("=" * 60)
    print("🧹 모듈 타입 정리 시작")
    print("=" * 60)
    print(f"\n📋 유지할 모듈: {', '.join(KEEP_MODULES)}")
    print("-" * 60)

    database_url = os.environ.get("DATABASE_URL")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # 1. 현재 모든 모듈 타입 조회
            result = await db.execute(select(ModuleType))
            all_modules = result.scalars().all()
            print(f"\n📊 현재 등록된 모듈 타입: {len(all_modules)}개")

            for m in all_modules:
                print(f"  - {m.code}: {m.name} ({m.category})")

            # 2. 삭제할 모듈 식별
            to_delete = [m for m in all_modules if m.code not in KEEP_MODULES]
            to_keep = [m for m in all_modules if m.code in KEEP_MODULES]

            print(f"\n🗑️  삭제할 모듈: {len(to_delete)}개")
            for m in to_delete:
                print(f"  - {m.code}: {m.name}")

            # 3. 모듈 삭제
            deleted_count = 0
            for m in to_delete:
                await db.delete(m)
                deleted_count += 1
                print(f"  ❌ 삭제됨: {m.code}")

            # 4. 유지할 모듈 업데이트 (카테고리, 이름, display_order)
            print(f"\n✏️  유지 모듈 업데이트: {len(to_keep)}개")
            updated_count = 0
            for m in to_keep:
                changes = []

                # 카테고리 업데이트
                new_category = CATEGORY_MAPPING.get(m.code)
                if new_category and m.category != new_category:
                    old_cat = m.category
                    m.category = new_category
                    changes.append(f"카테고리: {old_cat} → {new_category}")

                # 이름 변경
                new_name = NAME_CHANGES.get(m.code)
                if new_name and m.name != new_name:
                    old_name = m.name
                    m.name = new_name
                    changes.append(f"이름: {old_name} → {new_name}")

                # display_order 업데이트
                new_order = DISPLAY_ORDER.get(m.code)
                if new_order and m.display_order != new_order:
                    m.display_order = new_order
                    changes.append(f"순서: {new_order}")

                if changes:
                    updated_count += 1
                    print(f"  ✅ {m.code}: {', '.join(changes)}")
                else:
                    print(f"  ⏭️  {m.code}: 변경 없음")

            await db.commit()

            print("-" * 60)
            print(f"✅ 완료: {deleted_count}개 삭제, {updated_count}개 업데이트")
            print("=" * 60)

            # 5. 최종 결과 확인
            result = await db.execute(
                select(ModuleType)
                .order_by(ModuleType.category, ModuleType.display_order)
            )
            final_modules = result.scalars().all()

            print("\n📋 최종 모듈 타입 목록:")
            current_category = None
            for m in final_modules:
                if m.category != current_category:
                    current_category = m.category
                    print(f"\n  [{current_category}]")
                print(f"    {m.icon} {m.name} (code: {m.code})")

        except Exception as e:
            await db.rollback()
            print(f"❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(cleanup_module_types())
