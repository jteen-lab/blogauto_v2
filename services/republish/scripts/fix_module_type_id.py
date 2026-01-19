#!/usr/bin/env python3
"""
flow_modules 테이블의 module_type_id NULL 레코드 복구 스크립트

문제:
- flow_modules 테이블에 module_type_id가 NULL인 레코드가 있음
- 이로 인해 오토런 실행 시 모듈 타입을 식별할 수 없어 실행이 안 됨

해결:
- module_id를 통해 연결된 Module 테이블의 module_type_id를 참조
- 해당 값으로 flow_modules.module_type_id를 업데이트

사용법:
    cd /home/jteen/blogauto_v2/services/republish
    python scripts/fix_module_type_id.py

    # 드라이런 (실제 업데이트 없이 확인만)
    python scripts/fix_module_type_id.py --dry-run
"""

import asyncio
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 환경 변수 설정 (로컬 실행용)
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://blogauto:blogauto@localhost:5432/blogauto_v2"

from sqlalchemy import select, update, text
from sqlalchemy.orm import selectinload

from app.core.database import db_manager
from app.models.flow_module import FlowModule
from app.models.module import Module


def print_header(title: str):
    """섹션 헤더 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def fix_module_type_ids(dry_run: bool = False):
    """
    flow_modules 테이블의 module_type_id NULL 레코드 복구
    """
    print_header("flow_modules.module_type_id 복구 스크립트")
    print(f"  모드: {'드라이런 (변경 없음)' if dry_run else '실제 업데이트'}")

    try:
        async with db_manager.get_session() as db:
            # 1. 전체 flow_modules 조회
            print_header("1. 전체 flow_modules 조회")

            query = (
                select(FlowModule)
                .options(
                    selectinload(FlowModule.module).selectinload(Module.module_type)
                )
            )
            result = await db.execute(query)
            flow_modules = list(result.scalars().all())

            print(f"  총 flow_modules 레코드: {len(flow_modules)}개")

            # 2. module_type_id가 NULL인 레코드 찾기
            print_header("2. module_type_id가 NULL인 레코드 분석")

            null_records = []
            ok_records = []
            unfixable_records = []

            for fm in flow_modules:
                if fm.module_type_id is not None:
                    ok_records.append(fm)
                    continue

                # module_type_id가 NULL인 경우
                if fm.module and fm.module.module_type_id:
                    # module_id를 통해 복구 가능
                    null_records.append({
                        "flow_module": fm,
                        "new_module_type_id": fm.module.module_type_id,
                        "module_type_code": fm.module.module_type.code if fm.module.module_type else "unknown"
                    })
                else:
                    # 복구 불가능
                    unfixable_records.append(fm)

            print(f"  정상 레코드 (module_type_id 있음): {len(ok_records)}개")
            print(f"  복구 가능 레코드 (NULL → Module에서 유추): {len(null_records)}개")
            print(f"  복구 불가 레코드 (Module 연결 없음): {len(unfixable_records)}개")

            # 3. 복구 가능 레코드 상세 출력
            if null_records:
                print_header("3. 복구 대상 레코드 상세")
                for idx, record in enumerate(null_records):
                    fm = record["flow_module"]
                    print(f"\n  [{idx+1}] FlowModule ID: {fm.id}")
                    print(f"      flow_id: {fm.flow_id}")
                    print(f"      module_id: {fm.module_id}")
                    print(f"      현재 module_type_id: NULL")
                    print(f"      복구할 module_type_id: {record['new_module_type_id']}")
                    print(f"      module_type.code: {record['module_type_code']}")

            # 4. 복구 불가 레코드 출력
            if unfixable_records:
                print_header("4. 복구 불가 레코드 (수동 확인 필요)")
                for fm in unfixable_records:
                    print(f"  - FlowModule ID: {fm.id}, flow_id: {fm.flow_id}, module_id: {fm.module_id}")

            # 5. 업데이트 실행
            if null_records and not dry_run:
                print_header("5. 업데이트 실행")

                updated_count = 0
                for record in null_records:
                    fm = record["flow_module"]
                    fm.module_type_id = record["new_module_type_id"]
                    updated_count += 1
                    print(f"  [OK] FlowModule ID {fm.id} → module_type_id = {record['new_module_type_id']}")

                await db.commit()
                print(f"\n  총 {updated_count}개 레코드 업데이트 완료!")

            elif null_records and dry_run:
                print_header("5. 드라이런 - 업데이트 스킵")
                print(f"  {len(null_records)}개 레코드가 업데이트될 예정입니다.")
                print("  실제 업데이트를 수행하려면 --dry-run 옵션 없이 실행하세요.")

            else:
                print_header("5. 업데이트 불필요")
                print("  복구가 필요한 레코드가 없습니다.")

            # 6. 최종 상태 확인
            print_header("6. 최종 상태 확인")

            # 다시 조회
            result = await db.execute(select(FlowModule))
            all_records = list(result.scalars().all())

            null_count = sum(1 for fm in all_records if fm.module_type_id is None)
            not_null_count = sum(1 for fm in all_records if fm.module_type_id is not None)

            print(f"  총 레코드: {len(all_records)}개")
            print(f"  module_type_id 있음: {not_null_count}개")
            print(f"  module_type_id NULL: {null_count}개")

            if null_count == 0:
                print("\n  [SUCCESS] 모든 레코드가 정상 상태입니다!")
            else:
                print(f"\n  [WARNING] 아직 {null_count}개의 NULL 레코드가 있습니다.")

    except Exception as e:
        import traceback
        print_header("ERROR")
        print(f"  에러: {e}")
        print(f"\n{traceback.format_exc()}")
        return 1

    return 0


def main():
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    exit_code = asyncio.run(fix_module_type_ids(dry_run=dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
