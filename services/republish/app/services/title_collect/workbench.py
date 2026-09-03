"""제목 작업대 실행기 — 수집·생성을 한 회차로 묶는다.

임시제목 탭의 **손으로 돌리는 자리**다. 자동 모듈과 **같은 실행기**를 쓴다.
다른 코드를 타면 한쪽에서만 나는 버그가 생긴다.

켠 섹션만 돈다. 하나만 켜면 그 기능 전용이 된다.

    ☑ 수집 → ① 제목 수집(검색)  ② 도메인 추출(밀린 것 비우기)
    ☑ 생성 → L1 키워드 기반      L3 뉴스 시의성

계획서: docs/plans/title_tab_workplan.md §1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog
from ...models.user_settings import UserSettings
from .niche_gate import NicheGate
from .settings import TitleCollectSettings

logger = get_logger("title_workbench", "app.log")


class TitleWorkbench:
    """한 회차를 수행하고 사람이 읽을 요약을 돌려준다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def run(self, payload: Optional[dict]) -> Dict[str, Any]:
        """실행. `payload` 는 화면이 보낸 설정 그대로다."""
        raw = payload or {}
        out: Dict[str, Any] = {"success": True}
        samples: List[str] = []

        settings = await self._user_settings()
        if not settings:
            return {"success": False,
                    "error": "사용자 설정이 없습니다. API 키를 먼저 등록하세요"}

        if (raw.get("collect") or {}).get("enabled"):
            result = await self._collect(raw, settings)
            out["collect"] = result
            samples.extend(result.get("samples") or [])

        if (raw.get("gen") or {}).get("enabled"):
            result = await self._generate(raw, settings)
            out["gen"] = result
            samples.extend(result.get("samples") or [])

        out["samples"] = samples[:100]
        out["made"] = _total(out)
        out["message"] = _summarize(out)
        return out

    async def _collect(self, raw: dict, settings: Any) -> Dict[str, Any]:
        """수집 섹션. ①과 ②를 각각 켜고 끌 수 있다."""
        from .collector import TitleCollector
        from .extractor import DomainExtractor

        cfg = TitleCollectSettings.parse(raw)
        gate = NicheGate(self.db, cfg.niche_mode)
        result: Dict[str, Any] = {"saved": 0, "samples": []}

        if cfg.search_enabled:
            # 검색은 API 키가 필요하다. 추출(사이트맵)은 필요 없다.
            from ..naver_search_service import NaverSearchService

            search = NaverSearchService(settings)
            if not search.is_configured():
                result["search"] = {"saved": 0,
                                    "error": "네이버 검색 API 키가 없습니다"}
            else:
                found = await TitleCollector(
                    self.db, self.user_id, search).run(cfg, gate)
                result["search"] = found
                result["saved"] += found.get("saved") or 0
                result["samples"].extend(found.get("samples") or [])

        if cfg.extract_enabled:
            found = await DomainExtractor(self.db, self.user_id).run(cfg, gate)
            result["extract"] = found
            result["saved"] += found.get("saved") or 0
            result["samples"].extend(found.get("samples") or [])

        return result

    async def _generate(self, raw: dict, settings: Any) -> Dict[str, Any]:
        """생성 섹션. L1 은 기존 제목 모듈 실행기를 그대로 부른다."""
        gen = raw.get("gen") or {}
        result: Dict[str, Any] = {"made": 0, "samples": []}
        blog = await self._blog(gen.get("blog_id"))

        if gen.get("l1_enabled", True):
            found = await self._run_l1(gen, blog)
            result["l1"] = found
            result["made"] += found.get("made") or 0
            result["samples"].extend(found.get("samples") or [])

        if gen.get("l3_enabled"):
            found = await self._run_l3(gen, settings, blog)
            result["l3"] = found
            result["made"] += found.get("made") or 0
            result["samples"].extend(found.get("samples") or [])

        return result

    async def _run_l1(self, gen: dict, blog: Any) -> Dict[str, Any]:
        """L1 — 제목 모듈과 **같은 실행기**. 화면용 코드를 따로 만들지 않는다."""
        from ..title_gen.runner import TitleModuleRunner

        settings = {"title": {
            "enabled": True,
            "dry_run": bool(gen.get("dry_run", True)),
            "use_angles": bool(gen.get("use_angles", True)),
            "cluster_limit": gen.get("cluster_limit") or 5,
            "keyword_limit": gen.get("keyword_limit") or 20,
            "titles_per_keyword": gen.get("titles_per_keyword") or 3,
            "ai_provider": gen.get("ai_provider"),
            "ai_model": gen.get("ai_model"),
        }}
        runner = TitleModuleRunner(self.db, self.user_id)
        out = await runner.run_for_blogs(
            settings, [blog] if blog else [], force=True)
        preview = [p.get("title") for p in (out.get("preview") or [])
                   if p.get("title")]
        # 생성이 0편일 때 **왜** 인지 화면이 말해야 한다. 옛 결과는
        # "L1 0편" 만 보이고 사유는 로그에만 있었다.
        error = out.get("error")
        if not error and not preview and not (out.get("made") or 0):
            errors = out.get("errors") or []
            error = errors[0] if errors else (
                "제목이 생성되지 않았습니다 — 제목 생성 AI 를 고르거나 "
                "대상 블로그를 선택하세요")
        return {"made": out.get("made") or len(preview),
                "samples": preview[:50], "message": out.get("message"),
                "error": error}

    async def _run_l3(self, gen: dict, settings: Any,
                      blog: Any = None) -> Dict[str, Any]:
        """L3 — 뉴스 요지 + 니치 키워드."""
        from ..naver_news_service import NaverNewsService
        from ..title_gen.news_gen import NewsTitleGenerator

        news = NaverNewsService(settings)
        if not news.is_configured():
            return {"made": 0, "error": "네이버 뉴스 API 키가 없습니다"}

        ask = await self._make_ask(gen, blog)
        generator = NewsTitleGenerator(self.db, self.user_id, news, ask)
        out = await generator.run(days=gen.get("news_days") or 3,
                                  limit=gen.get("news_limit") or 10)
        titles = out.get("titles") or []

        if not gen.get("dry_run", True) and titles:
            await self._store_news(titles, gen.get("expires_days") or 14)

        return {"made": out.get("made") or 0,
                "samples": [t["title"] for t in titles][:50],
                "error": out.get("error")}

    async def _make_ask(self, gen: dict, blog: Any = None):
        """AI 호출 함수.

        고른 것이 없으면 **블로그의 제목 AI 를 쓴다.** 블로그마다 쓰는
        모델이 다른데 매번 화면에서 고르게 하면 실수가 난다. 둘 다 없을
        때만 None 이고, 그때는 만들지 않는다.
        """
        provider = gen.get("ai_provider")
        model = gen.get("ai_model")
        if not provider and blog is not None:
            ai_config = getattr(blog, "ai_config", None) or {}
            title_ai = ai_config.get("title_ai") or {}
            writing_ai = ai_config.get("writing_ai") or {}
            provider = title_ai.get("provider") or writing_ai.get("provider")
            model = model or title_ai.get("model") or writing_ai.get("model")
        if not provider:
            return None

        from ..ai.ai_service import AIService

        service = AIService(self.db, self.user_id)

        async def ask(prompt: str) -> str:
            result = await service.generate(
                prompt=prompt, provider=provider, model=model, max_tokens=300)
            return (result or {}).get("content") or ""

        return ask

    async def _store_news(self, titles: list, expires_days: int) -> None:
        """검증 모드가 아니면 저장한다. 만료일을 함께 박는다."""
        from ..title_gen.news_gen import expires_at
        from ..title_source import SRC_NEWS_GEN
        from .store import TitleStore

        gate = NicheGate(self.db)
        store = TitleStore(self.db, self.user_id, gate)
        deadline = expires_at(expires_days)
        for row in titles:
            await store.add(title=row["title"], url="", keyword=row["keyword"],
                            candidate_id=row.get("candidate_id"),
                            source=SRC_NEWS_GEN, expires_at=deadline)
        await self.db.commit()

    async def _blog(self, blog_id: Any):
        if not blog_id:
            return None
        return (await self.db.execute(
            select(Blog).where(Blog.id == int(blog_id))
        )).scalar_one_or_none()

    async def _user_settings(self):
        return (await self.db.execute(
            select(UserSettings).where(UserSettings.user_id == self.user_id)
        )).scalar_one_or_none()


def _total(out: Dict[str, Any]) -> int:
    """이번 회차에 얻은 제목 수."""
    collect = (out.get("collect") or {}).get("saved") or 0
    gen = (out.get("gen") or {}).get("made") or 0
    return collect + gen


def _summarize(out: Dict[str, Any]) -> str:
    """사람이 읽을 한 줄. 0건이면 **왜** 0건인지 앞에 적는다."""
    parts: List[str] = []
    errors: List[str] = []

    collect = out.get("collect")
    if collect is not None:
        search = collect.get("search") or {}
        extract = collect.get("extract") or {}
        if search:
            parts.append(f"수집 {search.get('saved', 0)}건")
            if search.get("skipped"):
                errors.append(search.get("message", ""))
            if search.get("error"):
                errors.append(search["error"])
        if extract:
            parts.append(f"추출 {extract.get('saved', 0)}건"
                         f"(도메인 {extract.get('domains', 0)}개)")
            missing = extract.get("no_sitemap") or []
            if missing:
                parts.append(f"사이트맵 없음 {len(missing)}개")
            if extract.get("error"):
                errors.append(extract["error"])
        if collect.get("error"):
            errors.append(collect["error"])

    gen = out.get("gen")
    if gen is not None:
        for key, label in (("l1", "L1"), ("l3", "L3")):
            block = gen.get(key)
            if block:
                parts.append(f"{label} {block.get('made', 0)}편")
                if block.get("error"):
                    errors.append(block["error"])

    head = f"⚠ {errors[0]} | " if errors and not _total(out) else ""
    tail = f" | ⚠ {errors[0]}" if errors and _total(out) else ""
    body = " · ".join(parts) or "실행한 섹션이 없습니다"
    return f"{head}{body}{tail}"
