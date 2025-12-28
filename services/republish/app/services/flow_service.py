"""
플로우 서비스

Features:
- 플로우 CRUD 작업
- 모듈/블로그 독립적 추가/제거
- 슬롯 검증 및 예약 관리
- 모듈 기반 스케줄 추출
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
import json

from ..models.flow import Flow
from ..models.flow_module import FlowModule
from ..models.flow_blog import FlowBlog
from ..models.module import Module
from ..models.blog import Blog, BlogPlatform
from ..models.user import User
from ..models.google_account_policy import GoogleAccountPolicy
from ..models.blogger_global_slot import BloggerGlobalSlot
from ..schemas.flow import (
    FlowCreateRequest,
    FlowUpdateRequest,
    FlowResponse,
    FlowDetailResponse,
    FlowListResponse,
    FlowModuleAddRequest,
    FlowBlogAddRequest,
    BlogAddResult
)
from ..schemas.blogger_slot import AddBlogResult, SlotInfo, SlotConflict, ScheduleInfo, SlotReservation
from ..services.flow_slot_validator import FlowSlotValidator
from ..core.logger import get_logger

logger = get_logger("flow_service", "app.log")


class FlowService:
    """플로우 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.slot_validator = FlowSlotValidator(db)

    # ===========================================
    # 플로우 CRUD
    # ===========================================

    async def get_flows(
        self,
        user: User,
        page: int = 1,
        size: int = 20
    ) -> FlowListResponse:
        """플로우 목록 조회"""
        try:
            logger.info(f"[GET_FLOWS] 사용자 {user.id} 플로우 목록 조회 (페이지: {page}/{size})")

            # 전체 개수 조회
            count_query = select(func.count(Flow.id)).where(Flow.user_id == user.id)
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            # 플로우 목록 조회 (관계 포함)
            offset = (page - 1) * size
            query = (
                select(Flow)
                .options(
                    selectinload(Flow.flow_modules).selectinload(FlowModule.module),
                    selectinload(Flow.flow_blogs).selectinload(FlowBlog.blog)
                )
                .where(Flow.user_id == user.id)
                .order_by(Flow.updated_at.desc())
                .offset(offset)
                .limit(size)
            )
            result = await self.db.execute(query)
            flows = result.scalars().all()

            has_next = (offset + size) < total

            logger.info(f"[GET_FLOWS] 총 {total}개 중 {len(flows)}개 조회 완료")

            return FlowListResponse(
                flows=[FlowResponse.model_validate(flow) for flow in flows],
                total=total,
                page=page,
                size=size,
                has_next=has_next
            )

        except Exception as e:
            logger.error(f"[GET_FLOWS] 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="플로우 목록을 조회하는 중 오류가 발생했습니다"
            )

    async def get_flow(self, user: User, flow_id: int) -> Optional[Flow]:
        """플로우 상세 조회"""
        try:
            logger.info(f"[GET_FLOW] 사용자 {user.id} 플로우 조회: {flow_id}")

            query = (
                select(Flow)
                .options(
                    selectinload(Flow.flow_modules).selectinload(FlowModule.module),
                    selectinload(Flow.flow_blogs).selectinload(FlowBlog.blog)
                )
                .where(
                    and_(
                        Flow.id == flow_id,
                        Flow.user_id == user.id
                    )
                )
            )
            result = await self.db.execute(query)
            flow = result.scalar_one_or_none()

            if flow:
                logger.info(f"[GET_FLOW] 플로우 조회 완료: {flow_id}")
            else:
                logger.warning(f"[GET_FLOW] 플로우를 찾을 수 없음: {flow_id}")

            return flow

        except Exception as e:
            logger.error(f"[GET_FLOW] 오류: {e}")
            raise

    async def create_flow(
        self,
        user: User,
        request: FlowCreateRequest
    ) -> Flow:
        """플로우 생성"""
        try:
            logger.info(f"[CREATE_FLOW] 사용자 {user.id} 플로우 생성: {request.name}")

            # 플로우 생성
            flow = Flow(
                user_id=user.id,
                name=request.name,
                description=request.description,
                status=request.status,
                priority=request.priority
            )

            self.db.add(flow)
            await self.db.commit()
            await self.db.refresh(flow)

            logger.info(f"[CREATE_FLOW] 플로우 생성 완료: {flow.id}")
            return flow

        except Exception as e:
            logger.error(f"[CREATE_FLOW] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우를 생성하는 중 오류가 발생했습니다"
            )

    async def update_flow(
        self,
        user: User,
        flow_id: int,
        request: FlowUpdateRequest
    ) -> Optional[Flow]:
        """플로우 수정"""
        try:
            logger.info(f"[UPDATE_FLOW] 사용자 {user.id} 플로우 수정: {flow_id}")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                return None

            # 업데이트 필드 적용 (None이 아닌 값만)
            update_data = request.model_dump(exclude_none=True)

            for field, value in update_data.items():
                if hasattr(flow, field):
                    setattr(flow, field, value)

            await self.db.commit()
            await self.db.refresh(flow)

            logger.info(f"[UPDATE_FLOW] 플로우 수정 완료: {flow_id}")
            return flow

        except Exception as e:
            logger.error(f"[UPDATE_FLOW] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우를 수정하는 중 오류가 발생했습니다"
            )

    async def delete_flow(self, user: User, flow_id: int) -> bool:
        """플로우 삭제"""
        try:
            logger.info(f"[DELETE_FLOW] 사용자 {user.id} 플로우 삭제: {flow_id}")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                return False

            # Blogger 블로그의 예약된 슬롯 해제
            await self.slot_validator.release_flow_blogger_slots(flow_id)

            # 관련 데이터 삭제 (CASCADE 되지만 명시적으로)
            await self.db.execute(delete(FlowModule).where(FlowModule.flow_id == flow_id))
            await self.db.execute(delete(FlowBlog).where(FlowBlog.flow_id == flow_id))

            await self.db.delete(flow)
            await self.db.commit()

            logger.info(f"[DELETE_FLOW] 플로우 삭제 완료: {flow_id}")
            return True

        except Exception as e:
            logger.error(f"[DELETE_FLOW] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="플로우를 삭제하는 중 오류가 발생했습니다"
            )

    # ===========================================
    # 모듈 관리
    # ===========================================

    async def add_modules(
        self,
        user: User,
        flow_id: int,
        request: FlowModuleAddRequest
    ) -> Optional[Flow]:
        """플로우에 모듈 추가"""
        try:
            logger.info(f"[ADD_MODULES] 플로우 {flow_id}에 모듈 추가: {request.module_ids}")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                return None

            # 이미 추가된 모듈 ID 조회
            existing_query = select(FlowModule.module_id).where(FlowModule.flow_id == flow_id)
            existing_result = await self.db.execute(existing_query)
            existing_module_ids = {row[0] for row in existing_result.fetchall()}

            # 새로 추가할 모듈만 필터링
            new_module_ids = [
                mid for mid in request.module_ids
                if mid not in existing_module_ids
            ]

            if not new_module_ids:
                logger.info(f"[ADD_MODULES] 모든 모듈이 이미 추가됨: {flow_id}")
                return flow

            # 모듈 소유권 확인
            module_query = select(Module).where(
                and_(
                    Module.id.in_(new_module_ids),
                    Module.user_id == user.id
                )
            )
            module_result = await self.db.execute(module_query)
            valid_modules = module_result.scalars().all()
            valid_module_ids = [m.id for m in valid_modules]

            if len(valid_module_ids) != len(new_module_ids):
                invalid_ids = set(new_module_ids) - set(valid_module_ids)
                raise HTTPException(
                    status_code=400,
                    detail=f"유효하지 않은 모듈 ID: {list(invalid_ids)}"
                )

            # 모듈-플로우 연결 생성
            for module_id in valid_module_ids:
                link = FlowModule(flow_id=flow_id, module_id=module_id)
                self.db.add(link)

            await self.db.commit()
            await self.db.refresh(flow)

            logger.info(f"[ADD_MODULES] 모듈 추가 완료: {len(valid_module_ids)}개")
            return flow

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[ADD_MODULES] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 추가하는 중 오류가 발생했습니다"
            )

    async def remove_module(self, user: User, flow_id: int, module_id: int) -> bool:
        """플로우에서 모듈 제거"""
        try:
            logger.info(f"[REMOVE_MODULE] 플로우 {flow_id}에서 모듈 {module_id} 제거")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                return False

            # 모듈-플로우 연결 제거
            delete_query = delete(FlowModule).where(
                and_(
                    FlowModule.flow_id == flow_id,
                    FlowModule.module_id == module_id
                )
            )
            result = await self.db.execute(delete_query)

            if result.rowcount == 0:
                logger.warning(f"[REMOVE_MODULE] 연결을 찾을 수 없음: flow={flow_id}, module={module_id}")
                return False

            await self.db.commit()

            logger.info(f"[REMOVE_MODULE] 모듈 제거 완료: {module_id}")
            return True

        except Exception as e:
            logger.error(f"[REMOVE_MODULE] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 제거하는 중 오류가 발생했습니다"
            )

    # ===========================================
    # 블로그 관리 (슬롯 검증 포함)
    # ===========================================

    async def add_blogs(
        self,
        user: User,
        flow_id: int,
        request: FlowBlogAddRequest
    ) -> BlogAddResult:
        """플로우에 블로그 추가 (슬롯 검증 포함)"""
        try:
            logger.info(f"[ADD_BLOGS] 플로우 {flow_id}에 블로그 추가: {request.blog_ids}")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                raise HTTPException(
                    status_code=404,
                    detail="플로우를 찾을 수 없습니다"
                )

            # 이미 추가된 블로그 ID 조회
            existing_query = select(FlowBlog.blog_id).where(FlowBlog.flow_id == flow_id)
            existing_result = await self.db.execute(existing_query)
            existing_blog_ids = {row[0] for row in existing_result.fetchall()}

            # 새로 추가할 블로그만 필터링
            new_blog_ids = [
                bid for bid in request.blog_ids
                if bid not in existing_blog_ids
            ]

            if not new_blog_ids:
                logger.info(f"[ADD_BLOGS] 모든 블로그가 이미 추가됨: {flow_id}")
                return BlogAddResult(
                    success_count=0,
                    total_requested=len(request.blog_ids),
                    failed_blogs=[],
                    warnings=["모든 블로그가 이미 추가되어 있습니다"]
                )

            # 블로그별 개별 처리
            results = {
                "success_count": 0,
                "failed_blogs": [],
                "warnings": []
            }

            for blog_id in new_blog_ids:
                blog_result = await self.slot_validator.add_single_blog_with_validation(user.id, flow, blog_id)
                if blog_result["success"]:
                    results["success_count"] += 1
                    if blog_result.get("warning"):
                        results["warnings"].append(blog_result["warning"])
                else:
                    results["failed_blogs"].append(blog_result["error"])

            await self.db.commit()

            logger.info(f"[ADD_BLOGS] 블로그 추가 완료: {results['success_count']}/{len(new_blog_ids)} 성공")

            return BlogAddResult(
                success_count=results["success_count"],
                total_requested=len(new_blog_ids),
                failed_blogs=results["failed_blogs"],
                warnings=results["warnings"]
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[ADD_BLOGS] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="블로그를 추가하는 중 오류가 발생했습니다"
            )

    async def remove_blog(self, user: User, flow_id: int, blog_id: int) -> bool:
        """플로우에서 블로그 제거 (슬롯 해제 포함)"""
        try:
            logger.info(f"[REMOVE_BLOG] 플로우 {flow_id}에서 블로그 {blog_id} 제거")

            # 플로우 조회 (소유권 확인 포함)
            flow = await self.get_flow(user, flow_id)
            if not flow:
                return False

            # 블로그 정보 조회
            blog_query = select(Blog).where(
                and_(Blog.id == blog_id, Blog.user_id == user.id)
            )
            blog_result = await self.db.execute(blog_query)
            blog = blog_result.scalar_one_or_none()

            if not blog:
                logger.warning(f"[REMOVE_BLOG] 블로그를 찾을 수 없음: {blog_id}")
                return False

            # Blogger 블로그인 경우 슬롯 해제
            if blog.is_blogger:
                await self.slot_validator.release_single_blog_slots(flow_id, blog_id)

            # 블로그-플로우 연결 제거
            delete_query = delete(FlowBlog).where(
                and_(
                    FlowBlog.flow_id == flow_id,
                    FlowBlog.blog_id == blog_id
                )
            )
            result = await self.db.execute(delete_query)

            if result.rowcount == 0:
                logger.warning(f"[REMOVE_BLOG] 연결을 찾을 수 없음: flow={flow_id}, blog={blog_id}")
                return False

            await self.db.commit()

            logger.info(f"[REMOVE_BLOG] 블로그 제거 완료: {blog_id}")
            return True

        except Exception as e:
            logger.error(f"[REMOVE_BLOG] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="블로그를 제거하는 중 오류가 발생했습니다"
            )

