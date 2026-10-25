"""리뉴얼 전용 생성 경로 (P2b).

기존 ContentGenerator.generate()를 건드리지 않고, 그 하위 서비스
인스턴스(제목재조합·참조수집·본문생성·내부링크·치환·이미지생성)를
재사용해 라이브 글을 현재 양식·최신 내용으로 재생성한다.

- 제목: plan.recombine_title=False면 라이브 제목 그대로, True면 재조합.
- 이미지: plan.image_action="reuse"면 기존 이미지 URL을 주입, "new"면 생성.
- 출력만 만들고 라이브 글 갱신은 하지 않는다(P2c가 담당, 데이터 변경 분리).
"""
import random
import re
from dataclasses import dataclass, field
from typing import Optional

# 기존 글 주입 시 토큰 폭증 방지용 상한
EXISTING_CONTENT_MAX_CHARS = 8000

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logger import get_logger
from ...models.blog import Blog, BlogPlatform
from ...models.module import Module
from ..generation.content_generator_helper import generate_content_with_meta
from ..generation import lead_keyword_flow
from ..generation.generator import ContentGenerator
from .renewal_plan import RenewalPlan

# 모듈에 리뉴얼 문구가 없을 때 쓰는 기본값. 성과 판정이 모드를 정했는데
# 문구가 없다고 아무 일도 안 하면 판정이 무의미해진다.
_AUGMENT_TEXT = (
    "기존 글의 구조와 이미 잘 쓰인 부분은 그대로 두고, 낡은 정보만 최신으로 "
    "고치고 빠진 내용을 덧붙여 더 충실하게 만드세요. 전체를 새로 쓰지 마세요."
)
_REWRITE_TEXT = (
    "이 주제를 처음부터 다시 쓰세요. 기존 글은 검색에서 성과를 내지 못했으므로 "
    "구성과 접근을 바꿔야 합니다. 검색한 사람이 제목을 보고 찾는 답(얼마인지·몇 개인지·"
    "어떻게 계산하는지)을 첫 부분에 숫자와 계산 예시로 주고, 본문은 공백 빼고 1,800자 "
    "이상으로 쓰세요. 요금·비용 글은 하루 값에서 멈추지 말고 한 달 값까지 계산하세요"
    "(예: 300W × 하루 8시간 × 30일 = 72kWh). 전기요금처럼 누진 구간이 있는 요금은 "
    "'실제 요금은 사용량 구간에 따라 달라지니 한전 요금표로 확인하세요' 같은 한 줄을 넣으세요. "
    "근거 없는 인과(예: '물통을 자주 비우면 전력 소모가 줄어듭니다')는 쓰지 마세요."
)

logger = get_logger("renewal_generator", "app.log")


def inject_featured(blog: Blog, html: str, image_url: str, title: str) -> str:
    """대표 이미지를 본문 맨 앞에 넣는다(alt = 제목 — 앞 검색어가 맨 앞에 온다)."""
    from ..publishing.html_injector import HtmlInjector

    platform = (blog.platform.value if isinstance(blog.platform, BlogPlatform)
                else str(blog.platform))
    return HtmlInjector().inject_featured_image(
        html=html, image_url=image_url, title=title,
        editor_type=getattr(blog, "editor_type", "classic"), platform=platform)


class _WriterBlog:
    """블로그를 그대로 보이되 글쓰기 모델만 바꾼 대리 객체(DB 에 쓰지 않음)."""

    def __init__(self, blog: Blog, model: tuple) -> None:
        self._blog = blog
        ai = dict(getattr(blog, "ai_config", None) or {})
        ai["writing_ai"] = {"provider": model[0], "model": model[1]}
        self.ai_config = ai

    def __getattr__(self, name: str):
        return getattr(self._blog, name)


@dataclass
class RenewalContent:
    """리뉴얼 재생성 결과(라이브 글 갱신 전 산출물)."""

    success: bool
    title: str = ""
    content_html: str = ""
    image_url: Optional[str] = None
    seo_meta: Optional[dict] = None
    error: str = ""
    warnings: list = field(default_factory=list)
    title_note: str = ""
    merge: bool = False     # 겹침 검사로 제목 유지 → 리뉴얼 대신 합치기 후보


class RenewalGenerator:
    """리뉴얼 재생성 오케스트레이터 (생성 파이프라인 하위 서비스 재사용)."""

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None) -> None:
        self.db = db
        # 동일 설정의 하위 서비스 인스턴스를 그대로 재사용해 현재 양식 일치.
        self.gen = ContentGenerator(db, user_id)

    async def regenerate(
        self,
        blog: Blog,
        module: Module,
        live_title: str,
        plan: RenewalPlan,
        subtopic_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        text_replace_enabled: bool = True,
        existing_content: str = "",
        gap_instruction: str = "",
        strict_title: bool = False,
        main_title=None,
        self_url: str = "",
        fact_cfg: Optional[dict] = None,
    ) -> RenewalContent:
        """라이브 글을 현재 양식·최신 내용으로 재생성한다.

        existing_content: 라이브 글 본문(HTML). 리뉴얼 프롬프트가 '추가/새'
            모드일 때 기존 내용 보존·확장용으로 주입한다.
        gap_instruction: 서치콘솔 실측으로 뽑은 '독자가 답을 못 찾은 것'.
            보강할 때만 들어온다.
        strict_title: 새 글과 같은 N1·N4·중복 검사로 제목을 정한다(renewal_title).
        main_title: 매칭된 정식제목(핵심어용).
        self_url: 이 글 주소 — 자기 글로 가는 내부 링크를 뺀다.
        fact_cfg: 사실 관문 설정(None 이면 끔). strict_title 과 함께 켠다(renewal_fact).
        """
        settings = module.settings or {}
        ai_config = blog.ai_config or {}
        warnings: list = []

        title_note, body_notes = "", []
        if strict_title:
            from . import renewal_title
            working_title, body_notes, title_note = await renewal_title.resolve(
                self.gen, blog, module, live_title, plan.recombine_title, main_title)
            if title_note.startswith(renewal_title.DUP_NOTE):
                # 같은 사이트에 비슷한 글 — 고쳐 쓰지 말고 합치기 후보로(301 은 형 확인 뒤)
                return RenewalContent(success=False, merge=True, title=live_title,
                                      title_note=title_note, error="합치기 후보 — " + title_note)
        else:
            working_title = await self._resolve_title(
                blog, module, live_title, plan, settings, ai_config,
            )

        ref_result = await self._collect_references(
            working_title, module, settings, ai_config,
        )
        if ref_result.count == 0:
            if settings.get("reference", {}).get("required", False):
                return RenewalContent(
                    success=False,
                    error="참조자료 수집 실패 (required=True)",
                )
            warnings.append("참조자료 없이 생성됨")
        from ..generation.health_hold import REASON, needs_hold
        if needs_hold(ref_result):  # 새 글과 같은 건강 글 보류(공식 출처 0건)
            return RenewalContent(success=False, error=f"근거 부족으로 보류: {REASON}")

        category_name = await self._category_name(subtopic_id, topic_id)

        override, extra, existing_for_prompt = self._renewal_prompt(
            settings, existing_content, plan,
        )
        if gap_instruction:
            # 갭은 **마지막에** 붙인다. 앞에 두면 모듈의 기본 지시를 밀어낸다.
            extra = f"{extra}\n\n{gap_instruction}" if extra else gap_instruction
        content_result = await generate_content_with_meta(
            ai_service=self.gen.ai_service,
            title=working_title,
            reference_injection=ref_result.to_prompt_injection(),
            settings=lead_keyword_flow.with_body(settings, body_notes),
            blog=blog,
            category_name=category_name,
            keywords_text="",
            prompt_override=override,
            extra_instruction=extra,
            existing_content=existing_for_prompt,
        )
        body = content_result["content"]
        if fact_cfg is not None:
            body = await self._fact_gate(
                body, working_title, ref_result, fact_cfg, warnings,
                dict(ai_service=self.gen.ai_service, title=working_title,
                     reference_injection=ref_result.to_prompt_injection(),
                     settings=lead_keyword_flow.with_body(settings, body_notes),
                     blog=blog, category_name=category_name, keywords_text="",
                     prompt_override=override, extra_instruction=extra,
                     existing_content=existing_for_prompt))
            if body is None:
                return RenewalContent(success=False, title=working_title, warnings=warnings,
                                      error="사실 관문 통과 못 함 — " + warnings[-1])
        content_with_links = await self.gen.internal_linker.insert_links(
            content=body,
            blog_id=blog.id,
            current_title=working_title,
            module_settings=settings,
            category=(topic_id, subtopic_id),
        )
        from .renewal_record import strip_self_links
        final_html = await self.gen.substitution_processor.process(
            content=strip_self_links(content_with_links, self_url),
            blog_id=blog.id,
            text_replace_enabled=text_replace_enabled,
        )

        final_html, image_url = await self._apply_image(
            blog, working_title, settings, final_html, plan,
        )

        seo_meta = self._build_seo(blog, working_title, final_html)

        return RenewalContent(
            success=True,
            title=working_title,
            content_html=final_html,
            image_url=image_url,
            seo_meta=seo_meta,
            warnings=warnings,
            title_note=title_note,
        )

    async def _fact_gate(self, body: str, title: str, ref_result, cfg: dict,
                         warnings: list, gen_kwargs: dict) -> Optional[str]:
        """사실 관문. 전제가 틀렸으면 바로잡는 지시로 한 번 다시 쓴다. 보류면 None."""
        from . import renewal_fact as rf

        refs = ref_result.to_prompt_injection()
        out = await rf.run(self.gen.ai_service, body, refs, title, cfg)
        if out.premise:
            warnings.append(f"전제 바로잡음: {out.premise[:80]}")
            extra = gen_kwargs.get("extra_instruction") or ""
            gen_kwargs["extra_instruction"] = f"{extra}\n\n{rf.premise_instruction(out.premise)}".strip()
            # 바로잡기는 검사 모델로 쓴다 — gpt-4o-mini 는 지시를 받고도 옛 전제를 섞었다(10/25 /1773)
            gen_kwargs["blog"] = _WriterBlog(gen_kwargs["blog"], rf._model(cfg))
            st = dict(gen_kwargs["settings"])
            st["content_generation"] = {**(st.get("content_generation") or {}), "max_tokens": 8000}
            gen_kwargs["settings"] = st
            try:
                again = await generate_content_with_meta(**gen_kwargs)
            except Exception as e:  # noqa: BLE001 — 바로잡기 실패면 갱신하지 않는다
                warnings.append(f"사실 관문 보류: 전제 바로잡기 다시 쓰기 실패({e})")
                return None
            out = await rf.run(self.gen.ai_service, again["content"], refs, title, cfg,
                               allow_premise=False)
        warnings += out.notes
        if out.hold:
            warnings.append(f"사실 관문 보류: {out.hold}")
            return None
        return out.html

    @staticmethod
    def _strip_html(html: str) -> str:
        """HTML 태그 제거 + 공백 정리 + 상한 절단(프롬프트 주입용)."""
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:EXISTING_CONTENT_MAX_CHARS]

    @classmethod
    def _renewal_prompt(cls, settings: dict, existing_content: str,
                        plan=None):
        """모듈 settings의 리뉴얼 프롬프트 모드 해석.

        content_generation.renewal_prompt = {mode, text}:
        - inherit(기본): 생성 프롬프트 그대로(기존 글 미주입, 현재 동작).
        - new: text를 프롬프트로 교체(+기존 글은 {existing_content}로 제공).
        - additional: text를 추가 지침으로 결합 + 기존 글 본문을 보존·확장하도록 주입.

        **성과 판정이 모드를 덮어쓴다.** 모듈 설정은 블로그 전체에 걸리는
        기본값이고, 유입은 글마다 다르다. 잘 되던 글을 살려 확장할지 없는
        글을 새로 쓸지는 그 글의 성적이 정해야 한다.

        Returns:
            (prompt_override, extra_instruction, existing_for_prompt)
        """
        cg = settings.get("content_generation", {}) if isinstance(settings, dict) else {}
        rp = (cg.get("renewal_prompt") or {}) if isinstance(cg, dict) else {}
        mode = (rp.get("mode") or "inherit").strip()
        text = (rp.get("text") or "").strip()

        forced = getattr(plan, "content_mode", "") if plan else ""
        if forced:
            mode = forced
            # 모듈에 문구가 없으면 기본 문구를 준다 — 없으면 아래 분기가
            # 통째로 inherit 으로 떨어져 성과 판정이 무시된다.
            if not text:
                text = (_AUGMENT_TEXT if forced == "additional"
                        else _REWRITE_TEXT)
        existing_text = cls._strip_html(existing_content)

        if mode == "new" and text:
            return text, "", existing_text
        if mode == "additional" and text:
            extra = text
            if existing_text:
                extra = (
                    f"{text}\n\n[기존 글 본문 — 아래 내용을 보존·반영하고 "
                    f"최신 정보를 추가해 확장하라]\n{existing_text}"
                )
            return "", extra, existing_text
        return "", "", ""  # inherit: 현재 동작 유지

    async def _resolve_title(
        self, blog, module, live_title, plan, settings, ai_config,
    ) -> str:
        """제목 결정: 유지면 그대로, 재조합이면 title_recombiner."""
        if not plan.recombine_title:
            return live_title
        title_ai = ai_config.get("title_ai", {})
        tr = settings.get("title_recombine", {})
        styles = tr.get("styles", [])
        style = random.choice(styles) if styles else None
        rec = await self.gen.title_recombiner.recombine(
            original_title=live_title,
            module_id=module.id,
            provider=title_ai.get("provider"),
            model=title_ai.get("model"),
            style=style,
        )
        return rec.recombined_title or live_title

    async def _collect_references(
        self, working_title, module, settings, ai_config,
    ):
        """참조자료 수집 (blog.reference_ai 우선)."""
        ref_ai = ai_config.get("reference_ai", {})
        if ref_ai.get("provider"):
            ref_settings = settings.get("reference", {}).copy()
            ref_settings["ai_provider"] = ref_ai["provider"]
            if ref_ai.get("model"):
                ref_settings["ai_model"] = ref_ai["model"]
            return await self.gen.reference_collector.collect_and_summarize(
                search_query=working_title, ref_settings=ref_settings,
            )
        return await self.gen.reference_collector.collect_and_summarize(
            search_query=working_title, module_id=module.id,
        )

    async def _category_name(self, subtopic_id, topic_id) -> str:
        """카테고리 표시명(프롬프트 플레이스홀더용). 없으면 빈 문자열."""
        from ...models.category import SubTopic, Topic

        if subtopic_id:
            sub = await self.db.get(SubTopic, subtopic_id)
            if sub:
                top = await self.db.get(Topic, sub.topic_id)
                return f"{top.name} > {sub.name}" if top else sub.name
        if topic_id:
            top = await self.db.get(Topic, topic_id)
            if top:
                return top.name
        return ""

    async def _apply_image(
        self, blog, working_title, settings, final_html, plan,
    ):
        """이미지 적용: reuse면 기존 URL 주입, new면 생성. (final_html, url).

        새 글 발행은 대표 이미지를 **발행 단계**(publisher)가 본문에 넣는다. 리뉴얼은 그
        단계를 거치지 않아 생성만 하고 본문에 안 들어갔다(10/25 미리보기 6편 모두 그림 0개).
        그래서 여기서 직접 넣는다 — 갱신 때 로컬 그림은 updater 가 올리고 주소를 바꾼다.
        """
        if plan.image_action == "reuse" and plan.reuse_image_url:
            return inject_featured(blog, final_html, plan.reuse_image_url,
                                   working_title), plan.reuse_image_url

        img = await self.gen._generate_image_with_retry(
            blog=blog, working_title=working_title,
            settings=settings, final_html=final_html, keywords_text="",
        )
        if img and img.success and img.image_url:
            html = img.final_html or final_html
            if img.image_url not in html:
                html = inject_featured(blog, html, img.image_url, working_title)
            return html, img.image_url
        return final_html, None

    @staticmethod
    def _build_seo(blog, working_title, final_html) -> Optional[dict]:
        """SEO 메타(규칙 기반). 실패 시 None."""
        try:
            from ..publishing.seo_meta_builder import SEOMetaBuilder

            return SEOMetaBuilder().build(
                blog=blog, title=working_title, content_html=final_html,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RENEWAL_GEN] SEO 메타 실패(무시): %s", exc)
            return None
