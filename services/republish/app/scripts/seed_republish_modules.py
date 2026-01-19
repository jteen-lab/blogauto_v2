"""
재발행 노드 모듈 타입 시드 스크립트

새로 추가된 5개 재발행 노드를 module_types 테이블에 삽입합니다.
"""
import asyncio
import sys
import os

# 경로 설정
sys.path.insert(0, '/app')

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://blogauto:blogauto123@db:5432/blogauto_v2"
)


async def seed_republish_module_types():
    """재발행 노드 모듈 타입 시드"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, text

    from app.models.module_type import ModuleType
    from app.models.module_type_defaults import get_republish_node_types

    print("=" * 60)
    print("🌱 재발행 노드 모듈 타입 시드 시작")
    print("=" * 60)

    database_url = os.environ.get("DATABASE_URL")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # 기존 재발행 노드 확인
            result = await db.execute(
                select(ModuleType).where(ModuleType.code.like('republish_%'))
            )
            existing = {mt.code: mt for mt in result.scalars().all()}

            republish_types = get_republish_node_types()
            created_count = 0
            updated_count = 0

            for type_data in republish_types:
                code = type_data["code"]

                if code in existing:
                    # 업데이트
                    mt = existing[code]
                    for key, value in type_data.items():
                        if key != "code":
                            setattr(mt, key, value)
                    updated_count += 1
                    print(f"  📝 업데이트: {code} ({type_data['name']})")
                else:
                    # 새로 생성
                    mt = ModuleType(**type_data)
                    db.add(mt)
                    created_count += 1
                    print(f"  ➕ 생성: {code} ({type_data['name']})")

            await db.commit()

            print("-" * 60)
            print(f"✅ 완료: {created_count}개 생성, {updated_count}개 업데이트")
            print("=" * 60)

            # 결과 확인
            result = await db.execute(
                select(ModuleType)
                .where(ModuleType.category == 'republish')
                .order_by(ModuleType.display_order)
            )
            republish_modules = result.scalars().all()

            print("\n📋 등록된 재발행 노드 모듈:")
            for mt in republish_modules:
                print(f"  {mt.icon} {mt.name} (code: {mt.code})")

        except Exception as e:
            await db.rollback()
            print(f"❌ 오류 발생: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_republish_module_types())
