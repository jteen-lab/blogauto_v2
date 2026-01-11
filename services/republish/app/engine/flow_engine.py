"""
플로우 엔진

Features:
- 모듈 조합에 따라 동작 실행
- action_type에 따른 액션 분기
- 플로우별 블로그 순회 실행
- 실행 로그 자동 기록
- 모듈의 post_range 조건에 따른 블로그 필터링
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import time
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.flow import Flow
from ..models.blog import Blog, BlogPlatform
from ..models.module import Module
from ..models.google_credential import GoogleCredential
from ..models.autorun_log import AutorunLog
from .actions.republish import RepublishAction
from ..core.logger import get_logger

logger = get_logger("flow_engine", "republish.log")

# Timezone 설정
KST = pytz.timezone('Asia/Seoul')


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
        module_id: Optional[int] = None,
        log_execution: bool = True
    ) -> Dict[str, Any]:
        """
        플로우 실행

        Args:
            db: 데이터베이스 세션
            flow: 실행할 플로우
            action_type: 액션 타입 (republish, publish, generate 등)
            target_blog_id: 특정 블로그만 실행 (None이면 전체)
            module_id: 특정 모듈 ID (None이면 action_type으로 첫 번째 모듈 사용)
            log_execution: 실행 로그 기록 여부 (기본: True)

        Returns:
            실행 결과
        """
        start_time = time.time()

        try:
            logger.info(
                f"[FLOW_ENGINE] Starting | FlowID={flow.id} | "
                f"FlowName={flow.name} | ActionType={action_type} | ModuleID={module_id}"
            )

            # 액션 타입 검증
            if action_type not in self.ACTION_TYPES:
                logger.error(f"[FLOW_ENGINE] Invalid action type | ActionType={action_type}")
                return {
                    "success": False,
                    "message": f"지원하지 않는 액션 타입: {action_type}",
                    "flow_id": flow.id
                }

            # 모듈 찾기 (module_id가 있으면 해당 모듈, 없으면 action_type으로)
            module = await self._find_module(flow, action_type, module_id)
            if not module:
                logger.warning(
                    f"[FLOW_ENGINE] No module found | FlowID={flow.id} | "
                    f"ActionType={action_type} | ModuleID={module_id}"
                )
                return {
                    "success": False,
                    "message": f"플로우에 {action_type} 모듈이 없습니다",
                    "flow_id": flow.id
                }

            # 대상 블로그 목록 조회 (모듈의 post_range 조건으로 필터링)
            blogs = await self._get_target_blogs(db, flow, target_blog_id, module)
            if not blogs:
                logger.info(
                    f"[FLOW_ENGINE] No matching blogs | FlowID={flow.id} | "
                    f"ModuleName={module.name} | Range={module.post_range_start}-{module.post_range_end}"
                )
                return {
                    "success": True,
                    "message": "해당 모듈 조건에 맞는 블로그가 없습니다",
                    "flow_id": flow.id,
                    "skipped": True
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
                    # 재발행 성공 시 포스트 수 +1 (재발행은 기존 포스트를 올리는 것이므로 유지)
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
                f"[FLOW_ENGINE] Completed | FlowID={flow.id} | ModuleName={module.name} | "
                f"Success={success_count} | Fail={fail_count} | Duration={duration_ms}ms"
            )

            return {
                "success": fail_count == 0,
                "message": f"실행 완료 (성공: {success_count}, 실패: {fail_count})",
                "flow_id": flow.id,
                "flow_name": flow.name,
                "action_type": action_type,
                "module_name": module.name,
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

    async def _find_module(
        self,
        flow: Flow,
        action_type: str,
        module_id: Optional[int] = None
    ) -> Optional[Module]:
        """
        모듈 찾기

        Args:
            flow: 플로우
            action_type: 액션 타입
            module_id: 특정 모듈 ID (있으면 해당 모듈 반환)

        Returns:
            찾은 모듈 또는 None
        """
        for link in flow.module_links:
            module = link.module
            if module and module.module_type:
                # module_id가 지정된 경우 해당 모듈만 반환
                if module_id is not None:
                    if module.id == module_id:
                        return module
                else:
                    # module_id가 없으면 action_type으로 첫 번째 모듈 반환
                    if module.module_type.code == action_type:
                        return module
        return None

    async def _get_target_blogs(
        self,
        db: AsyncSession,
        flow: Flow,
        target_blog_id: Optional[int],
        module: Module
    ) -> List[Blog]:
        """
        실행 대상 블로그 목록 조회 (모듈의 post_range 조건으로 필터링)

        Args:
            db: 데이터베이스 세션
            flow: 플로우
            target_blog_id: 특정 블로그 ID (None이면 전체)
            module: 실행할 모듈 (post_range 조건 포함)

        Returns:
            필터링된 블로그 목록
        """
        blogs = []
        has_range_condition = (
            module.post_range_start is not None or
            module.post_range_end is not None
        )

        for link in flow.blog_links:
            blog = link.blog
            if not blog or not blog.is_active or blog.is_deleted:
                continue

            # 특정 블로그 지정 시 필터링
            if target_blog_id and blog.id != target_blog_id:
                continue

            # 모듈에 포스트 범위 조건이 있는 경우 필터링
            if has_range_condition:
                # 포스트 수가 없으면 API로 조회 후 저장
                if blog.total_post_count is None:
                    post_count = await self._fetch_and_save_post_count(db, blog)
                else:
                    post_count = blog.total_post_count

                # 범위 시작 조건 (post_range_start 이상)
                if module.post_range_start is not None:
                    if post_count < module.post_range_start:
                        logger.debug(
                            f"[FLOW_ENGINE] Blog filtered out (below range) | "
                            f"Blog={blog.name} | PostCount={post_count} | "
                            f"RangeStart={module.post_range_start}"
                        )
                        continue

                # 범위 끝 조건 (post_range_end 이하)
                if module.post_range_end is not None:
                    if post_count > module.post_range_end:
                        logger.debug(
                            f"[FLOW_ENGINE] Blog filtered out (above range) | "
                            f"Blog={blog.name} | PostCount={post_count} | "
                            f"RangeEnd={module.post_range_end}"
                        )
                        continue

                logger.debug(
                    f"[FLOW_ENGINE] Blog matched | Blog={blog.name} | "
                    f"PostCount={post_count} | Range={module.post_range_start}-{module.post_range_end}"
                )

            blogs.append(blog)

        return blogs

    async def _fetch_and_save_post_count(
        self,
        db: AsyncSession,
        blog: Blog
    ) -> int:
        """
        블로그의 포스트 수를 API로 조회하여 DB에 저장

        Args:
            db: 데이터베이스 세션
            blog: 블로그 객체

        Returns:
            포스트 수
        """
        from ..services.wordpress_service import WordPressRepublishService
        from ..services.blogger_service import BloggerRepublishService

        try:
            post_count = 0

            if blog.platform == BlogPlatform.WORDPRESS:
                wp_service = WordPressRepublishService()
                post_count = await wp_service.get_post_count(blog)

            elif blog.platform == BlogPlatform.BLOGGER:
                # Blogger는 credential 필요
                if blog.google_credential_id:
                    query = select(GoogleCredential).where(
                        GoogleCredential.id == blog.google_credential_id
                    )
                    result = await db.execute(query)
                    credential = result.scalar_one_or_none()

                    if credential:
                        blogger_service = BloggerRepublishService()
                        post_count = await blogger_service.get_post_count(blog, credential)

            # DB에 저장
            blog.total_post_count = post_count
            blog.post_count_updated_at = datetime.now(KST)
            await db.flush()

            logger.info(
                f"[FLOW_ENGINE] Post count fetched | Blog={blog.name} | "
                f"Platform={blog.platform.value} | Count={post_count}"
            )
            return post_count

        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Post count fetch failed | Blog={blog.name} | Error={e}")
            return 0

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
        self, db: AsyncSession, user_id: int, flow_id: int, flow_name: str,
        module_name: str, blog_name: str, action_type: str,
        result: Dict[str, Any], duration_ms: int
    ) -> None:
        """간결한 로그 생성"""
        try:
            is_success = result.get("success", False)
            status = "success" if is_success else "failed"
            post_title = result.get("post_title", "")

            # 액션 시간 추출
            action_time = None
            date_str = result.get("new_published") or result.get("new_date")
            if date_str and "T" in date_str:
                try:
                    parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    action_time = parsed.strftime("%Y/%m/%d/%H:%M:%S")
                except Exception:
                    action_time = date_str[:19]

            error_msg = None if is_success else result.get("message", "")
            log = AutorunLog.create_execution_log(
                user_id=user_id, flow_id=flow_id, action=action_type, status=status,
                flow_name=flow_name, module_name=module_name, blog_name=blog_name,
                post_title=post_title, action_time=action_time,
                duration_ms=duration_ms, message=error_msg
            )
            db.add(log)
            await db.commit()
        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Log creation failed | Error={e}")

    async def _create_error_log(
        self, db: AsyncSession, user_id: int, flow_id: int,
        flow_name: str, error_message: str
    ) -> None:
        """에러 로그 생성"""
        try:
            log = AutorunLog.create_action_log(
                user_id=user_id, flow_id=flow_id, action="failed",
                status="failed", flow_name=flow_name, message=error_message
            )
            db.add(log)
            await db.commit()
        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Error log creation failed | Error={e}")
