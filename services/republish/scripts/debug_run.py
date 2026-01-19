#!/usr/bin/env python3
"""
오토런 실행 디버깅 스크립트

오토런 프로세스와 동일한 환경에서 특정 FlowID를 강제 실행하고
결과를 터미널에 상세히 출력합니다.

사용법:
    cd /home/jteen/blogauto_v2/services/republish
    python scripts/debug_run.py <flow_id>

예시:
    python scripts/debug_run.py 1

환경 변수:
    DATABASE_URL: PostgreSQL 연결 문자열 (기본값: 로컬 Docker DB)
"""

import asyncio
import sys
import os
import traceback
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 환경 변수 설정 (로컬 실행용 - Docker 없이 직접 실행 시)
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://blogauto:blogauto@localhost:5432/blogauto_v2"

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import db_manager
from app.models.flow import Flow
from app.models.flow_module import FlowModule
from app.models.flow_blog import FlowBlog
from app.models.module import Module
from app.models.blog import Blog
from app.engine.branching_orchestrator import BranchingOrchestrator


def print_header(title: str):
    """섹션 헤더 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_info(label: str, value):
    """정보 출력"""
    print(f"  {label}: {value}")


async def debug_flow_execution(flow_id: int):
    """
    플로우 실행을 디버깅 모드로 수행
    """
    print_header(f"오토런 디버그 실행 시작 - FlowID: {flow_id}")
    print_info("시작 시간", datetime.now().isoformat())

    try:
        async with db_manager.get_session() as db:
            print_header("1. DB 세션 상태 확인")
            print_info("세션 ID", id(db))
            print_info("세션 활성화", getattr(db, 'is_active', 'unknown'))

            # 플로우 조회
            print_header("2. 플로우 조회")
            query = (
                select(Flow)
                .options(
                    selectinload(Flow.module_links)
                    .selectinload(FlowModule.module)
                    .selectinload(Module.module_type),
                    selectinload(Flow.module_links)
                    .selectinload(FlowModule.module_type),
                    selectinload(Flow.blog_links)
                    .selectinload(FlowBlog.blog)
                    .selectinload(Blog.google_credential)
                )
                .where(Flow.id == flow_id)
            )
            result = await db.execute(query)
            flow = result.scalar_one_or_none()

            if not flow:
                print(f"\n  [ERROR] FlowID={flow_id} 플로우를 찾을 수 없습니다!")
                return

            print_info("플로우 ID", flow.id)
            print_info("플로우 이름", flow.name)
            print_info("사용자 ID", flow.user_id)
            print_info("오토런 활성화", flow.is_in_autorun)
            print_info("플로우 상태", flow.status)

            # 모듈 링크 확인
            print_header("3. 모듈 링크 (flow.module_links) 확인")
            if not flow.module_links:
                print("  [WARNING] module_links가 비어있습니다!")
            else:
                print_info("module_links 개수", len(flow.module_links))
                for idx, link in enumerate(flow.module_links):
                    print(f"\n  --- module_link[{idx}] ---")
                    print_info("  FlowModule ID", link.id)
                    print_info("  module_type_id", link.module_type_id)
                    print_info("  module_id (레거시)", link.module_id)
                    print_info("  is_active", link.is_active)
                    print_info("  execution_order", link.execution_order)
                    print_info("  params", link.params)

                    # module_type 객체 확인
                    if link.module_type:
                        print_info("  module_type.code", link.module_type.code)
                        print_info("  module_type.name", link.module_type.name)
                    else:
                        print("  [WARNING] module_type 객체가 None입니다!")

                    # module 객체 확인 (레거시)
                    if link.module:
                        print_info("  module.name", link.module.name)
                        if link.module.module_type:
                            print_info("  module.module_type.code", link.module.module_type.code)
                    else:
                        print("  [INFO] module 객체가 None (새로운 방식)")

            # 블로그 링크 확인
            print_header("4. 블로그 링크 (flow.blog_links) 확인")
            if not flow.blog_links:
                print("  [WARNING] blog_links가 비어있습니다!")
            else:
                print_info("blog_links 개수", len(flow.blog_links))
                for idx, blog_link in enumerate(flow.blog_links):
                    blog = blog_link.blog
                    if blog:
                        print(f"\n  --- blog[{idx}] ---")
                        print_info("  블로그 ID", blog.id)
                        print_info("  블로그 이름", blog.name)
                        print_info("  플랫폼", blog.platform.value)

            # classifier_modules 구성
            print_header("5. classifier_modules 구성")
            classifier_modules = []
            for link in flow.module_links:
                if not link.is_active:
                    print(f"  [SKIP] FlowModuleID={link.id} - 비활성화됨")
                    continue

                module_type = link.module_type
                module = link.module
                params = link.params or {}

                if module_type:
                    type_code = module_type.code
                elif module and module.module_type:
                    type_code = module.module_type.code
                else:
                    type_code = "status_classifier"
                    print(f"  [WARNING] FlowModuleID={link.id} - module_type 없음, 기본값 사용")

                module_config = {
                    "module_id": link.id,
                    "module_type": type_code,
                    "post_range_start": params.get("post_range_start", 1),
                    "post_range_end": params.get("post_range_end"),
                    "settings": {
                        "min_post_count": params.get("min_post_count", 10),
                        "schedule_matrix": params.get("schedule_matrix"),
                        "save_url_history": params.get("save_url_history", False),
                        **(module.settings if module and module.settings else {}),
                        **(params.get("settings", {}))
                    }
                }
                classifier_modules.append(module_config)
                print(f"  [OK] 추가됨: FlowModuleID={link.id}, type={type_code}")

            print_info("\nclassifier_modules 총 개수", len(classifier_modules))

            if not classifier_modules:
                print("\n  [ERROR] 활성화된 모듈이 없습니다! 실행 불가.")
                return

            # BranchingOrchestrator 실행
            print_header("6. BranchingOrchestrator 실행")
            print_info("시작 시간", datetime.now().isoformat())

            orchestrator = BranchingOrchestrator(db)
            result = await orchestrator.execute(
                flow_id=flow.id,
                user_id=flow.user_id,
                classifier_modules=classifier_modules,
                parallel=False
            )

            print_info("완료 시간", datetime.now().isoformat())

            # 결과 출력
            print_header("7. 실행 결과")
            print_info("execution_id", result.get("execution_id"))
            print_info("총 실행", result.get("total_executed", 0))
            print_info("성공", result.get("total_success", 0))
            print_info("실패", result.get("total_failed", 0))
            print_info("스킵", result.get("total_skipped", 0))
            print_info("소요 시간(ms)", result.get("execution_time_ms", 0))

            # 브랜치별 상세 결과
            branches = result.get("branches", [])
            if branches:
                print_header("8. 브랜치별 상세 결과")
                for idx, branch in enumerate(branches):
                    print(f"\n  --- branch[{idx}] ---")
                    print_info("  module_id", branch.get("module_id"))
                    print_info("  queue_count", branch.get("queue_count"))
                    print_info("  executed_count", branch.get("executed_count"))
                    print_info("  success_count", branch.get("success_count"))
                    print_info("  failed_count", branch.get("failed_count"))

            print_header("디버그 실행 완료")
            success = result.get("total_failed", 0) == 0 and result.get("total_executed", 0) > 0
            print_info("최종 결과", "SUCCESS" if success else "FAILED")

    except Exception as e:
        print_header("ERROR - 실행 중 예외 발생")
        print(f"\n  에러: {e}")
        print(f"\n  Traceback:\n{traceback.format_exc()}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/debug_run.py <flow_id>")
        print("예시: python scripts/debug_run.py 1")
        sys.exit(1)

    try:
        flow_id = int(sys.argv[1])
    except ValueError:
        print(f"오류: flow_id는 정수여야 합니다: {sys.argv[1]}")
        sys.exit(1)

    asyncio.run(debug_flow_execution(flow_id))


if __name__ == "__main__":
    main()
