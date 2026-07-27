"""유사도 그룹핑 — 회색지대 AI 판정 믹스인.

TitleTransferService에서 분리(파일 크기 규칙). 아래 속성이 self에 있어야 함:
- self.db, self.user_id, self.threshold, self.similarity_service
- self._sim_cfg(dict), self._ai_cache(dict)
"""
from typing import Any, Dict, Optional

from ..core.logger import get_logger

logger = get_logger("title_transfer", "title_transfer.log")


class SimilarityGroupingMixin:
    """밴드(상/하한) + 회색지대 AI 판정 로직."""

    async def _load_similarity_config(self) -> Dict[str, Any]:
        """유사도 회색지대/AI 설정 로드(SystemSettings)."""
        from .system_settings_service import SystemSettingsService

        db = self.db
        return {
            # 회색지대 하한. 상한은 임계값(self.threshold)이 담당한다.
            "gray_lower": await SystemSettingsService.get_float(
                "similarity_gray_lower", db, 68.0
            ),
            "ai_enabled": await SystemSettingsService.get_bool(
                "similarity_ai_enabled", db, False
            ),
            "ai_provider": (await SystemSettingsService.get(
                "similarity_ai_provider", db, "") or ""),
            "ai_model": (await SystemSettingsService.get(
                "similarity_ai_model", db, "") or ""),
        }

    def _title_tokens(self, text: str) -> frozenset:
        """제목의 의미 토큰(불용어 제거) — 키워드 블로킹용. 인스턴스 캐시."""
        if not hasattr(self, "_token_cache") or self._token_cache is None:
            self._token_cache = {}
        cached = self._token_cache.get(text)
        if cached is not None:
            return cached
        norm = self.similarity_service.normalize_text(text, remove_stopwords=True)
        toks = frozenset(t for t in norm.split() if len(t) > 1)
        self._token_cache[text] = toks
        return toks

    def _score_best_group(
        self, title, groups_with_reps,
    ) -> Optional[tuple]:
        """키워드 공유 + 카테고리 호환 후보 중 최고 유사도(임계값 무관).

        후보는 그룹 대표뿐 아니라 그룹 없는 제목(group=None)도 포함한다.
        키워드 블로킹: 토큰이 하나도 안 겹치면 유사도 계산을 생략(속도).
        카테고리: 양쪽 다 값이 있고 다를 때만 제외(한쪽 NULL이면 허용).

        Returns: (group_or_None, rep_title, score) 또는 None
        """
        title_tokens = self._title_tokens(title.title)
        best = None
        best_score = -1.0
        for group, rep_title in groups_with_reps:
            if rep_title is title:
                continue
            cand_cat = group.category_id if group is not None else rep_title.category_id
            if title.category_id and cand_cat and cand_cat != title.category_id:
                continue
            rep_tokens = self._title_tokens(rep_title.title)
            if title_tokens and rep_tokens and not (title_tokens & rep_tokens):
                continue
            score = self.similarity_service.calculate_similarity_v3(
                title.title, rep_title.title
            )["score"]
            if score > best_score:
                best_score = score
                best = (group, rep_title, score)
        return best

    async def _should_group(
        self, new_title: str, rep_title: str, score: float,
    ) -> bool:
        """밴드 판정(임계값=상한):
        임계값↑ 그룹 / 하한↓ 분리 / 하한~임계값(회색지대) AI(활성 시).

        AI 비활성 시 기존 동작(임계값 컷) 유지.
        """
        cfg = self._sim_cfg
        if cfg.get("ai_enabled") and cfg.get("ai_provider"):
            if score >= self.threshold:
                return True
            if score <= cfg["gray_lower"]:
                return False
            verdict = await self._ai_same_topic(new_title, rep_title, cfg)
            logger.info(
                "[TRANSFER] 회색지대 AI판정 | score=%.1f (하한%s~임계값%s) | "
                "'%s' ↔ '%s' → %s",
                score, cfg["gray_lower"], self.threshold,
                new_title[:20], rep_title[:20],
                "그룹" if verdict else "분리",
            )
            return verdict
        return score >= self.threshold

    async def _ai_same_topic(
        self, a: str, b: str, cfg: Dict[str, Any],
    ) -> bool:
        """회색지대 두 제목이 같은 주제인지 저렴 AI로 판정(캐시)."""
        key = tuple(sorted((a.strip(), b.strip())))
        if key in self._ai_cache:
            return self._ai_cache[key]
        verdict = False
        try:
            from .ai.ai_service import AIService
            prompt = (
                "두 블로그 글 제목이 사실상 같은 주제·내용을 다루면 '예', "
                "다르면 '아니오'로만 답하세요.\n"
                f"제목1: {a}\n제목2: {b}\n답:"
            )
            ai = AIService(self.db, self.user_id)
            res = await ai.generate(
                prompt=prompt,
                provider=cfg["ai_provider"],
                model=(cfg["ai_model"] or None),
                max_tokens=8,
                temperature=0.0,
            )
            text = ((res or {}).get("content") or "").strip().lower()
            verdict = text.startswith(("예", "네", "yes", "y", "true", "1"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[TRANSFER] 회색지대 AI 판정 실패(분리 처리): {e}")
            verdict = False
        self._ai_cache[key] = verdict
        return verdict
