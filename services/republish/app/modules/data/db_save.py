"""
DB 저장 모듈

데이터를 데이터베이스에 저장합니다.
노드 체인에서 발행 결과를 autorun_logs에 저장하는 마지막 단계로 사용됩니다.
"""

from datetime import datetime
from typing import Any, Optional
from sqlalchemy import select
from app.core.interface import (
    ModuleInterface, ModuleType, ModuleParam,
    ModuleResult, PortType, ExecutionContext
)
from app.core.item import BlogAutoItem, ItemList, ItemMeta


class DBSaveModule(ModuleInterface):
    """DB 저장 모듈"""

    @property
    def module_type(self) -> ModuleType:
        return ModuleType.DATA

    @property
    def name(self) -> str:
        return "db_save"

    @property
    def display_name(self) -> str:
        return "DB 저장"

    @property
    def description(self) -> str:
        return "데이터를 데이터베이스에 저장합니다."

    @property
    def icon(self) -> str:
        return "💾"

    @property
    def inputs(self) -> list[PortType]:
        return [PortType.MAIN]

    @property
    def outputs(self) -> list[PortType]:
        return [PortType.MAIN]

    @property
    def params(self) -> list[ModuleParam]:
        return [
            ModuleParam(
                name="table",
                type="select",
                required=True,
                description="저장할 테이블",
                options=[
                    {"value": "url_history", "label": "URL 히스토리"},
                    {"value": "autorun_logs", "label": "오토런 로그"},
                    {"value": "temp_titles", "label": "임시 제목"},
                ]
            ),
            ModuleParam(
                name="mode",
                type="select",
                required=False,
                default="insert",
                description="저장 모드",
                options=[
                    {"value": "insert", "label": "새로 저장"},
                    {"value": "update", "label": "업데이트"},
                    {"value": "upsert", "label": "저장 또는 업데이트"}
                ]
            ),
            ModuleParam(
                name="key_field",
                type="string",
                required=False,
                default="id",
                description="업데이트 시 키 필드"
            ),
            ModuleParam(
                name="map_publish_result",
                type="boolean",
                required=False,
                default=True,
                description="Publish 결과를 autorun_logs 필드로 매핑"
            )
        ]

    async def execute(
        self,
        items: ItemList,
        params: dict,
        context: ExecutionContext
    ) -> ModuleResult:
        """DB 저장 실행"""
        table = params.get("table")
        mode = params.get("mode", "insert")
        key_field = params.get("key_field", "id")
        map_publish = params.get("map_publish_result", True)

        context.log(f"[DB_SAVE] 시작 | table={table} | mode={mode} | items={len(items)}")

        try:
            # autorun_logs 특별 처리 (Publish 결과 매핑)
            if table == "autorun_logs" and map_publish:
                return await self._save_autorun_logs(context, items)

            # temp_titles 특별 처리 (TitleCollector 결과 매핑)
            if table == "temp_titles":
                return await self._save_temp_titles(context, items)

            model = self._get_model(table)
            if not model:
                return ModuleResult.fail(f"알 수 없는 테이블: {table}")

            saved_items = []
            for item in items:
                data = item.json.copy()

                if mode == "insert":
                    obj = model(**self._filter_model_fields(model, data))
                    context.db_session.add(obj)

                elif mode == "update":
                    key_value = data.get(key_field)
                    if not key_value:
                        continue
                    result = await context.db_session.execute(
                        select(model).where(getattr(model, key_field) == key_value)
                    )
                    obj = result.scalar_one_or_none()
                    if obj:
                        for k, v in self._filter_model_fields(model, data).items():
                            if k != key_field:
                                setattr(obj, k, v)

                elif mode == "upsert":
                    key_value = data.get(key_field)
                    obj = None
                    if key_value:
                        result = await context.db_session.execute(
                            select(model).where(getattr(model, key_field) == key_value)
                        )
                        obj = result.scalar_one_or_none()
                    if obj:
                        for k, v in self._filter_model_fields(model, data).items():
                            if k != key_field:
                                setattr(obj, k, v)
                    else:
                        obj = model(**self._filter_model_fields(model, data))
                        context.db_session.add(obj)

                saved_item = BlogAutoItem(
                    json={**item.json, "saved": True},
                    meta=ItemMeta(source_module=self.name)
                )
                saved_items.append(saved_item)

            await context.db_session.commit()
            context.log(f"[DB_SAVE] 완료 | {len(saved_items)}건")
            return ModuleResult.ok(saved_items)

        except Exception as e:
            await context.db_session.rollback()
            context.log(f"[DB_SAVE] 실패 | error={e}", level="error")
            return ModuleResult.fail(str(e))

    async def _save_autorun_logs(
        self,
        context: ExecutionContext,
        items: ItemList
    ) -> ModuleResult:
        """
        Publish 결과를 autorun_logs 테이블에 저장

        입력 (Publish 출력):
        - blog_id, blog_name, platform
        - post_id, post_title, post_url
        - publish_result: {success, message, ...}
        - published_at

        AutorunLog 실제 필드:
        - user_id, flow_id (필수)
        - action, status
        - flow_name, module_name, blog_name, post_title, action_time
        - message, execution_duration_ms
        """
        from app.models.autorun_log import AutorunLog
        from app.models.flow import Flow

        saved_items = []

        # flow에서 user_id와 flow_name 가져오기
        user_id = 1  # 기본값
        flow_name = context.flow_name or ""
        try:
            result = await context.db_session.execute(
                select(Flow).where(Flow.id == context.flow_id)
            )
            flow = result.scalar_one_or_none()
            if flow:
                user_id = flow.user_id
                flow_name = flow.name
        except Exception:
            pass

        for item in items:
            data = item.json
            publish_result = data.get("publish_result", {})

            # action_time 생성 (현재 시간)
            action_time = datetime.now().strftime("%Y/%m/%d %H:%M")

            log_entry = AutorunLog(
                user_id=user_id,
                flow_id=context.flow_id,
                action="republish",
                status="success" if publish_result.get("success") else "failed",
                flow_name=flow_name,
                module_name="재발행",
                blog_name=data.get("blog_name", ""),
                post_title=data.get("post_title", ""),
                action_time=action_time,
                message=publish_result.get("message", "")
            )

            context.db_session.add(log_entry)

            saved_item = BlogAutoItem(
                json={**item.json, "saved": True, "log_id": None},
                meta=ItemMeta(source_module=self.name)
            )
            saved_items.append(saved_item)

        await context.db_session.commit()

        context.log(
            f"[DB_SAVE] autorun_logs 저장 완료 | flow_id={context.flow_id} | "
            f"{len(saved_items)}건"
        )
        return ModuleResult.ok(saved_items)

    async def _save_temp_titles(
        self,
        context: ExecutionContext,
        items: ItemList
    ) -> ModuleResult:
        """
        TitleCollector 결과를 temp_titles 테이블에 저장

        입력 (TitleCollector 출력):
        - title: 수집된 제목
        - source: 수집 소스 (naver_news, google_news, naver_webdoc)
        - keyword: 검색 키워드
        - link: 원본 URL

        TempTitle 필수 필드:
        - title (String): 제목
        - source_blog_url (String): 블로그/소스 URL
        - source_post_url (String): 포스트 URL
        - collection_stage (String): 수집 단계
        """
        from app.models.title import TempTitle

        saved_items = []
        skipped_count = 0

        for item in items:
            data = item.json
            title = data.get("title", "")

            # 제목이 없으면 스킵
            if not title or len(title) < 5:
                skipped_count += 1
                continue

            # 필드 매핑
            source = data.get("source", "unknown")
            link = data.get("link", "")

            # source_blog_url: 소스 도메인 추출 또는 기본값
            source_blog_url = self._extract_domain(link) if link else f"https://{source}"

            # source_post_url: 원본 링크 사용
            source_post_url = link if link else f"https://{source}/unknown"

            # collection_stage: 소스 기반 결정
            collection_stage = "keyword_search" if data.get("keyword") else "random_crawl"

            temp_title = TempTitle(
                title=title,
                source_blog_url=source_blog_url,
                source_post_url=source_post_url,
                collection_stage=collection_stage,
                status="new"
            )

            context.db_session.add(temp_title)

            saved_item = BlogAutoItem(
                json={**item.json, "saved": True},
                meta=ItemMeta(source_module=self.name)
            )
            saved_items.append(saved_item)

        await context.db_session.commit()

        context.log(
            f"[DB_SAVE] temp_titles 저장 완료 | flow_id={context.flow_id} | "
            f"저장={len(saved_items)}건 | 스킵={skipped_count}건"
        )
        return ModuleResult.ok(saved_items)

    def _extract_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url
        except Exception:
            return url

    def _get_model(self, table: str):
        """테이블명으로 모델 반환"""
        from app.models.url_history import BlogUrlHistory
        from app.models.autorun_log import AutorunLog
        from app.models.title import TempTitle

        models = {
            "url_history": BlogUrlHistory,
            "autorun_logs": AutorunLog,
            "temp_titles": TempTitle,
        }
        return models.get(table)

    def _filter_model_fields(self, model, data: dict) -> dict:
        """모델에 존재하는 필드만 필터링"""
        if hasattr(model, "__table__"):
            valid_columns = {c.name for c in model.__table__.columns}
            return {k: v for k, v in data.items() if k in valid_columns}
        return data
