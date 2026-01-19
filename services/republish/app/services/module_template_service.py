"""
모듈 템플릿 서비스

Features:
- 미리 정의된 모듈 조합 템플릿 제공
- 템플릿으로 FlowModule 일괄 생성
- 기본 파라미터 자동 설정
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.flow_module import FlowModule
from app.models.module_type import ModuleType


# 모듈 템플릿 정의
MODULE_TEMPLATES = {
    "publish": {
        "name": "발행 템플릿",
        "description": "저장된 포스트를 블로그에 발행합니다",
        "icon": "📤",
        "modules": [
            {"code": "schedule", "order": 1},
            {"code": "post_select", "order": 2, "default_params": {"post_type": "saved"}},
            {"code": "publish_condition", "order": 3},
            {"code": "publish", "order": 4},
        ]
    },
    "republish": {
        "name": "재발행 템플릿 (레거시)",
        "description": "기존 발행된 포스트를 재발행합니다 (레거시 모듈 조합)",
        "icon": "🔄",
        "modules": [
            {"code": "schedule", "order": 1},
            {"code": "post_select", "order": 2, "default_params": {"post_type": "published", "min_age_days": 30}},
            {"code": "publish_condition", "order": 3},
            {"code": "publish", "order": 4},
        ]
    },
    "republish_node": {
        "name": "재발행 노드 템플릿",
        "description": "5개 노드 기반 재발행 파이프라인 (권장)",
        "icon": "🔄",
        "modules": [
            {"code": "republish_blog_fetch", "order": 1},
            {
                "code": "republish_status_classify",
                "order": 2,
                "default_params": {"min_post_count": 10}
            },
            {
                "code": "republish_action_schedule",
                "order": 3,
                "default_params": {
                    "schedule_matrix": [[1]*24 for _ in range(7)]
                }
            },
            {"code": "republish_publish_execute", "order": 4},
            {
                "code": "republish_status_log",
                "order": 5,
                "default_params": {"save_url_history": False, "update_post_count": True}
            },
        ]
    },
    "generate_text": {
        "name": "글 생성 템플릿",
        "description": "AI를 사용해 블로그 글을 생성합니다",
        "icon": "✨",
        "modules": [
            {"code": "schedule", "order": 1},
            {"code": "ai_api", "order": 2},
            {"code": "prompt", "order": 3},
            {"code": "generate", "order": 4, "default_params": {"content_type": "text"}},
            {"code": "result_save", "order": 5},
        ]
    },
    "generate_image": {
        "name": "이미지 생성 템플릿",
        "description": "AI를 사용해 이미지를 생성합니다",
        "icon": "🖼️",
        "modules": [
            {"code": "schedule", "order": 1},
            {"code": "ai_api", "order": 2},
            {"code": "prompt", "order": 3},
            {"code": "generate", "order": 4, "default_params": {"content_type": "image"}},
            {"code": "result_save", "order": 5},
        ]
    },
    "collect": {
        "name": "수집 템플릿",
        "description": "키워드, 제목, 포스트를 수집합니다",
        "icon": "📥",
        "modules": [
            {"code": "schedule", "order": 1},
            {"code": "search_api", "order": 2},
            {"code": "keyword_collect", "order": 3},
            {"code": "title_collect", "order": 4},
            {"code": "post_collect", "order": 5},
            {"code": "result_save", "order": 6},
        ]
    },
}


class ModuleTemplateService:
    """모듈 템플릿 서비스"""

    def __init__(self, db_session: AsyncSession):
        """
        서비스 초기화

        Args:
            db_session: 비동기 DB 세션
        """
        self.db = db_session

    def get_all_templates(self) -> List[Dict[str, Any]]:
        """
        모든 템플릿 목록 반환

        Returns:
            템플릿 목록
        """
        templates = []
        for code, template in MODULE_TEMPLATES.items():
            templates.append({
                "code": code,
                "name": template["name"],
                "description": template["description"],
                "icon": template["icon"],
                "module_codes": [m["code"] for m in template["modules"]],
                "module_count": len(template["modules"]),
            })
        return templates

    def get_template(self, template_code: str) -> Optional[Dict[str, Any]]:
        """
        특정 템플릿 상세 정보 반환

        Args:
            template_code: 템플릿 코드

        Returns:
            템플릿 정보 또는 None
        """
        template = MODULE_TEMPLATES.get(template_code)
        if not template:
            return None

        return {
            "code": template_code,
            "name": template["name"],
            "description": template["description"],
            "icon": template["icon"],
            "modules": template["modules"],
        }

    async def create_modules_from_template(
        self,
        flow_id: int,
        template_code: str,
        user_id: int
    ) -> List[FlowModule]:
        """
        템플릿으로 FlowModule 일괄 생성

        Args:
            flow_id: Flow ID
            template_code: 템플릿 코드
            user_id: 사용자 ID

        Returns:
            생성된 FlowModule 목록

        Raises:
            ValueError: 템플릿이 존재하지 않는 경우
        """
        template = MODULE_TEMPLATES.get(template_code)
        if not template:
            raise ValueError(f"템플릿을 찾을 수 없습니다: {template_code}")

        # 모듈 타입 조회
        module_type_map = await self._get_module_type_map(
            [m["code"] for m in template["modules"]]
        )

        created_modules = []
        for module_config in template["modules"]:
            module_type = module_type_map.get(module_config["code"])
            if not module_type:
                continue

            # FlowModule 생성
            flow_module = FlowModule(
                flow_id=flow_id,
                module_type_id=module_type.id,
                name=module_type.name,
                order=module_config["order"],
                params=module_config.get("default_params", {}),
                is_enabled=True,
            )
            self.db.add(flow_module)
            created_modules.append(flow_module)

        await self.db.flush()

        return created_modules

    async def _get_module_type_map(
        self,
        codes: List[str]
    ) -> Dict[str, ModuleType]:
        """
        모듈 타입 코드로 모듈 타입 맵 조회

        Args:
            codes: 모듈 타입 코드 목록

        Returns:
            코드 -> ModuleType 맵
        """
        result = await self.db.execute(
            select(ModuleType).where(ModuleType.code.in_(codes))
        )
        module_types = result.scalars().all()

        return {mt.code: mt for mt in module_types}

    async def validate_template(self, template_code: str) -> Dict[str, Any]:
        """
        템플릿의 모듈들이 모두 활성화되어 있는지 검증

        Args:
            template_code: 템플릿 코드

        Returns:
            검증 결과 (valid, missing_modules, inactive_modules)
        """
        template = MODULE_TEMPLATES.get(template_code)
        if not template:
            return {"valid": False, "error": "템플릿을 찾을 수 없습니다"}

        codes = [m["code"] for m in template["modules"]]
        module_type_map = await self._get_module_type_map(codes)

        missing = []
        inactive = []

        for code in codes:
            mt = module_type_map.get(code)
            if not mt:
                missing.append(code)
            elif not mt.is_active:
                inactive.append(code)

        return {
            "valid": len(missing) == 0 and len(inactive) == 0,
            "missing_modules": missing,
            "inactive_modules": inactive,
        }
