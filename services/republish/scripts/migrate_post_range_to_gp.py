#!/usr/bin/env python3
"""Phase M: post_range -> Growth Profile 마이그레이션
GP 모듈이 없는 Flow에 balanced GP 모듈을 자동 생성한다.
Usage: python scripts/migrate_post_range_to_gp.py [--dry-run]
"""
import asyncio
import argparse
import json
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.generation.growth_profile_defaults import get_default_profile

# SQL 쿼리 상수
SQL_GP_EXISTS = ("SELECT 1 FROM flow_modules fm JOIN modules m ON m.id = fm.module_id "
                 "WHERE fm.flow_id = :fid AND m.module_type_id = :tid LIMIT 1")
SQL_REPUBLISH_RANGE = (
    "SELECT m.name, m.post_range_start, m.post_range_end FROM flow_modules fm "
    "JOIN modules m ON m.id = fm.module_id JOIN module_types mt ON mt.id = m.module_type_id "
    "WHERE fm.flow_id = :fid AND mt.code = 'republish'")
SQL_INSERT_MODULE = (
    "INSERT INTO modules (user_id, module_type_id, name, settings) "
    "VALUES (:uid, :tid, :name, :settings) RETURNING id")
SQL_SHIFT_ORDER = (
    "UPDATE flow_modules SET execution_order = execution_order + 1 WHERE flow_id = :fid")
SQL_INSERT_FM = (
    "INSERT INTO flow_modules (flow_id, module_id, execution_order) VALUES (:fid, :mid, 0)")


async def migrate(dry_run: bool = False) -> None:
    """GP 모듈이 없는 모든 Flow에 balanced GP 모듈을 생성한다."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    created, skipped = 0, 0

    try:
        async with async_session() as session:
            # GP 모듈 타입 ID 조회
            row = await session.execute(
                text("SELECT id FROM module_types WHERE code = 'growth_profile'"))
            gp_type_id = row.scalar()
            if not gp_type_id:
                print("[ERROR] growth_profile 모듈 타입이 module_types 테이블에 없습니다")
                sys.exit(1)

            # 모든 Flow 조회
            rows = await session.execute(text("SELECT id, user_id, name FROM flows"))
            flows = rows.fetchall()

            for flow in flows:
                # GP 모듈 존재 여부 확인
                exists = await session.execute(
                    text(SQL_GP_EXISTS), {"fid": flow.id, "tid": gp_type_id})
                if exists.scalar():
                    skipped += 1
                    print(f"  [SKIP] Flow #{flow.id} '{flow.name}' - GP 이미 존재")
                    continue

                # 참조용: 재발행 모듈의 post_range 로깅
                rp_rows = await session.execute(
                    text(SQL_REPUBLISH_RANGE), {"fid": flow.id})
                for rp in rp_rows.fetchall():
                    print(f"    [REF] '{rp.name}': range={rp.post_range_start}~{rp.post_range_end}")

                if not dry_run:
                    # GP 모듈 생성 + FlowModule 연결
                    gp_settings = json.dumps(get_default_profile("balanced"))
                    result = await session.execute(text(SQL_INSERT_MODULE), {
                        "uid": flow.user_id, "tid": gp_type_id,
                        "name": "Growth Profile (자동생성)", "settings": gp_settings})
                    mid = result.scalar()
                    await session.execute(text(SQL_SHIFT_ORDER), {"fid": flow.id})
                    await session.execute(text(SQL_INSERT_FM), {"fid": flow.id, "mid": mid})

                created += 1
                tag = "DRY" if dry_run else "OK"
                print(f"  [{tag}] Flow #{flow.id} '{flow.name}' - GP 모듈 생성")

            if not dry_run:
                await session.commit()

            # 결과 통계 출력
            mode = "DRY RUN" if dry_run else "COMPLETE"
            print(f"\n{'='*40}\n[{mode}] Flow 총 {len(flows)}개 | "
                  f"GP 생성: {created}개 | 이미 존재: {skipped}개\n{'='*40}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="post_range -> GP 마이그레이션")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션 모드")
    asyncio.run(migrate(dry_run=parser.parse_args().dry_run))
