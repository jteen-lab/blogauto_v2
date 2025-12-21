"""
발행 통합 서비스

Features:
- WordPress/Blogger 통합 발행 인터페이스
- 플랫폼별 API 클라이언트 라우팅
- 발행 이력 자동 기록
- 에러 핸들링 및 로깅
"""

from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.blog import Blog, BlogPlatform
from ..models.post import Post
from ..models.user import User
from ..models.publish_log import PublishLog
from .wordpress_api import WordPressAPI, WordPressAPIError
from .platform_limiter import PlatformLimiter
from ..core.logger import get_logger

logger = get_logger("publish_service", "republish.log")


class PublishService:
    """발행 통합 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.platform_limiter = PlatformLimiter(db)

    # ===========================================
    # 발행/재발행 메인 인터페이스
    # ===========================================

    async def publish_post(
        self,
        user: User,
        blog: Blog,
        post: Post,
        profile_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """새 포스트 발행"""
        try:
            # 발행 가능 여부 확인
            can_publish, limit_msg = await self.platform_limiter.can_publish(
                blog.id, blog.platform.value
            )

            if not can_publish:
                logger.warning(f"[PUBLISH] Blog {blog.id}: {limit_msg}")
                return {
                    "success": False,
                    "message": limit_msg,
                    "action": "skipped"
                }

            # 포스트 데이터 준비
            post_data = {
                "title": post.title,
                "content": post.content,
                "excerpt": post.excerpt
            }

            # 플랫폼별 발행
            result = await self._route_to_platform(
                blog=blog,
                action="create",
                post_data=post_data
            )

            if result["success"]:
                # 포스트 상태 업데이트
                post.mark_as_published(
                    remote_id=result["remote_id"],
                    remote_url=result.get("remote_url")
                )

                # 성공 로그 기록
                log = PublishLog.create_success_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="publish",
                    platform=blog.platform.value,
                    remote_id=result["remote_id"],
                    response_time_ms=result.get("response_time_ms"),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()

                logger.info(f"[PUBLISH] Success | Blog={blog.id} | Post={post.id} | RemoteID={result['remote_id']}")

                return {
                    "success": True,
                    "message": "발행 완료",
                    "remote_id": result["remote_id"],
                    "remote_url": result.get("remote_url"),
                    "response_time_ms": result.get("response_time_ms")
                }

            else:
                # 실패 로그 기록
                log = PublishLog.create_failed_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="publish",
                    platform=blog.platform.value,
                    error_message=result.get("message", "알 수 없는 오류"),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()

                return {
                    "success": False,
                    "message": f"발행 실패: {result.get('message', '알 수 없는 오류')}"
                }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[PUBLISH] Error | Blog={blog.id} | Post={post.id} | Error={e}")

            # 실패 로그 기록
            try:
                log = PublishLog.create_failed_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="publish",
                    platform=blog.platform.value,
                    error_message=str(e),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()
            except:
                pass  # 로그 기록 실패해도 무시

            return {
                "success": False,
                "message": f"시스템 오류: {str(e)}"
            }

    async def republish_post(
        self,
        user: User,
        blog: Blog,
        post: Post,
        profile_id: int
    ) -> Dict[str, Any]:
        """포스트 재발행"""
        try:
            # 재발행 가능 여부 확인
            if not post.can_be_republished:
                return {
                    "success": False,
                    "message": "재발행할 수 없는 포스트입니다"
                }

            # 발행 가능 여부 확인
            can_publish, limit_msg = await self.platform_limiter.can_publish(
                blog.id, blog.platform.value
            )

            if not can_publish:
                logger.warning(f"[REPUBLISH] Blog {blog.id}: {limit_msg}")
                return {
                    "success": False,
                    "message": limit_msg,
                    "action": "skipped"
                }

            # 포스트 데이터 준비
            post_data = {
                "title": post.title,
                "content": post.content,
                "excerpt": post.excerpt
            }

            # 플랫폼별 재발행
            result = await self._route_to_platform(
                blog=blog,
                action="update",
                remote_id=post.remote_id,
                post_data=post_data
            )

            if result["success"]:
                # 포스트 재발행 상태 업데이트
                post.mark_as_republished()

                # 성공 로그 기록
                log = PublishLog.create_success_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="republish",
                    platform=blog.platform.value,
                    remote_id=result["remote_id"],
                    response_time_ms=result.get("response_time_ms"),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()

                logger.info(f"[REPUBLISH] Success | Blog={blog.id} | Post={post.id} | RemoteID={result['remote_id']}")

                return {
                    "success": True,
                    "message": "재발행 완료",
                    "remote_id": result["remote_id"],
                    "remote_url": result.get("remote_url"),
                    "response_time_ms": result.get("response_time_ms")
                }

            else:
                # 실패 로그 기록
                log = PublishLog.create_failed_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="republish",
                    platform=blog.platform.value,
                    error_message=result.get("message", "알 수 없는 오류"),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()

                return {
                    "success": False,
                    "message": f"재발행 실패: {result.get('message', '알 수 없는 오류')}"
                }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[REPUBLISH] Error | Blog={blog.id} | Post={post.id} | Error={e}")

            # 실패 로그 기록
            try:
                log = PublishLog.create_failed_log(
                    user_id=user.id,
                    blog_id=blog.id,
                    post_id=post.id,
                    action="republish",
                    platform=blog.platform.value,
                    error_message=str(e),
                    profile_id=profile_id
                )

                self.db.add(log)
                await self.db.commit()
            except:
                pass

            return {
                "success": False,
                "message": f"시스템 오류: {str(e)}"
            }

    # ===========================================
    # 플랫폼별 라우팅
    # ===========================================

    async def _route_to_platform(
        self,
        blog: Blog,
        action: str,
        post_data: Dict[str, Any],
        remote_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """플랫폼별 API 클라이언트 라우팅"""
        try:
            if blog.platform == BlogPlatform.WORDPRESS:
                return await self._handle_wordpress(blog, action, post_data, remote_id)

            elif blog.platform == BlogPlatform.BLOGGER:
                # TODO: Blogger API 구현 후 추가
                return {
                    "success": False,
                    "message": "Blogger API는 아직 구현되지 않았습니다"
                }

            else:
                return {
                    "success": False,
                    "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
                }

        except Exception as e:
            logger.error(f"플랫폼 라우팅 오류 | Blog={blog.id} | Platform={blog.platform.value} | Error={e}")
            return {
                "success": False,
                "message": f"플랫폼 처리 오류: {str(e)}"
            }

    async def _handle_wordpress(
        self,
        blog: Blog,
        action: str,
        post_data: Dict[str, Any],
        remote_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """WordPress API 처리"""
        try:
            async with WordPressAPI() as wp_api:
                if action == "create":
                    return await wp_api.create_post(blog, post_data)

                elif action == "update":
                    if not remote_id:
                        raise ValueError("재발행에는 remote_id가 필요합니다")
                    return await wp_api.update_post(blog, remote_id, post_data)

                else:
                    return {
                        "success": False,
                        "message": f"지원하지 않는 작업: {action}"
                    }

        except WordPressAPIError as e:
            return {
                "success": False,
                "message": e.message
            }

        except Exception as e:
            logger.error(f"WordPress 처리 오류 | Blog={blog.id} | Action={action} | Error={e}")
            return {
                "success": False,
                "message": f"WordPress 오류: {str(e)}"
            }

    # ===========================================
    # 연결 테스트
    # ===========================================

    async def test_blog_connection(self, blog: Blog) -> Dict[str, Any]:
        """블로그 연결 테스트"""
        try:
            logger.info(f"[TEST] Testing blog connection | Blog={blog.id} | Platform={blog.platform.value}")

            if blog.platform == BlogPlatform.WORDPRESS:
                async with WordPressAPI() as wp_api:
                    return await wp_api.test_connection(blog)

            elif blog.platform == BlogPlatform.BLOGGER:
                # TODO: Blogger API 구현 후 추가
                return {
                    "success": False,
                    "message": "Blogger 연결 테스트는 아직 구현되지 않았습니다"
                }

            else:
                return {
                    "success": False,
                    "message": f"지원하지 않는 플랫폼: {blog.platform.value}"
                }

        except Exception as e:
            logger.error(f"[TEST] Connection test error | Blog={blog.id} | Error={e}")
            return {
                "success": False,
                "message": f"연결 테스트 오류: {str(e)}"
            }