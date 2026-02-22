"""
Growth Profile Resolver

블로그 포스트 수 -> 성장 단계 매핑, 모듈별 간격 계산, 활성 시간 체크.
Phase B에서 Flow 실행 시 Step 0으로 호출됨.

설계 문서: growth_stage_strategy_plan.md - Section 6
"""
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict

from .flow_execution_context import (
    FlowExecutionContext,
    StageParams,
    ModuleIntervalParams,
)

logger = logging.getLogger(__name__)


class GrowthProfileResolver:
    """
    Growth Profile 해석기

    블로그별 포스트 수를 기반으로 적절한 성장 단계를 결정하고,
    모듈별 실행 간격을 계산하여 FlowExecutionContext를 생성한다.

    주요 기능:
        - stages 배열 유효성 검증
        - schedule_matrix 기반 활성 시간 수 계산
        - 포스트 수 -> 성장 단계 매핑 (경계값 inclusive)
        - FlowExecutionContext 빌드 (Phase B Step 0)
    """

    @staticmethod
    def validate_stages(stages: list) -> Tuple[bool, Optional[str]]:
        """stages 배열의 유효성 검증 (필수 필드, 연속성, 경계값)

        Args:
            stages: settings["stages"] 배열

        Returns:
            (True, None) 또는 (False, "에러 메시지")
        """
        if not stages:
            return False, "stages 배열이 비어있습니다"

        required_fields = ["name", "label", "post_count_min"]
        for i, stage in enumerate(stages):
            for req_field in required_fields:
                if req_field not in stage:
                    return False, f"stage[{i}]에 '{req_field}' 필드가 없습니다"

            # 첫 번째 stage: post_count_min == 0 필수
            if i == 0 and stage["post_count_min"] != 0:
                return False, (
                    f"첫 번째 stage의 post_count_min은 0이어야 합니다 "
                    f"(현재: {stage['post_count_min']})"
                )

            # 연속성 검증 (두 번째 stage부터)
            if i > 0:
                prev_max = stages[i - 1].get("post_count_max")
                curr_min = stage["post_count_min"]
                if prev_max is None:
                    return False, (
                        f"stage[{i - 1}]의 post_count_max가 None인데 "
                        f"다음 stage가 존재합니다"
                    )
                if curr_min != prev_max + 1:
                    return False, (
                        f"stage[{i}]의 post_count_min({curr_min})이 "
                        f"이전 stage의 post_count_max({prev_max}) + 1 = "
                        f"{prev_max + 1}과 다릅니다"
                    )

        return True, None

    @staticmethod
    def count_active_hours(
        schedule_matrix: Optional[list],
        weekday: Optional[int] = None,
    ) -> int:
        """
        schedule_matrix에서 특정 요일(또는 오늘)의 활성 시간 수 계산

        Args:
            schedule_matrix: 7x24 bool 배열. None이면 24 반환.
            weekday: 0=월~6=일. None이면 오늘 요일 사용.

        Returns:
            활성 시간 수 (0~24). matrix가 None이거나 형태가 잘못되면 24 반환.
        """
        if schedule_matrix is None:
            return 24

        if weekday is None:
            weekday = datetime.now().weekday()

        # matrix 유효성 검증 (7x24 형태가 아니면 24 반환)
        if (
            not isinstance(schedule_matrix, list)
            or len(schedule_matrix) != 7
            or not isinstance(schedule_matrix[weekday], list)
            or len(schedule_matrix[weekday]) != 24
        ):
            return 24

        return sum(1 for h in schedule_matrix[weekday] if h)

    @staticmethod
    def resolve_stage_for_blog(
        post_count: int,
        stages: list,
    ) -> Optional[dict]:
        """
        블로그의 포스트 수로 적절한 성장 단계(stage) 결정

        경계값 규칙 (작업계획서 Q3):
            post_count_max는 inclusive.
            50글 = 해당 스테이지, 51글 = 다음 스테이지.

        Args:
            post_count: 블로그의 현재 누적 포스트 수
            stages: settings["stages"] 배열

        Returns:
            매칭된 stage dict. stages가 비어있으면 None.
            어떤 구간에도 매칭되지 않으면 마지막 stage 반환.

        Examples:
            stages = [{min:0, max:50}, {min:51, max:150}, {min:151, max:None}]
            post_count=50  -> stages[0] (inclusive)
            post_count=51  -> stages[1]
            post_count=999 -> stages[2] (max=None이므로)
        """
        if not stages:
            return None

        for stage in stages:
            stage_min = stage.get("post_count_min", 0)
            stage_max = stage.get("post_count_max")

            if stage_max is None:
                # 마지막 구간 (무제한)
                if post_count >= stage_min:
                    return stage
            else:
                # post_count_max inclusive
                if stage_min <= post_count <= stage_max:
                    return stage

        # 어떤 구간에도 매칭되지 않으면 마지막 구간 적용
        logger.warning(
            "[GP_RESOLVE] post_count=%d가 어떤 구간에도 매칭되지 않음. "
            "마지막 구간 적용",
            post_count,
        )
        return stages[-1]

    @classmethod
    def _map_blogs_to_stages(
        cls,
        blog_post_counts: Dict[int, int],
        stages: list,
        active_hours: int,
    ) -> Dict[int, StageParams]:
        """블로그별 포스트 수 기반으로 스테이지 매핑 수행

        Args:
            blog_post_counts: {blog_id: post_count} 매핑
            stages: 검증 완료된 stages 배열
            active_hours: 오늘 활성 시간 수

        Returns:
            {blog_id: StageParams} 매핑
        """
        blog_stages: Dict[int, StageParams] = {}
        for blog_id, post_count in blog_post_counts.items():
            stage_dict = cls.resolve_stage_for_blog(post_count, stages)
            if stage_dict is None:
                continue

            stage_params = StageParams.from_stage_dict(
                stage_dict, active_hours
            )
            blog_stages[blog_id] = stage_params
            logger.info(
                "[GP_RESOLVE] blog_id=%d | posts=%d | stage=%s "
                "| gen=%smin | pub=%smin | rep=%smin",
                blog_id, post_count, stage_dict["name"],
                stage_params.generate.computed_interval,
                stage_params.publish.computed_interval,
                stage_params.republish.computed_interval,
            )
        return blog_stages

    @classmethod
    def build_execution_context(
        cls,
        flow_id: int,
        gp_settings: dict,
        blog_post_counts: Dict[int, int],
    ) -> FlowExecutionContext:
        """Flow 실행 시 FlowExecutionContext 생성 (Phase B Step 0)

        Args:
            flow_id: Flow ID
            gp_settings: Growth Profile 모듈의 settings dict
            blog_post_counts: {blog_id: post_count} 매핑

        Returns:
            FlowExecutionContext (blog_stages 매핑 완료)

        Raises:
            ValueError: stages 유효성 검증 실패 시
        """
        schedule_matrix = gp_settings.get("schedule_matrix")
        jitter = gp_settings.get("jitter")
        stages = gp_settings.get("stages", [])

        # stages 유효성 검증
        valid, error = cls.validate_stages(stages)
        if not valid:
            logger.error("[GP_RESOLVE] stages 검증 실패: %s", error)
            raise ValueError(f"Growth Profile stages 검증 실패: {error}")

        active_hours = cls.count_active_hours(schedule_matrix)
        blog_stages = cls._map_blogs_to_stages(
            blog_post_counts, stages, active_hours
        )

        context = FlowExecutionContext(
            flow_id=flow_id,
            growth_profile=gp_settings,
            schedule_matrix=schedule_matrix,
            jitter=jitter,
            blog_stages=blog_stages,
        )
        logger.info(
            "[GP_RESOLVE] context 생성 완료 | flow_id=%d "
            "| blogs=%d | active_hours=%d",
            flow_id, len(blog_stages), active_hours,
        )
        return context
