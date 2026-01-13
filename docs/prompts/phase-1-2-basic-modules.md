# Phase 1-2: 기본 모듈 구현

> **작업 유형**: 신규 개발  
> **예상 시간**: 4-6시간  
> **우선순위**: P0 (Critical)  
> **선행 작업**: Phase 1-1 완료

---

## 📋 작업 개요

노드 방식 모듈 시스템의 기본 모듈들을 구현합니다.

### 목표
- 트리거 모듈: ScheduleTrigger, ManualTrigger
- 데이터 모듈: DBQuery, DBSave
- 액션 모듈: Publish (핵심)

### 작업 위치
```
services/republish/app/modules/     # 🆕 신규 디렉토리
```

---

## 📁 생성할 파일

### 1. 디렉토리 구조

```
app/modules/
├── __init__.py
├── triggers/
│   ├── __init__.py
│   ├── schedule.py
│   └── manual.py
├── data/
│   ├── __init__.py
│   ├── db_query.py
│   └── db_save.py
└── actions/
    ├── __init__.py
    └── publish.py
```

### 2. app/modules/__init__.py (~30줄)

```python
"""
BlogAuto V2 모듈 패키지

노드 방식 모듈들을 등록합니다.
"""

from app.core.registry import ModuleRegistry

# 트리거 모듈
from app.modules.triggers.schedule import ScheduleTriggerModule
from app.modules.triggers.manual import ManualTriggerModule

# 데이터 모듈
from app.modules.data.db_query import DBQueryModule
from app.modules.data.db_save import DBSaveModule

# 액션 모듈
from app.modules.actions.publish import PublishModule


def register_all_modules():
    """모든 기본 모듈 등록"""
    # 트리거
    ModuleRegistry.register(ScheduleTriggerModule())
    ModuleRegistry.register(ManualTriggerModule())
    
    # 데이터
    ModuleRegistry.register(DBQueryModule())
    ModuleRegistry.register(DBSaveModule())
    
    # 액션
    ModuleRegistry.register(PublishModule())


__all__ = [
    "register_all_modules",
    "ScheduleTriggerModule",
    "ManualTriggerModule",
    "DBQueryModule",
    "DBSaveModule",
    "PublishModule",
]
```

### 3. app/modules/triggers/schedule.py (~100줄)

```python
"""
스케줄 트리거 모듈

지정된 시간에 플로우를 시작합니다.
"""

from datetime import datetime
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class ScheduleTriggerModule(ModuleInterface):
    """스케줄 트리거"""
    
    @property
    def module_type(self) -> ModuleType:
        return ModuleType.TRIGGER
    
    @property
    def name(self) -> str:
        return "schedule_trigger"
    
    @property
    def display_name(self) -> str:
        return "스케줄 트리거"
    
    @property
    def description(self) -> str:
        return "지정된 시간에 플로우를 시작합니다."
    
    @property
    def icon(self) -> str:
        return "⏰"
    
    @property
    def inputs(self) -> list[PortType]:
        return []  # 트리거는 입력 없음
    
    @property
    def outputs(self) -> list[PortType]:
        return [PortType.MAIN]
    
    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="cron",
                type="string",
                required=False,
                default="0 9 * * *",
                description="Cron 표현식"
            ),
            ModuleParam(
                name="timezone",
                type="string",
                required=False,
                default="Asia/Seoul",
                description="시간대"
            )
        ]
    
    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """트리거 실행"""
        trigger_item = BlogAutoItem(
            json={
                "trigger_type": "schedule",
                "triggered_at": datetime.now().isoformat(),
                "cron": params.get("cron", "0 9 * * *"),
                "timezone": params.get("timezone", "Asia/Seoul"),
                "is_test": context.is_test
            },
            meta=ItemMeta(source_module=self.name)
        )
        
        context.log(f"스케줄 트리거 실행")
        return ModuleResult.ok([trigger_item])
```

### 4. app/modules/triggers/manual.py (~70줄)

```python
"""
수동 트리거 모듈

수동으로 플로우를 시작합니다. (1회 실행용)
"""

# ScheduleTriggerModule과 유사하게 구현
# trigger_type: "manual"
```

### 5. app/modules/data/db_query.py (~150줄)

```python
"""
DB 조회 모듈

데이터베이스에서 데이터를 조회합니다.
"""

from typing import Any
from sqlalchemy import select
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class DBQueryModule(ModuleInterface):
    """DB 조회 모듈"""
    
    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA
    
    @property
    def name(self) -> str:
        return "db_query"
    
    @property
    def display_name(self) -> str:
        return "DB 조회"
    
    @property
    def description(self) -> str:
        return "데이터베이스에서 데이터를 조회합니다."
    
    @property
    def icon(self) -> str:
        return "🗄️"
    
    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="table",
                type="select",
                required=True,
                description="조회할 테이블",
                options=[
                    {"value": "blogs", "label": "블로그"},
                    {"value": "url_history", "label": "URL 히스토리"},
                ]
            ),
            ModuleParam(
                name="filter",
                type="json",
                required=False,
                default={},
                description="필터 조건"
            ),
            ModuleParam(
                name="limit",
                type="number",
                required=False,
                default=100,
                description="최대 조회 개수"
            ),
            ModuleParam(
                name="order_by",
                type="string",
                required=False,
                default="id",
                description="정렬 기준"
            ),
            ModuleParam(
                name="order_desc",
                type="boolean",
                required=False,
                default=False,
                description="내림차순"
            )
        ]
    
    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """DB 조회 실행"""
        table = params.get("table")
        filter_cond = params.get("filter", {})
        limit = params.get("limit", 100)
        
        context.log(f"DB 조회: {table}, limit={limit}")
        
        try:
            model = self._get_model(table)
            if not model:
                return ModuleResult.fail(f"알 수 없는 테이블: {table}")
            
            # 쿼리 실행
            query = select(model)
            
            # 필터 적용
            for key, value in filter_cond.items():
                if hasattr(model, key):
                    query = query.where(getattr(model, key) == value)
            
            # 정렬 및 제한
            order_by = params.get("order_by", "id")
            order_desc = params.get("order_desc", False)
            if hasattr(model, order_by):
                col = getattr(model, order_by)
                query = query.order_by(col.desc() if order_desc else col)
            
            query = query.limit(limit)
            
            result = await context.db_session.execute(query)
            rows = result.scalars().all()
            
            # 아이템 변환
            output_items = []
            for row in rows:
                item = BlogAutoItem(
                    json=self._row_to_dict(row),
                    meta=ItemMeta(source_module=self.name)
                )
                output_items.append(item)
            
            context.log(f"DB 조회 완료: {len(output_items)}건")
            return ModuleResult.ok(output_items)
            
        except Exception as e:
            context.log(f"DB 조회 실패: {e}", level="error")
            return ModuleResult.fail(str(e))
    
    def _get_model(self, table: str):
        """테이블명으로 모델 반환"""
        from app.models.blog import Blog
        from app.models.url_history import URLHistory
        
        models = {
            "blogs": Blog,
            "url_history": URLHistory,
        }
        return models.get(table)
    
    def _row_to_dict(self, row) -> dict:
        """ORM 객체를 딕셔너리로"""
        if hasattr(row, "__table__"):
            return {c.name: getattr(row, c.name) for c in row.__table__.columns}
        return {}
```

### 6. app/modules/data/db_save.py (~120줄)

```python
"""
DB 저장 모듈

데이터를 데이터베이스에 저장합니다.
"""

# DBQueryModule과 유사한 구조
# 입력 아이템을 지정된 테이블에 저장
# update_or_insert 옵션 제공
```

### 7. app/modules/actions/publish.py (~180줄)

```python
"""
발행 모듈

블로그에 포스트를 발행합니다.
재발행과 신규 발행 모두 이 모듈을 사용합니다.
"""

from datetime import datetime
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class PublishModule(ModuleInterface):
    """발행 모듈 (핵심)"""
    
    @property
    def module_type(self) -> ModuleType:
        return ModuleType.ACTION
    
    @property
    def name(self) -> str:
        return "publish"
    
    @property
    def display_name(self) -> str:
        return "발행"
    
    @property
    def description(self) -> str:
        return "블로그에 포스트를 발행합니다."
    
    @property
    def icon(self) -> str:
        return "📤"
    
    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="platform",
                type="select",
                required=True,
                default="wordpress",
                description="발행 플랫폼",
                options=[
                    {"value": "wordpress", "label": "워드프레스"},
                    {"value": "blogger", "label": "블로거"},
                ]
            ),
            ModuleParam(
                name="publish_mode",
                type="select",
                required=False,
                default="update",
                description="발행 모드",
                options=[
                    {"value": "new", "label": "신규 발행"},
                    {"value": "update", "label": "업데이트 (재발행)"}
                ]
            ),
            ModuleParam(
                name="update_date",
                type="boolean",
                required=False,
                default=True,
                description="발행 날짜 업데이트"
            )
        ]
    
    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """발행 실행"""
        platform = params.get("platform", "wordpress")
        publish_mode = params.get("publish_mode", "update")
        update_date = params.get("update_date", True)
        
        context.log(f"발행 시작: {platform}, mode={publish_mode}")
        
        results = []
        for item in items:
            try:
                blog_id = item.get("blog_id") or item.get("id")
                
                if not blog_id:
                    context.log("blog_id 누락", level="warning")
                    continue
                
                # 플랫폼별 발행
                if platform == "wordpress":
                    result = await self._publish_wordpress(
                        blog_id, item, update_date, context
                    )
                elif platform == "blogger":
                    result = await self._publish_blogger(
                        blog_id, item, update_date, context
                    )
                else:
                    result = {"success": False, "error": f"미지원: {platform}"}
                
                result_item = BlogAutoItem(
                    json={
                        **item.json,
                        "publish_result": result,
                        "published_at": datetime.now().isoformat()
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                results.append(result_item)
                
            except Exception as e:
                context.log(f"발행 실패: {e}", level="error")
                error_item = BlogAutoItem(
                    json={
                        **item.json,
                        "publish_result": {"success": False, "error": str(e)}
                    },
                    meta=ItemMeta(source_module=self.name)
                )
                results.append(error_item)
        
        success_count = sum(
            1 for r in results 
            if r.get("publish_result", {}).get("success")
        )
        context.log(f"발행 완료: {success_count}/{len(results)}")
        
        return ModuleResult.ok(results)
    
    async def _publish_wordpress(
        self,
        blog_id: int,
        item: BlogAutoItem,
        update_date: bool,
        context: ExecutionContext
    ) -> dict:
        """워드프레스 발행"""
        # 기존 republish 로직 재사용
        # TODO: WordPressService 연동
        try:
            # 테스트 모드면 실제 발행 안함
            if context.is_test:
                return {"success": True, "url": "http://test.com/post/1", "test_mode": True}
            
            # 실제 발행 로직
            # from app.services.wordpress_service import WordPressService
            # ...
            
            return {"success": True, "url": "http://example.com/post/1"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _publish_blogger(
        self,
        blog_id: int,
        item: BlogAutoItem,
        update_date: bool,
        context: ExecutionContext
    ) -> dict:
        """블로거 발행"""
        # TODO: Blogger API 구현
        return {"success": False, "error": "미구현"}
```

---

## ✅ 완료 조건

### 필수
- [ ] app/modules/__init__.py (register_all_modules)
- [ ] app/modules/triggers/schedule.py
- [ ] app/modules/triggers/manual.py
- [ ] app/modules/data/db_query.py
- [ ] app/modules/data/db_save.py
- [ ] app/modules/actions/publish.py
- [ ] 모든 모듈 < 200줄
- [ ] ModuleInterface 구현 완료

### 검증
- [ ] ModuleRegistry에 등록 성공
- [ ] 각 모듈 execute 호출 가능

---

## 🚨 주의사항

1. **기존 로직 재사용**: publish 모듈에서 기존 WordPress/Blogger 서비스 활용
2. **테스트 모드**: is_test=True일 때 실제 발행하지 않음
3. **에러 처리**: 개별 아이템 실패해도 전체 중단하지 않음

---

## 📝 커밋 메시지

```
feat(modules): 기본 노드 모듈 구현

- triggers: schedule, manual
- data: db_query, db_save
- actions: publish

관련: DCR-001
```
