"""
Google 계정 정책 서비스

Features:
- 계정별 발행 정책 관리
- 슬롯 할당량 계산
- 정책 효과성 분석
- 안전 모드 적용
"""
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, time

from ..models.google_credential import GoogleCredential
from ..models.google_account_policy import GoogleAccountPolicy
from ..schemas.google_account_policy import (
    GoogleAccountPolicyCreate,
    GoogleAccountPolicyUpdate,
    GoogleAccountPolicyResponse
)
from ..core.logger import get_logger

logger = get_logger("google_policy", "strategy.log")


class GoogleAccountPolicyService:
    """Google 계정 정책 서비스"""

    def __init__(self, db: Session):
        self.db = db

    async def get_or_create_default(self, credential_id: int) -> GoogleAccountPolicy:
        """기본 정책 조회 또는 생성"""
        logger.info(f"[GET_OR_CREATE] credential_id={credential_id}")

        # 기존 정책 조회
        policy = self.db.query(GoogleAccountPolicy).filter(
            GoogleAccountPolicy.google_credential_id == credential_id
        ).first()

        if policy:
            logger.debug(f"[GET_OR_CREATE] 기존 정책 발견: policy_id={policy.id}")
            return policy

        # 기본 정책 생성
        try:
            policy = GoogleAccountPolicy.create_default_policy(
                credential_id=credential_id,
                safety_mode=True
            )
            self.db.add(policy)
            self.db.commit()

            logger.info(f"[GET_OR_CREATE] 기본 정책 생성: policy_id={policy.id}")
            return policy

        except Exception as e:
            self.db.rollback()
            logger.error(f"[GET_OR_CREATE] 정책 생성 실패: {e}")
            raise

    async def get_by_credential_id(self, credential_id: int) -> Optional[GoogleAccountPolicy]:
        """Google 계정 ID로 정책 조회"""
        policy = self.db.query(GoogleAccountPolicy).filter(
            GoogleAccountPolicy.google_credential_id == credential_id
        ).first()

        logger.debug(f"[GET_BY_CREDENTIAL] credential_id={credential_id}, found={bool(policy)}")
        return policy

    async def update(self, credential_id: int, policy_data: GoogleAccountPolicyUpdate) -> GoogleAccountPolicy:
        """정책 업데이트"""
        logger.info(f"[UPDATE] credential_id={credential_id}")

        policy = await self.get_or_create_default(credential_id)

        try:
            # 업데이트할 필드들 적용
            if policy_data.min_interval_minutes is not None:
                policy.min_interval_minutes = policy_data.min_interval_minutes

            if policy_data.max_daily_per_blog is not None:
                policy.max_daily_per_blog = policy_data.max_daily_per_blog

            if policy_data.max_daily_total is not None:
                policy.max_daily_total = policy_data.max_daily_total

            if policy_data.allowed_hours_start is not None:
                policy.allowed_hours_start = policy_data.allowed_hours_start

            if policy_data.allowed_hours_end is not None:
                policy.allowed_hours_end = policy_data.allowed_hours_end

            if policy_data.safety_mode is not None:
                policy.safety_mode = policy_data.safety_mode

            # 안전 모드 제한 적용
            if policy.safety_mode:
                policy.apply_safety_restrictions()

            # 정책 검증
            self._validate_policy(policy)

            self.db.commit()
            logger.info(f"[UPDATE] 정책 업데이트 완료: policy_id={policy.id}")
            return policy

        except Exception as e:
            self.db.rollback()
            logger.error(f"[UPDATE] 정책 업데이트 실패: {e}")
            raise

    async def get_slots_per_hour(self, credential_id: int) -> int:
        """시간당 최대 슬롯 수 계산"""
        policy = await self.get_or_create_default(credential_id)
        return policy.slots_per_hour

    async def calculate_daily_capacity(self, credential_id: int) -> Dict[str, Any]:
        """일일 발행 가능 용량 계산"""
        policy = await self.get_or_create_default(credential_id)

        # 기본 계산
        slots_per_hour = policy.slots_per_hour
        working_hours = policy.working_hours_count
        theoretical_daily_slots = slots_per_hour * working_hours

        # 실제 제한 적용
        actual_daily_capacity = min(
            theoretical_daily_slots,
            policy.max_daily_total
        )

        capacity_info = {
            "credential_id": credential_id,
            "slots_per_hour": slots_per_hour,
            "working_hours": working_hours,
            "theoretical_daily_slots": theoretical_daily_slots,
            "actual_daily_capacity": actual_daily_capacity,
            "max_daily_per_blog": policy.max_daily_per_blog,
            "max_daily_total": policy.max_daily_total,
            "utilization_rate": actual_daily_capacity / theoretical_daily_slots if theoretical_daily_slots > 0 else 0
        }

        logger.debug(f"[DAILY_CAPACITY] {capacity_info}")
        return capacity_info

    async def analyze_policy_effectiveness(self, credential_id: int) -> Dict[str, Any]:
        """정책 효과성 분석"""
        logger.info(f"[ANALYZE_EFFECTIVENESS] credential_id={credential_id}")

        policy = await self.get_or_create_default(credential_id)
        capacity = await self.calculate_daily_capacity(credential_id)

        # 분석 요소들
        analysis = {
            "credential_id": credential_id,
            "policy_type": "conservative" if policy.is_conservative_policy else "standard",
            "capacity": capacity,
            "bottlenecks": [],
            "recommendations": [],
            "risk_level": "low"
        }

        # 병목 지점 분석
        if capacity["utilization_rate"] < 0.5:
            analysis["bottlenecks"].append("정책이 너무 보수적임")
            analysis["recommendations"].append("발행 간격 단축 고려")

        if policy.working_hours_count < 8:
            analysis["bottlenecks"].append("작업 시간이 제한적임")
            analysis["recommendations"].append("허용 시간대 확장 고려")

        if policy.max_daily_per_blog < 3:
            analysis["bottlenecks"].append("블로그당 일일 제한이 낮음")
            analysis["recommendations"].append("블로그별 제한 완화 고려")

        # 리스크 레벨 계산
        if policy.min_interval_minutes < 30 or not policy.safety_mode:
            analysis["risk_level"] = "high"
        elif policy.min_interval_minutes < 60:
            analysis["risk_level"] = "medium"

        logger.info(f"[ANALYZE_EFFECTIVENESS] 분석 완료: {analysis['policy_type']}, 리스크={analysis['risk_level']}")
        return analysis

    async def apply_conservative_policy(self, credential_id: int) -> GoogleAccountPolicy:
        """보수적 정책 적용"""
        logger.info(f"[APPLY_CONSERVATIVE] credential_id={credential_id}")

        policy_data = GoogleAccountPolicyUpdate(
            min_interval_minutes=60,
            max_daily_per_blog=3,
            max_daily_total=20,
            allowed_hours_start=10,
            allowed_hours_end=18,
            safety_mode=True
        )

        return await self.update(credential_id, policy_data)

    async def apply_aggressive_policy(self, credential_id: int) -> GoogleAccountPolicy:
        """적극적 정책 적용 (주의 필요)"""
        logger.warning(f"[APPLY_AGGRESSIVE] credential_id={credential_id} - 적극적 정책 적용")

        policy_data = GoogleAccountPolicyUpdate(
            min_interval_minutes=15,
            max_daily_per_blog=10,
            max_daily_total=100,
            allowed_hours_start=8,
            allowed_hours_end=23,
            safety_mode=False
        )

        return await self.update(credential_id, policy_data)

    def _validate_policy(self, policy: GoogleAccountPolicy) -> None:
        """정책 유효성 검증"""
        # 시간 논리 검증
        if policy.min_interval_minutes > 1440:  # 하루
            raise ValueError("발행 간격이 너무 깁니다")

        if policy.max_daily_per_blog > policy.max_daily_total:
            raise ValueError("블로그별 제한이 전체 제한보다 클 수 없습니다")

        # 안전성 검증
        if not policy.safety_mode and policy.min_interval_minutes < 30:
            logger.warning(f"[VALIDATE] 위험한 설정: 안전모드 비활성 + 짧은 간격({policy.min_interval_minutes}분)")

        # 용량 검증
        daily_slots = policy.slots_per_hour * policy.working_hours_count
        if daily_slots < policy.max_daily_total:
            logger.warning(f"[VALIDATE] 시간 제약으로 일일 목표 달성 불가: {daily_slots} < {policy.max_daily_total}")

        logger.debug(f"[VALIDATE] 정책 검증 완료: policy_id={policy.id}")

    async def get_optimal_time_slots(self, credential_id: int) -> Dict[str, Any]:
        """최적 시간 슬롯 추천"""
        policy = await self.get_or_create_default(credential_id)

        # 허용 시간대 내에서 추천 시간 생성
        optimal_slots = []
        for hour in range(policy.allowed_hours_start, policy.allowed_hours_end + 1):
            if policy.is_hour_allowed(hour):
                # 시간당 슬롯 수만큼 생성
                for slot_num in range(policy.slots_per_hour):
                    minute = slot_num * (60 // policy.slots_per_hour)
                    optimal_slots.append({"hour": hour, "minute": minute})

        return {
            "credential_id": credential_id,
            "total_slots": len(optimal_slots),
            "slots": optimal_slots,
            "policy_summary": {
                "min_interval": policy.min_interval_minutes,
                "working_hours": policy.working_hours_count,
                "slots_per_hour": policy.slots_per_hour
            }
        }