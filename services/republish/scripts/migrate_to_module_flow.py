#!/usr/bin/env python3
"""
데이터 마이그레이션 스크립트: Profile/Group → Module/Flow

Purpose:
- 기존 publish_profiles 데이터를 modules로 이전
- 기존 profile_groups 데이터를 flows로 이전
- 기존 group_profile_links 데이터를 flow_modules로 이전
- 기존 blog_group_links 데이터를 flow_blogs로 이전
- is_active 필드를 status 필드로 변환

Usage:
    python scripts/migrate_to_module_flow.py --dry-run  # 시뮬레이션
    python scripts/migrate_to_module_flow.py           # 실제 실행
    python scripts/migrate_to_module_flow.py --rollback # 롤백
"""
import asyncio
import argparse
import sys
import json
from datetime import datetime
from typing import Dict, List, Any

import asyncpg
from sqlalchemy import create_engine, text, select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


class ModuleFlowMigrator:
    """Module/Flow 시스템으로의 데이터 마이그레이션"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.engine = create_async_engine(settings.database_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.stats = {
            "modules_migrated": 0,
            "flows_migrated": 0,
            "flow_modules_migrated": 0,
            "flow_blogs_migrated": 0,
            "errors": []
        }

    async def migrate_data(self) -> bool:
        """데이터 마이그레이션 실행"""
        print("🚀 Module/Flow 시스템 데이터 마이그레이션 시작")
        print(f"📋 모드: {'DRY RUN (시뮬레이션)' if self.dry_run else '실제 실행'}")

        try:
            async with self.async_session() as session:
                # 1. 기존 데이터 검증
                await self._validate_existing_data(session)

                # 2. 프로파일 → 모듈 마이그레이션
                await self._migrate_profiles_to_modules(session)

                # 3. 그룹 → 플로우 마이그레이션
                await self._migrate_groups_to_flows(session)

                # 4. 그룹-프로파일 링크 → 플로우-모듈 링크 마이그레이션
                await self._migrate_group_profile_links(session)

                # 5. 블로그-그룹 링크 → 플로우-블로그 링크 마이그레이션
                await self._migrate_blog_group_links(session)

                if not self.dry_run:
                    await session.commit()
                    print("✅ 데이터 마이그레이션 커밋 완료")
                else:
                    print("🔍 DRY RUN 완료 - 실제 변경사항은 적용되지 않음")

                await self._print_migration_summary()
                return True

        except Exception as e:
            self.stats["errors"].append(f"마이그레이션 실패: {str(e)}")
            print(f"❌ 마이그레이션 오류: {e}")
            return False

    async def _validate_existing_data(self, session: AsyncSession) -> None:
        """기존 데이터 유효성 검증"""
        print("\n📊 기존 데이터 분석...")

        # 프로파일 개수
        result = await session.execute(text("SELECT COUNT(*) FROM publish_profiles"))
        profile_count = result.scalar()
        print(f"   📁 기존 프로파일: {profile_count}개")

        # 그룹 개수
        result = await session.execute(text("SELECT COUNT(*) FROM profile_groups"))
        group_count = result.scalar()
        print(f"   📂 기존 그룹: {group_count}개")

        # 링크 개수
        result = await session.execute(text("SELECT COUNT(*) FROM group_profile_links"))
        link_count = result.scalar()
        print(f"   🔗 그룹-프로파일 링크: {link_count}개")

        result = await session.execute(text("SELECT COUNT(*) FROM blog_group_links"))
        blog_link_count = result.scalar()
        print(f"   🔗 블로그-그룹 링크: {blog_link_count}개")

        if profile_count == 0 and group_count == 0:
            print("⚠️  마이그레이션할 데이터가 없습니다.")

    async def _migrate_profiles_to_modules(self, session: AsyncSession) -> None:
        """프로파일 → 모듈 마이그레이션"""
        print("\n🔄 프로파일 → 모듈 마이그레이션...")

        # republish 모듈 타입 ID 가져오기
        result = await session.execute(
            text("SELECT id FROM module_types WHERE code = 'republish'")
        )
        republish_type_id = result.scalar()
        if not republish_type_id:
            raise ValueError("republish 모듈 타입을 찾을 수 없습니다")

        # 기존 프로파일 조회
        result = await session.execute(text("""
            SELECT id, user_id, name,
                   min_post_count, post_range_start, post_range_end,
                   interval_mode, manual_interval_minutes, auto_daily_count,
                   jitter_enabled, jitter_min_percent, jitter_max_percent,
                   active_hours_start, active_hours_end, blackout_days,
                   cooldown_days, priority, platform_overrides, schedule_matrix,
                   created_at, updated_at
            FROM publish_profiles
            WHERE is_deleted = FALSE OR is_deleted IS NULL
        """))

        profiles = result.fetchall()

        for profile in profiles:
            # schedule_matrix 처리 (TEXT → JSONB)
            schedule_matrix = None
            if profile.schedule_matrix:
                try:
                    # 이미 JSON 문자열인지 확인
                    if isinstance(profile.schedule_matrix, str):
                        schedule_matrix = json.loads(profile.schedule_matrix)
                    else:
                        schedule_matrix = profile.schedule_matrix
                except (json.JSONDecodeError, TypeError):
                    print(f"   ⚠️  프로파일 {profile.id}: schedule_matrix 파싱 실패")

            # blackout_days 처리
            blackout_days = profile.blackout_days or []
            platform_overrides = profile.platform_overrides or {}

            insert_sql = """
                INSERT INTO modules (
                    user_id, module_type_id, name,
                    schedule_matrix, manual_interval_minutes,
                    min_post_count, post_range_start, post_range_end,
                    interval_mode, auto_daily_count,
                    jitter_enabled, jitter_min_percent, jitter_max_percent,
                    active_hours_start, active_hours_end, blackout_days,
                    cooldown_days, priority, platform_overrides,
                    created_at, updated_at
                ) VALUES (
                    :user_id, :module_type_id, :name,
                    :schedule_matrix, :manual_interval_minutes,
                    :min_post_count, :post_range_start, :post_range_end,
                    :interval_mode, :auto_daily_count,
                    :jitter_enabled, :jitter_min_percent, :jitter_max_percent,
                    :active_hours_start, :active_hours_end, :blackout_days,
                    :cooldown_days, :priority, :platform_overrides,
                    :created_at, :updated_at
                ) RETURNING id
            """

            if not self.dry_run:
                result = await session.execute(text(insert_sql), {
                    "user_id": profile.user_id,
                    "module_type_id": republish_type_id,
                    "name": profile.name,
                    "schedule_matrix": json.dumps(schedule_matrix) if schedule_matrix else None,
                    "manual_interval_minutes": profile.manual_interval_minutes,
                    "min_post_count": profile.min_post_count,
                    "post_range_start": profile.post_range_start,
                    "post_range_end": profile.post_range_end,
                    "interval_mode": profile.interval_mode,
                    "auto_daily_count": profile.auto_daily_count,
                    "jitter_enabled": profile.jitter_enabled,
                    "jitter_min_percent": profile.jitter_min_percent,
                    "jitter_max_percent": profile.jitter_max_percent,
                    "active_hours_start": profile.active_hours_start,
                    "active_hours_end": profile.active_hours_end,
                    "blackout_days": json.dumps(blackout_days),
                    "cooldown_days": profile.cooldown_days,
                    "priority": profile.priority,
                    "platform_overrides": json.dumps(platform_overrides),
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at
                })

            self.stats["modules_migrated"] += 1
            print(f"   ✅ 프로파일 {profile.id} → 모듈 변환 완료")

        print(f"✅ 총 {len(profiles)}개 프로파일 → 모듈 마이그레이션 완료")

    async def _migrate_groups_to_flows(self, session: AsyncSession) -> None:
        """그룹 → 플로우 마이그레이션"""
        print("\n🔄 그룹 → 플로우 마이그레이션...")

        # 기존 그룹 조회
        result = await session.execute(text("""
            SELECT id, user_id, name, description, is_active, created_at, updated_at
            FROM profile_groups
        """))

        groups = result.fetchall()

        for group in groups:
            # is_active → status 변환
            status = "active" if group.is_active else "inactive"

            insert_sql = """
                INSERT INTO flows (
                    user_id, name, description, status, created_at, updated_at
                ) VALUES (
                    :user_id, :name, :description, :status, :created_at, :updated_at
                ) RETURNING id
            """

            if not self.dry_run:
                await session.execute(text(insert_sql), {
                    "user_id": group.user_id,
                    "name": group.name,
                    "description": group.description,
                    "status": status,
                    "created_at": group.created_at,
                    "updated_at": group.updated_at
                })

            self.stats["flows_migrated"] += 1
            print(f"   ✅ 그룹 {group.id} → 플로우 변환 완료 (status: {status})")

        print(f"✅ 총 {len(groups)}개 그룹 → 플로우 마이그레이션 완료")

    async def _migrate_group_profile_links(self, session: AsyncSession) -> None:
        """그룹-프로파일 링크 → 플로우-모듈 링크 마이그레이션"""
        print("\n🔄 그룹-프로파일 링크 → 플로우-모듈 링크 마이그레이션...")

        # ID 매핑 테이블 생성
        links_sql = """
            SELECT
                gpl.id, gpl.group_id, gpl.profile_id, gpl.created_at,
                f.id as flow_id, m.id as module_id
            FROM group_profile_links gpl
            JOIN profile_groups pg ON pg.id = gpl.group_id
            JOIN flows f ON f.user_id = pg.user_id AND f.name = pg.name
            JOIN publish_profiles pp ON pp.id = gpl.profile_id
            JOIN modules m ON m.user_id = pp.user_id AND m.name = pp.name
        """

        result = await session.execute(text(links_sql))
        links = result.fetchall()

        for i, link in enumerate(links):
            insert_sql = """
                INSERT INTO flow_modules (
                    flow_id, module_id, execution_order, created_at
                ) VALUES (
                    :flow_id, :module_id, :execution_order, :created_at
                )
            """

            if not self.dry_run:
                await session.execute(text(insert_sql), {
                    "flow_id": link.flow_id,
                    "module_id": link.module_id,
                    "execution_order": i,  # 순서대로 실행 순서 할당
                    "created_at": link.created_at
                })

            self.stats["flow_modules_migrated"] += 1

        print(f"✅ 총 {len(links)}개 그룹-프로파일 링크 → 플로우-모듈 링크 마이그레이션 완료")

    async def _migrate_blog_group_links(self, session: AsyncSession) -> None:
        """블로그-그룹 링크 → 플로우-블로그 링크 마이그레이션"""
        print("\n🔄 블로그-그룹 링크 → 플로우-블로그 링크 마이그레이션...")

        # ID 매핑 테이블 생성
        links_sql = """
            SELECT
                bgl.id, bgl.blog_id, bgl.group_id, bgl.created_at,
                f.id as flow_id
            FROM blog_group_links bgl
            JOIN profile_groups pg ON pg.id = bgl.group_id
            JOIN flows f ON f.user_id = pg.user_id AND f.name = pg.name
        """

        result = await session.execute(text(links_sql))
        links = result.fetchall()

        for link in links:
            insert_sql = """
                INSERT INTO flow_blogs (
                    flow_id, blog_id, created_at
                ) VALUES (
                    :flow_id, :blog_id, :created_at
                )
            """

            if not self.dry_run:
                await session.execute(text(insert_sql), {
                    "flow_id": link.flow_id,
                    "blog_id": link.blog_id,
                    "created_at": link.created_at
                })

            self.stats["flow_blogs_migrated"] += 1

        print(f"✅ 총 {len(links)}개 블로그-그룹 링크 → 플로우-블로그 링크 마이그레이션 완료")

    async def _print_migration_summary(self) -> None:
        """마이그레이션 요약 출력"""
        print("\n" + "="*50)
        print("📋 마이그레이션 요약")
        print("="*50)
        print(f"📁 모듈: {self.stats['modules_migrated']}개")
        print(f"📂 플로우: {self.stats['flows_migrated']}개")
        print(f"🔗 플로우-모듈 링크: {self.stats['flow_modules_migrated']}개")
        print(f"🔗 플로우-블로그 링크: {self.stats['flow_blogs_migrated']}개")

        if self.stats["errors"]:
            print(f"\n⚠️  오류 ({len(self.stats['errors'])}개):")
            for error in self.stats["errors"]:
                print(f"   • {error}")

    async def rollback_migration(self) -> bool:
        """마이그레이션 롤백"""
        print("🔙 Module/Flow 시스템 롤백 시작...")

        try:
            async with self.async_session() as session:
                # 역순으로 데이터 삭제
                await session.execute(text("DELETE FROM flow_blogs"))
                await session.execute(text("DELETE FROM flow_modules"))
                await session.execute(text("DELETE FROM flows"))
                await session.execute(text("DELETE FROM modules"))

                await session.commit()
                print("✅ 롤백 완료")
                return True

        except Exception as e:
            print(f"❌ 롤백 오류: {e}")
            return False

    async def close(self):
        """리소스 정리"""
        await self.engine.dispose()


async def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="Module/Flow 데이터 마이그레이션")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션 모드")
    parser.add_argument("--rollback", action="store_true", help="마이그레이션 롤백")

    args = parser.parse_args()

    migrator = ModuleFlowMigrator(dry_run=args.dry_run)

    try:
        if args.rollback:
            success = await migrator.rollback_migration()
        else:
            success = await migrator.migrate_data()

        sys.exit(0 if success else 1)

    finally:
        await migrator.close()


if __name__ == "__main__":
    asyncio.run(main())