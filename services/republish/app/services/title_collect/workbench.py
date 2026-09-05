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

# L1(제목 생성) 실행기가 읽는 설정 키. 화면·모듈이 보낸 값을 그대로
# 넘기기 위한 목록이다. 여기서 빠진 키는 기본값이 되살아나 사용자가 끈
# 옵션이 강제로 켜진다.
_L1_KEYS = (
    "dry_run", "use_angles", "angle_sample",
    "cluster_enabled", "cluster_threshold", "cluster_min_size",
    "cluster_max_size", "titles_per_cluster", "titles_per_keyword",
    "cluster_limit", "keyword_limit", "min_inventory",
    "ai_provider", "ai_model",
)


def _ids(value: Any) -> tuple:
    """화면이 보낸 하위주제 id 목록. 문자열도 받는다."""
    if not value:
        return ()
    if isinstance(value, (int, str)):
        value = [value]
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(out)


class TitleWorkbench:
    """한 회차를 수행하고 사람이 읽을 요약을 돌려준다."""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def run_for_module(self, settings: Optional[dict],
                             blogs: Optional[list] = None,
                             force: bool = False) -> Dict[str, Any]:
        """모듈·플로우 진입점. **화면과 같은 실행기를 탄다.**

        수집·추출은 블로그와 무관하므로 회차당 한 번만 돈다. 생성만
        블로그마다 돈다 — 블로그별로 니치가 다르기 때문이다.

        Args:
            settings: 모듈 settings(`{"title": {...}}`)
            blogs: 이 모듈에 연결된 블로그들
            force: 재고가 충분해도 실행(사용자가 직접 누른 단발 실행)
        """
        from .module_settings import normalize

        payload = normalize(settings)
        targets = list(blogs or [])

        out: Dict[str, Any] = {"success": True}
        samples: List[str] = []

        user_settings = await self._user_settings()
        if not user_settings:
            return {"success": False,
                    "error": "사용자 설정이 없습니다. API 키를 먼저 등록하세요"}

        if payload["collect"].get("enabled"):
            result = await self._collect(payload, user_settings)
            out["collect"] = result
            samples.extend(result.get("samples") or [])

        if payload["gen"].get("enabled"):
            rows = []
            for blog in (targets or [None]):
                gen = dict(payload["gen"])
                gen["blog_id"] = getattr(blog, "id", None)
                gen["force"] = force
                rows.append(await self._generate({"gen": gen}, user_settings))
            out["gen"] = _merge_gen(rows)
            samples.extend(out["gen"].get("samples") or [])

        out["samples"] = samples[:100]
        out["made"] = _total(out)
        out["message"] = _summarize(out)
        out["blogs"] = len(targets)
        out["success"] = _succeeded(out)
        out["skipped"] = _skipped(out)
        return out

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
        out["success"] = _succeeded(out)
        out["skipped"] = _skipped(out)
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

        # 화면이 보낸 값을 **그대로** 넘긴다. 예전에는 몇 개만 골라
        # 넘겨서, 빠뜨린 항목(cluster_enabled 등)이 기본값으로 되살아났다
        # — 사용자가 끈 옵션이 강제로 켜졌다.
        title: Dict[str, Any] = {
            key: gen[key] for key in _L1_KEYS if key in gen
        }
        title["enabled"] = True
        title.setdefault("dry_run", True)
        settings = {"title": title}
        # 니치 하나만 채우라는 지시(요약탭 카드)를 그대로 넘긴다.
        runner = TitleModuleRunner(self.db, self.user_id,
                                   subtopic_ids=_ids(gen.get("subtopic_ids")))
        # 화면에서 누른 실행은 재고가 충분해도 돈다 — 조용히 건너뛰면
        # 테스트가 불가능하다. 자동 실행은 재고를 본다.
        out = await runner.run_for_blogs(
            settings, [blog] if blog else [],
            force=bool(gen.get("force", True)))
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


def _merge_gen(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """블로그별 생성 결과를 하나로 합친다."""
    merged: Dict[str, Any] = {"made": 0, "samples": []}
    for row in rows:
        merged["made"] += row.get("made") or 0
        merged["samples"].extend(row.get("samples") or [])
        for key in ("l1", "l3"):
            block = row.get(key)
            if not block:
                continue
            base = merged.setdefault(key, {"made": 0, "samples": []})
            base["made"] += block.get("made") or 0
            base["samples"].extend(block.get("samples") or [])
            # 사유는 하나만 남긴다 — 블로그마다 같은 이유일 때가 많다
            if block.get("error") and not base.get("error"):
                base["error"] = block["error"]
    merged["samples"] = merged["samples"][:100]
    return merged


def _total(out: Dict[str, Any]) -> int:
    """이번 회차에 얻은 제목 수."""
    collect = (out.get("collect") or {}).get("saved") or 0
    gen = (out.get("gen") or {}).get("made") or 0
    return collect + gen


def _errors_of(out: Dict[str, Any]) -> List[str]:
    """켠 섹션이 남긴 실패 사유들."""
    found: List[str] = []
    collect = out.get("collect") or {}
    for block in (collect.get("search"), collect.get("extract"), collect):
        if isinstance(block, dict) and block.get("error"):
            found.append(str(block["error"]))
    gen = out.get("gen") or {}
    for key in ("l1", "l3"):
        block = gen.get(key)
        if isinstance(block, dict) and block.get("error"):
            found.append(str(block["error"]))
    return found


def _skipped(out: Dict[str, Any]) -> bool:
    """할 일이 없어 지나간 회차인가.

    실패도 성공도 아니다. '성공' 으로 적으면 시드가 없어 아무것도 안 한
    회차가 잘 돈 회차와 같아 보인다.
    """
    if _total(out) or _errors_of(out):
        return False
    collect = out.get("collect") or {}
    blocks = [collect.get("search"), collect.get("extract")]
    gen = out.get("gen") or {}
    blocks += [gen.get("l1"), gen.get("l3")]
    seen = [b for b in blocks if isinstance(b, dict)]
    return bool(seen) and all(b.get("skipped") for b in seen)


def _succeeded(out: Dict[str, Any]) -> bool:
    """정말 성공했는가.

    예전에는 무조건 True 였다. AI 제공자를 안 골라 한 편도 못 만든
    회차가 동작로그에 SUCCESS 로 남아, 사용자가 상세를 펼쳐 보기 전에는
    실패를 알 수 없었다.

    얻은 게 하나라도 있으면 성공으로 본다 — 두 섹션 중 하나만 실패한
    회차까지 실패로 적으면 진짜 실패가 묻힌다. 그 경우 메시지 끝에
    ``| ⚠ 사유`` 가 붙는다.
    """
    if _total(out):
        return True
    return not _errors_of(out)


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
