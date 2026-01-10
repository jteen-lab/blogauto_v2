"""
모듈 서비스

Features:
- 모듈 CRUD 작업
- 모듈 타입별 필터링
- 플로우 연동 여부 확인
- 모듈 유효성 검증
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from ..models.module_type import ModuleType
from ..models.module import Module
from ..models.flow_module import FlowModule
from ..models.user import User
from ..schemas.module import (
    ModuleCreateRequest,
    ModuleUpdateRequest,
    ModuleResponse,
    ModuleDetailResponse,
    ModuleListResponse,
    ModuleTypeResponse
)
from ..core.logger import get_logger

logger = get_logger("module_service", "app.log")


class ModuleService:
    """모듈 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===========================================
    # 모듈 타입 관련
    # ===========================================

    async def get_module_types(self) -> List[ModuleTypeResponse]:
        """모듈 타입 목록 조회"""
        try:
            logger.info("[GET_MODULE_TYPES] 모듈 타입 목록 조회 시작")

            query = select(ModuleType).order_by(ModuleType.display_order, ModuleType.id)
            result = await self.db.execute(query)
            module_types = result.scalars().all()

            logger.info(f"[GET_MODULE_TYPES] {len(module_types)}개 모듈 타입 조회 완료")

            return [ModuleTypeResponse.model_validate(mt) for mt in module_types]

        except Exception as e:
            logger.error(f"[GET_MODULE_TYPES] 오류: {e}")
            raise

    async def get_module_type_by_code(self, code: str) -> Optional[ModuleType]:
        """코드로 모듈 타입 조회"""
        try:
            query = select(ModuleType).where(ModuleType.code == code)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[GET_MODULE_TYPE_BY_CODE] 오류: {e}")
            raise

    # ===========================================
    # 모듈 CRUD
    # ===========================================

    async def get_modules(
        self,
        user: User,
        module_type_code: Optional[str] = None,
        page: int = 1,
        size: int = 20
    ) -> ModuleListResponse:
        """모듈 목록 조회"""
        try:
            logger.info(
                f"[GET_MODULES] 사용자 {user.id} 모듈 목록 조회 "
                f"(타입: {module_type_code}, 페이지: {page}/{size})"
            )

            # 쿼리 조건 구성
            conditions = [Module.user_id == user.id]

            if module_type_code:
                # 모듈 타입 조회
                module_type = await self.get_module_type_by_code(module_type_code)
                if not module_type:
                    raise HTTPException(
                        status_code=400,
                        detail=f"존재하지 않는 모듈 타입: {module_type_code}"
                    )
                conditions.append(Module.module_type_id == module_type.id)

            # 전체 개수 조회
            count_query = select(func.count(Module.id)).where(and_(*conditions))
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            # 모듈 목록 조회 (관계 포함)
            offset = (page - 1) * size
            query = (
                select(Module)
                .options(selectinload(Module.module_type))
                .where(and_(*conditions))
                .order_by(Module.updated_at.desc())
                .offset(offset)
                .limit(size)
            )
            result = await self.db.execute(query)
            modules = result.scalars().all()

            has_next = (offset + size) < total

            logger.info(f"[GET_MODULES] 총 {total}개 중 {len(modules)}개 조회 완료")

            return ModuleListResponse(
                modules=[ModuleResponse.model_validate(module) for module in modules],
                total=total,
                page=page,
                size=size,
                has_next=has_next
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[GET_MODULES] 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="모듈 목록을 조회하는 중 오류가 발생했습니다"
            )

    async def get_module(self, user: User, module_id: int) -> Optional[Module]:
        """모듈 상세 조회"""
        try:
            logger.info(f"[GET_MODULE] 사용자 {user.id} 모듈 조회: {module_id}")

            query = (
                select(Module)
                .options(selectinload(Module.module_type))
                .where(
                    and_(
                        Module.id == module_id,
                        Module.user_id == user.id
                    )
                )
            )
            result = await self.db.execute(query)
            module = result.scalar_one_or_none()

            if module:
                logger.info(f"[GET_MODULE] 모듈 조회 완료: {module_id}")
            else:
                logger.warning(f"[GET_MODULE] 모듈을 찾을 수 없음: {module_id}")

            return module

        except Exception as e:
            logger.error(f"[GET_MODULE] 오류: {e}")
            raise

    async def create_module(
        self,
        user: User,
        request: ModuleCreateRequest
    ) -> Module:
        """모듈 생성"""
        try:
            logger.info(f"[CREATE_MODULE] 사용자 {user.id} 모듈 생성: {request.name}")

            # 모듈 타입 조회
            module_type = await self.get_module_type_by_code(request.module_type_code)
            if not module_type:
                raise HTTPException(
                    status_code=400,
                    detail=f"존재하지 않는 모듈 타입: {request.module_type_code}"
                )

            # 모듈 생성
            module = Module(
                user_id=user.id,
                module_type_id=module_type.id,
                name=request.name,
                description=request.description,
                schedule_matrix=request.schedule_matrix,
                manual_interval_minutes=request.manual_interval_minutes,
                min_post_count=request.min_post_count,
                post_range_start=request.post_range_start,
                post_range_end=request.post_range_end,
                interval_mode=request.interval_mode,
                auto_daily_count=request.auto_daily_count,
                jitter_enabled=request.jitter_enabled,
                jitter_min_percent=request.jitter_min_percent,
                jitter_max_percent=request.jitter_max_percent,
                active_hours_start=request.active_hours_start,
                active_hours_end=request.active_hours_end,
                blackout_days=request.blackout_days,
                cooldown_days=request.cooldown_days,
                priority=request.priority,
                platform_overrides=request.platform_overrides,
                settings=request.settings
            )

            self.db.add(module)
            await self.db.commit()
            await self.db.refresh(module, ["module_type"])

            logger.info(f"[CREATE_MODULE] 모듈 생성 완료: {module.id}")
            return module

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CREATE_MODULE] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 생성하는 중 오류가 발생했습니다"
            )

    async def update_module(
        self,
        user: User,
        module_id: int,
        request: ModuleUpdateRequest
    ) -> Optional[Module]:
        """모듈 수정

        Note:
            - None 값은 업데이트에서 제외됨 (기존 값 유지)
            - 빈 문자열("")은 명시적으로 설정됨 (필드 초기화)
            - nullable_fields에 있는 필드는 None도 유효한 값으로 처리
        """
        try:
            logger.info(f"[UPDATE_MODULE] 사용자 {user.id} 모듈 수정: {module_id}")

            # 모듈 조회 (소유권 확인 포함)
            module = await self.get_module(user, module_id)
            if not module:
                return None

            # None도 유효한 값으로 처리해야 하는 필드 목록
            nullable_fields = {'post_range_end', 'cooldown_days', 'description'}

            # 업데이트 필드 적용
            # exclude_none=True: None은 제외, 빈 문자열("")은 포함
            update_data = request.model_dump(exclude_none=True)

            # nullable 필드는 별도로 처리 (None 값도 명시적으로 설정)
            raw_data = request.model_dump()
            for field in nullable_fields:
                if field in raw_data and raw_data[field] is None:
                    # 요청에 필드가 있고 값이 None이면 명시적으로 None 설정
                    update_data[field] = None

            logger.debug(f"[UPDATE_MODULE] 업데이트 필드: {list(update_data.keys())}")

            for field, value in update_data.items():
                if hasattr(module, field):
                    old_value = getattr(module, field, None)
                    setattr(module, field, value)
                    # 값이 변경되는 경우 로깅
                    if value != old_value:
                        logger.info(
                            f"[UPDATE_MODULE] 필드 '{field}' 변경: "
                            f"'{old_value}' -> '{value}'"
                        )

            await self.db.commit()
            await self.db.refresh(module, ["module_type", "created_at", "updated_at"])

            logger.info(f"[UPDATE_MODULE] 모듈 수정 완료: {module_id}")
            return module

        except Exception as e:
            logger.error(f"[UPDATE_MODULE] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 수정하는 중 오류가 발생했습니다"
            )

    async def copy_module(
        self,
        user: User,
        module_id: int
    ) -> Optional[Module]:
        """모듈 복사"""
        try:
            logger.info(f"[COPY_MODULE] 사용자 {user.id} 모듈 복사: {module_id}")

            # 원본 모듈 조회 (소유권 확인 포함)
            original_module = await self.get_module(user, module_id)
            if not original_module:
                return None

            # 복사본 생성을 위한 요청 데이터 구성
            copy_request = ModuleCreateRequest(
                name=f"{original_module.name} (복사본)",
                module_type_code=original_module.module_type.code,
                description=original_module.description,
                schedule_matrix=original_module.schedule_matrix,
                manual_interval_minutes=original_module.manual_interval_minutes,
                min_post_count=original_module.min_post_count,
                post_range_start=original_module.post_range_start,
                post_range_end=original_module.post_range_end,
                interval_mode=original_module.interval_mode,
                auto_daily_count=original_module.auto_daily_count,
                jitter_enabled=original_module.jitter_enabled,
                jitter_min_percent=original_module.jitter_min_percent,
                jitter_max_percent=original_module.jitter_max_percent,
                active_hours_start=original_module.active_hours_start,
                active_hours_end=original_module.active_hours_end,
                blackout_days=original_module.blackout_days or [],
                cooldown_days=original_module.cooldown_days,
                priority=original_module.priority,
                platform_overrides=original_module.platform_overrides,
                settings=original_module.settings
            )

            # create_module 메소드를 재사용하여 복사본 생성
            copied_module = await self.create_module(user, copy_request)

            logger.info(f"[COPY_MODULE] 모듈 복사 완료: {original_module.id} -> {copied_module.id}")
            return copied_module

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[COPY_MODULE] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 복사하는 중 오류가 발생했습니다"
            )

    async def delete_module(self, user: User, module_id: int) -> bool:
        """모듈 삭제"""
        try:
            logger.info(f"[DELETE_MODULE] 사용자 {user.id} 모듈 삭제: {module_id}")

            # 모듈 조회 (소유권 확인 포함)
            module = await self.get_module(user, module_id)
            if not module:
                return False

            # 플로우에서 사용 중인지 확인
            flow_check_query = select(FlowModule).where(FlowModule.module_id == module_id)
            flow_result = await self.db.execute(flow_check_query)
            flow_links = flow_result.scalars().all()

            if flow_links:
                # 사용 중인 플로우 이름 수집 (최대 3개)
                flow_ids = [link.flow_id for link in flow_links[:3]]
                flow_names = []
                for flow_id in flow_ids:
                    from ..models.flow import Flow
                    flow_query = select(Flow.name).where(Flow.id == flow_id)
                    flow_result = await self.db.execute(flow_query)
                    flow_name = flow_result.scalar()
                    if flow_name:
                        flow_names.append(flow_name)

                raise HTTPException(
                    status_code=400,
                    detail=f"플로우에서 사용 중인 모듈은 삭제할 수 없습니다. 사용 중인 플로우: {', '.join(flow_names)}"
                )

            await self.db.delete(module)
            await self.db.commit()

            logger.info(f"[DELETE_MODULE] 모듈 삭제 완료: {module_id}")
            return True

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DELETE_MODULE] 오류: {e}")
            await self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail="모듈을 삭제하는 중 오류가 발생했습니다"
            )

    # ===========================================
    # 유틸리티 메서드
    # ===========================================

    async def check_module_in_use(self, module_id: int) -> bool:
        """모듈이 플로우에서 사용 중인지 확인"""
        try:
            query = select(func.count(FlowModule.id)).where(FlowModule.module_id == module_id)
            result = await self.db.execute(query)
            count = result.scalar()
            return count > 0
        except Exception as e:
            logger.error(f"[CHECK_MODULE_IN_USE] 오류: {e}")
            return False