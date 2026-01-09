"""
플로우 엔진

Features:
- 모듈 조합에 따라 동작 실행
- action_type에 따른 액션 분기
- 플로우별 블로그 순회 실행
- 실행 로그 자동 기록
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.flow import Flow
from ..models.blog import Blog
from ..models.module import Module
from ..models.google_credential import GoogleCredential
from ..models.autorun_log import AutorunLog
from .actions.republish import RepublishAction
from ..core.logger import get_logger

logger = get_logger("flow_engine", "republish.log")


class FlowEngine:
    """플로우 엔진 - 모듈 조합에 따라 동작 실행"""

    # 지원하는 액션 타입
    ACTION_TYPES = ["republish"]  # 추후 publish, generate 등 추가

    def __init__(self):
        self.republish_action = RepublishAction()

    async def execute(
        self,
        db: AsyncSession,
        flow: Flow,
        action_type: str,
        target_blog_id: Optional[int] = None,
        log_execution: bool = True
    ) -> Dict[str, Any]:
        """
        플로우 실행

        Args:
            db: 데이터베이스 세션
            flow: 실행할 플로우
            action_type: 액션 타입 (republish, publish, generate 등)
            target_blog_id: 특정 블로그만 실행 (None이면 전체)
            log_execution: 실행 로그 기록 여부 (기본: True)

        Returns:
            실행 결과
        """
        start_time = time.time()

        try:
            logger.info(
                f"[FLOW_ENGINE] Starting | FlowID={flow.id} | "
                f"FlowName={flow.name} | ActionType={action_type}"
            )

            # 액션 타입 검증
            if action_type not in self.ACTION_TYPES:
                logger.error(f"[FLOW_ENGINE] Invalid action type | ActionType={action_type}")
                return {
                    "success": False,
                    "message": f"지원하지 않는 액션 타입: {action_type}",
                    "flow_id": flow.id
                }

            # 해당 액션 타입의 모듈 찾기
            module = await self._find_module_by_action_type(flow, action_type)
            if not module:
                logger.warning(
                    f"[FLOW_ENGINE] No module found | FlowID={flow.id} | ActionType={action_type}"
                )
                return {
                    "success": False,
                    "message": f"플로우에 {action_type} 모듈이 없습니다",
                    "flow_id": flow.id
                }

            # 대상 블로그 목록 조회
            blogs = await self._get_target_blogs(db, flow, target_blog_id)
            if not blogs:
                logger.warning(f"[FLOW_ENGINE] No blogs found | FlowID={flow.id}")
                return {
                    "success": False,
                    "message": "실행할 블로그가 없습니다",
                    "flow_id": flow.id
                }

            # 각 블로그에 대해 액션 실행 및 개별 로그 기록
            results = []
            success_count = 0
            fail_count = 0

            for blog in blogs:
                blog_start = time.time()
                result = await self._execute_action(db, action_type, blog, module)
                blog_duration = int((time.time() - blog_start) * 1000)
                results.append(result)

                is_success = result.get("success", False)
                if is_success:
                    success_count += 1
                else:
                    fail_count += 1

                # 개별 실행 로그 기록 (간결한 포맷)
                if log_execution and flow.user_id:
                    await self._create_compact_log(
                        db=db,
                        user_id=flow.user_id,
                        flow_id=flow.id,
                        flow_name=flow.name,
                        module_name=module.name if module else None,
                        blog_name=blog.name,
                        action_type=action_type,
                        result=result,
                        duration_ms=blog_duration
                    )

            # 전체 실행 시간 계산
            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"[FLOW_ENGINE] Completed | FlowID={flow.id} | "
                f"Success={success_count} | Fail={fail_count} | Duration={duration_ms}ms"
            )

            return {
                "success": fail_count == 0,
                "message": f"실행 완료 (성공: {success_count}, 실패: {fail_count})",
                "flow_id": flow.id,
                "flow_name": flow.name,
                "action_type": action_type,
                "total": len(blogs),
                "success_count": success_count,
                "fail_count": fail_count,
                "results": results,
                "executed_at": datetime.now().isoformat(),
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[FLOW_ENGINE] Error | FlowID={flow.id} | Error={e}")

            # 오류 로그 기록
            if log_execution and flow.user_id:
                await self._create_error_log(
                    db=db,
                    user_id=flow.user_id,
                    flow_id=flow.id,
                    flow_name=flow.name,
                    error_message=str(e)
                )

            return {
                "success": False,
                "message": f"플로우 실행 오류: {e}",
                "flow_id": flow.id
            }

    async def _find_module_by_action_type(
        self,
        flow: Flow,
        action_type: str
    ) -> Optional[Module]:
        """액션 타입에 해당하는 모듈 찾기"""
        for link in flow.module_links:
            module = link.module
            if module and module.module_type:
                # 모듈 타입 코드와 액션 타입 매칭
                if module.module_type.code == action_type:
                    return module
        return None

    async def _get_target_blogs(
        self,
        db: AsyncSession,
        flow: Flow,
        target_blog_id: Optional[int] = None
    ) -> List[Blog]:
        """실행 대상 블로그 목록 조회"""
        blogs = []

        for link in flow.blog_links:
            blog = link.blog
            if blog and blog.is_active and not blog.is_deleted:
                # 특정 블로그 지정 시 필터링
                if target_blog_id and blog.id != target_blog_id:
                    continue
                blogs.append(blog)

        return blogs

    async def _execute_action(
        self,
        db: AsyncSession,
        action_type: str,
        blog: Blog,
        module: Module
    ) -> Dict[str, Any]:
        """액션 실행"""
        try:
            # Blogger의 경우 Google 인증 정보 조회
            credential = None
            if blog.is_blogger and blog.google_credential_id:
                query = select(GoogleCredential).where(
                    GoogleCredential.id == blog.google_credential_id
                )
                result = await db.execute(query)
                credential = result.scalar_one_or_none()

                if not credential:
                    logger.warning(
                        f"[FLOW_ENGINE] No credential found | BlogID={blog.id}"
                    )
                    return {
                        "success": False,
                        "message": "Google 인증 정보를 찾을 수 없습니다",
                        "blog_id": blog.id,
                        "blog_name": blog.name
                    }

            # 액션 타입별 실행
            if action_type == "republish":
                return await self.republish_action.execute(blog, module, credential)

            # 추후 다른 액션 타입 추가
            # elif action_type == "publish":
            #     return await self.publish_action.execute(blog, module)

            return {
                "success": False,
                "message": f"구현되지 않은 액션: {action_type}",
                "blog_id": blog.id
            }

        except Exception as e:
            logger.error(
                f"[FLOW_ENGINE] Action error | BlogID={blog.id} | "
                f"Action={action_type} | Error={e}"
            )
            return {
                "success": False,
                "message": f"액션 실행 오류: {e}",
                "blog_id": blog.id,
                "blog_name": blog.name
            }

    async def test_connection(
        self,
        db: AsyncSession,
        blog: Blog
    ) -> Dict[str, Any]:
        """
        블로그 연결 테스트

        Args:
            db: 데이터베이스 세션
            blog: 테스트할 블로그

        Returns:
            테스트 결과
        """
        try:
            # Blogger의 경우 Google 인증 정보 조회
            credential = None
            if blog.is_blogger and blog.google_credential_id:
                query = select(GoogleCredential).where(
                    GoogleCredential.id == blog.google_credential_id
                )
                result = await db.execute(query)
                credential = result.scalar_one_or_none()

            return await self.republish_action.test_connection(blog, credential)

        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Connection test error | BlogID={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"연결 테스트 오류: {e}"
            }

    async def _create_compact_log(
        self,
        db: AsyncSession,
        user_id: int,
        flow_id: int,
        flow_name: str,
        module_name: str,
        blog_name: str,
        action_type: str,
        result: Dict[str, Any],
        duration_ms: int
    ) -> None:
        """
        간결한 로그 생성
        포맷: [플로우명][모듈명]-[포스트 제목][재발행 시간][처리 결과]
        """
        try:
            is_success = result.get("success", False)
            status = "success" if is_success else "failed"

            # 포스트 제목 추출
            post_title = result.get("post_title", "")

            # 액션 시간 추출 (재발행: new_published/new_date)
            action_time = None
            if result.get("new_published"):
                # Blogger: ISO 형식 → 간단 시간 형식
                try:
                    from datetime import datetime as dt
                    published = result["new_published"]
                    if "T" in published:
                        parsed = dt.fromisoformat(published.replace("Z", "+00:00"))
                        action_time = parsed.strftime("%H:%M:%S")
                except Exception:
                    action_time = result.get("new_published", "")[:19]
            elif result.get("new_date"):
                # WordPress: date 형식
                try:
                    from datetime import datetime as dt
                    parsed = dt.fromisoformat(result["new_date"].replace("Z", "+00:00"))
                    action_time = parsed.strftime("%H:%M:%S")
                except Exception:
                    action_time = result.get("new_date", "")[:19]

            # 에러 메시지
            error_msg = None if is_success else result.get("message", "")

            log = AutorunLog.create_execution_log(
                user_id=user_id,
                flow_id=flow_id,
                action=action_type,
                status=status,
                flow_name=flow_name,
                module_name=module_name,
                blog_name=blog_name,
                post_title=post_title,
                action_time=action_time,
                duration_ms=duration_ms,
                message=error_msg
            )
            db.add(log)
            await db.commit()

            logger.debug(
                f"[FLOW_ENGINE] Compact log | [{flow_name}][{module_name}]-"
                f"[{post_title[:20] if post_title else 'N/A'}][{action_time or '-'}]"
                f"[{'✅' if is_success else '❌'}]"
            )
        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Log creation failed | Error={e}")
            # 로그 생성 실패는 실행에 영향을 주지 않음

    async def _create_error_log(
        self,
        db: AsyncSession,
        user_id: int,
        flow_id: int,
        flow_name: str,
        error_message: str
    ) -> None:
        """에러 로그 생성"""
        try:
            log = AutorunLog.create_action_log(
                user_id=user_id,
                flow_id=flow_id,
                action="failed",
                status="failed",
                flow_name=flow_name,
                message=error_message
            )
            db.add(log)
            await db.commit()
            logger.debug(f"[FLOW_ENGINE] Error log | FlowID={flow_id} | Error={error_message[:50]}")
        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Error log creation failed | Error={e}")
            # 로그 생성 실패는 실행에 영향을 주지 않음
