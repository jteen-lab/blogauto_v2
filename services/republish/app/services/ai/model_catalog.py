"""AI 모델 카탈로그 동기화 — 제공자 목록 API 에서 받아 DB 에 반영한다.

순서도: docs/flowcharts/ai_model_catalog.md

설계상 지키는 것
    - 한 제공자가 실패해도 나머지는 진행한다(키가 없으면 그냥 건너뛴다).
    - 사라진 모델은 지우지 않고 is_available=false 로 남긴다. 지우면 그 모델을
      쓰던 블로그 설정이 무엇을 가리켰는지 알 수 없게 된다.
    - 용도 분류는 Google 이 메타데이터를 주므로 그것을 쓰고, 나머지는 이름
      규칙으로 거른다(제공자가 용도를 알려주지 않는다).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.ai_model import (
    CAP_EMBEDDING, CAP_IMAGE, CAP_OTHER, CAP_TEXT, AIModel,
)
from ...schemas.ai_api_key import AIProvider
from ..ai_key_manager import AIKeyManager

logger = get_logger("model_catalog", "app.log")

# 글 생성에 쓸 수 없는 모델을 이름으로 거른다.
# 제공자가 용도를 알려주지 않아(구글 제외) 규칙으로 판단할 수밖에 없다.
_IMAGE_HINTS = ("image", "dall-e", "imagen")
_EMBED_HINTS = ("embed",)
_OTHER_HINTS = (
    "tts", "audio", "whisper", "realtime", "moderation", "transcribe",
    "speech", "search-preview", "computer-use",
)


def classify_by_name(model_id: str) -> str:
    """이름으로 용도를 가른다(구글 외 제공자용)."""
    low = model_id.lower()
    if any(h in low for h in _EMBED_HINTS):
        return CAP_EMBEDDING
    if any(h in low for h in _IMAGE_HINTS):
        return CAP_IMAGE
    if any(h in low for h in _OTHER_HINTS):
        return CAP_OTHER
    return CAP_TEXT


class ModelCatalogService:
    """제공자 모델 목록을 받아 카탈로그에 반영한다."""

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.key_manager = AIKeyManager(db, user_id)

    # ── 제공자별 목록 조회 ────────────────────────────────
    async def _fetch_openai_like(
        self, api_key: str, base_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        import openai

        kwargs = {"api_key": api_key, "timeout": 30}
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.AsyncOpenAI(**kwargs)
        page = await client.models.list()
        out = []
        for m in page.data:
            out.append({
                "model_id": m.id,
                "display_name": m.id,
                "capability": classify_by_name(m.id),
                # OpenAI 는 종료일을 알려준다 — 사라지기 전에 경고할 수 있다
                "shutdown_date": getattr(m, "shutdown_date", None),
            })
        return out

    async def _fetch_google(self, api_key: str) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
            r.raise_for_status()
            data = r.json()

        out = []
        for m in data.get("models", []):
            model_id = m.get("name", "").split("/")[-1]
            if not model_id:
                continue
            methods = m.get("supportedGenerationMethods", [])
            # 구글은 용도를 메타데이터로 준다 — 이름 규칙보다 정확하다
            if "generateContent" in methods:
                cap = CAP_TEXT
            elif "embedContent" in methods:
                cap = CAP_EMBEDDING
            else:
                cap = classify_by_name(model_id)
            out.append({
                "model_id": model_id,
                "display_name": m.get("displayName") or model_id,
                "capability": cap,
                "shutdown_date": None,
            })
        return out

    async def _fetch_anthropic(self, api_key: str) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key,
                         "anthropic-version": "2023-06-01"},
            )
            r.raise_for_status()
            data = r.json()
        return [
            {
                "model_id": m["id"],
                "display_name": m.get("display_name") or m["id"],
                "capability": CAP_TEXT,
                "shutdown_date": None,
            }
            for m in data.get("data", [])
        ]

    async def fetch_provider(self, provider: AIProvider) -> List[Dict[str, Any]]:
        """제공자 하나의 모델 목록. 키가 없으면 빈 목록."""
        key = await self.key_manager.get_available_key(provider)
        if not key:
            return []

        if provider == AIProvider.OPENAI:
            return await self._fetch_openai_like(key.api_key)
        if provider == AIProvider.DEEPSEEK:
            from .deepseek_pricing import BASE_URL

            return await self._fetch_openai_like(key.api_key, BASE_URL)
        if provider == AIProvider.GOOGLE:
            return await self._fetch_google(key.api_key)
        if provider == AIProvider.ANTHROPIC:
            return await self._fetch_anthropic(key.api_key)
        return []

    # ── 반영 ──────────────────────────────────────────────
    async def sync_provider(self, provider: AIProvider) -> Dict[str, Any]:
        """한 제공자를 동기화한다. 실패해도 예외를 밖으로 던지지 않는다."""
        name = provider.value
        try:
            fetched = await self.fetch_provider(provider)
        except Exception as e:
            logger.warning("[MODEL_CATALOG] %s 목록 조회 실패 | %s", name, e)
            return {"provider": name, "ok": False, "error": str(e)[:200],
                    "added": 0, "gone": 0, "kept": 0}

        if not fetched:
            return {"provider": name, "ok": True, "skipped": True,
                    "added": 0, "gone": 0, "kept": 0}

        now = datetime.now(timezone.utc)
        rows = (await self.db.execute(
            select(AIModel).where(AIModel.provider == name)
        )).scalars().all()
        existing = {r.model_id: r for r in rows}
        seen = set()
        added = kept = 0

        for item in fetched:
            mid = item["model_id"]
            seen.add(mid)
            row = existing.get(mid)
            if row is None:
                self.db.add(AIModel(
                    provider=name, model_id=mid,
                    display_name=item["display_name"],
                    capability=item["capability"],
                    shutdown_date=item.get("shutdown_date"),
                    is_available=True,
                    first_seen_at=now, last_seen_at=now, synced_at=now,
                ))
                added += 1
                continue
            row.display_name = item["display_name"]
            row.capability = item["capability"]
            row.shutdown_date = item.get("shutdown_date")
            row.is_available = True
            row.last_seen_at = now
            row.synced_at = now
            kept += 1

        gone = 0
        for mid, row in existing.items():
            if mid in seen:
                continue
            row.synced_at = now
            if row.is_available:
                # 행은 남긴다 — '지원 종료' 표시와 경고에 필요하다
                row.is_available = False
                # 없어진 모델에 추천 배지가 남아 있으면 안 된다
                row.tier = None
                gone += 1

        await self.db.commit()
        logger.info(
            "[MODEL_CATALOG] %s 동기화 | 신규 %d / 사라짐 %d / 유지 %d",
            name, added, gone, kept,
        )
        return {"provider": name, "ok": True, "added": added,
                "gone": gone, "kept": kept}

    async def sync_all(self) -> Dict[str, Any]:
        """등록된 키가 있는 제공자를 모두 동기화한다."""
        results = []
        for provider in (AIProvider.OPENAI, AIProvider.ANTHROPIC,
                         AIProvider.GOOGLE, AIProvider.DEEPSEEK):
            results.append(await self.sync_provider(provider))

        total = {
            "added": sum(r["added"] for r in results),
            "gone": sum(r["gone"] for r in results),
            "kept": sum(r["kept"] for r in results),
        }
        return {"success": True, "results": results, "total": total}
