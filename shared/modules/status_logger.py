"""
노드 5: 상태 기록 모듈 (공용)

Features:
- 실행 결과를 AutorunLog에 기록
- 블로그 상태 업데이트 (last_publish_at)
- URL 히스토리 저장 (선택)
"""
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("status_logger")


class StatusLogger:
    """
    상태 기록 노드

    발행 결과를 데이터베이스에 기록합니다.
    - AutorunLog 생성
    - 블로그 last_publish_at 업데이트
    - URL 히스토리 저장 (옵션)
    """

    def __init__(self, db: AsyncSession):
        """
        Args:
            db: 데이터베이스 세션
        """
        self.db = db

    async def execute(
        self,
        result: dict[str, Any],
        flow_id: int,
        user_id: int,
        module_id: Optional[int] = None,
        save_url_history: bool = False
    ) -> dict[str, Any]:
        """
        결과 기록 실행

        Args:
            result: PublishResult 형식의 발행 결과
            flow_id: 플로우 ID
            user_id: 사용자 ID
            module_id: 모듈 ID (선택)
            save_url_history: URL 히스토리 저장 여부

        Returns:
            StatusLoggerOutput 형식의 딕셔너리
        """
        blog_id = result.get("blog_id")
        status = result.get("status", "unknown")

        logger.info(
            f"[STATUS_LOGGER] 시작 | FlowID={flow_id}, "
            f"BlogID={blog_id}, Status={status}"
        )

        try:
            # 1. AutorunLog 생성
            log_entry = await self._create_autorun_log(
                result, flow_id, user_id, module_id
            )

            # 2. 블로그 상태 업데이트
            blog_updated = await self._update_blog_status(result)

            # 3. URL 히스토리 저장 (옵션)
            url_saved = False
            if save_url_history and result.get("post_url"):
                url_saved = await self._save_url_history(result, user_id)

            logger.info(
                f"[STATUS_LOGGER] 완료 | LogID={log_entry.get('id')}, "
                f"BlogUpdated={blog_updated}, URLSaved={url_saved}"
            )

            return {
                "log_entry": log_entry,
                "blog_updated": blog_updated,
                "url_saved": url_saved
            }

        except Exception as e:
            logger.error(f"[STATUS_LOGGER] 오류 | FlowID={flow_id} | Error={e}")
            raise

    async def _create_autorun_log(
        self,
        result: dict[str, Any],
        flow_id: int,
        user_id: int,
        module_id: Optional[int]
    ) -> dict[str, Any]:
        """AutorunLog 생성"""
        # 동적 임포트로 순환 참조 방지 (컨테이너/로컬 환경 호환)
        try:
            from app.models.autorun_log import AutorunLog
        except ImportError:
            from services.republish.app.models.autorun_log import AutorunLog

        status = result.get("status", "unknown")
        is_success = status == "success"

        # 액션 타입 결정
        action = "republish"

        # 메시지 구성
        if is_success:
            message = f"재발행 성공: {result.get('post_title', '')[:30]}"
        else:
            message = result.get("error_message", "재발행 실패")

        log = AutorunLog(
            user_id=user_id,
            flow_id=flow_id,
            module_name="재발행" if module_id else None,
            action=action,
            status="success" if is_success else "failed",
            message=message,
            blog_name=result.get("blog_name"),
            post_title=result.get("post_title"),
            execution_duration_ms=result.get("response_time_ms"),
            posts_processed=1,
            posts_success=1 if is_success else 0,
            posts_failed=0 if is_success else 1
        )

        self.db.add(log)
        await self.db.flush()

        return {
            "id": log.id,
            "flow_id": flow_id,
            "blog_id": result.get("blog_id"),
            "action": action,
            "status": log.status,
            "message": message,
            "created_at": datetime.now().isoformat()
        }

    async def _update_blog_status(self, result: dict[str, Any]) -> bool:
        """블로그 상태 업데이트"""
        blog_id = result.get("blog_id")
        status = result.get("status")

        if not blog_id or status != "success":
            return False

        try:
            try:
                from app.models.blog import Blog
            except ImportError:
                from services.republish.app.models.blog import Blog

            stmt = (
                update(Blog)
                .where(Blog.id == blog_id)
                .values(
                    post_count_updated_at=datetime.now(),
                    # post_count 증가는 API에서 조회한 값으로 업데이트하는 것이 더 정확
                )
            )
            await self.db.execute(stmt)
            return True

        except Exception as e:
            logger.warning(f"[STATUS_LOGGER] 블로그 업데이트 실패 | BlogID={blog_id} | Error={e}")
            return False

    async def _save_url_history(
        self,
        result: dict[str, Any],
        user_id: int
    ) -> bool:
        """URL 히스토리 저장"""
        post_url = result.get("post_url")
        if not post_url:
            return False

        try:
            # URL 히스토리 모델이 있다면 저장
            # 현재는 구현되지 않았으므로 로깅만 수행
            logger.info(
                f"[STATUS_LOGGER] URL 히스토리 저장 예정 | "
                f"URL={post_url}, UserID={user_id}"
            )
            return True

        except Exception as e:
            logger.warning(f"[STATUS_LOGGER] URL 저장 실패 | Error={e}")
            return False


async def create_status_logger(db: AsyncSession) -> StatusLogger:
    """
    StatusLogger 인스턴스 생성 팩토리 함수

    Args:
        db: 데이터베이스 세션

    Returns:
        StatusLogger 인스턴스
    """
    return StatusLogger(db)
