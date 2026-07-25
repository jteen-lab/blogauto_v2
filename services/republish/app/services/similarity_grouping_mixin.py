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
            "gray_lower": await SystemSettingsService.get_float(
                "similarity_gray_lower", db, 68.0
            ),
            "gray_upper": await SystemSettingsService.get_float(
                "similarity_gray_upper", db, 80.0
            ),
            "ai_enabled": await SystemSettingsService.get_bool(
                "similarity_ai_enabled", db, False
            ),
            "ai_provider": (await SystemSettingsService.get(
                "similarity_ai_provider", db, "") or ""),
            "ai_model": (await SystemSettingsService.get(
                "similarity_ai_model", db, "") or ""),
        }

    def _score_best_group(
        self, title, groups_with_reps,
    ) -> Optional[tuple]:
        """카테고리 일치 그룹 중 최고 유사도 후보 반환(임계값 무관).

        Returns: (group, rep_title, score) 또는 None
        """
        best = None
        best_score = -1.0
        for group, rep_title in groups_with_reps:
            if title.category_id and group.category_id != title.category_id:
                continue
            result = self.similarity_service.calculate_similarity_v3(
                title.title, rep_title.title
            )
            score = result["score"]
            if score > best_score:
                best_score = score
                best = (group, rep_title, score)
        return best

    async def _should_group(
        self, new_title: str, rep_title: str, score: float,
    ) -> bool:
        """밴드 판정: 상한↑ 그룹 / 하한↓ 분리 / 회색지대 AI(활성 시).

        AI 비활성 시 기존 동작(임계값 컷) 유지.
        """
        cfg = self._sim_cfg
        if cfg.get("ai_enabled") and cfg.get("ai_provider"):
            if score >= cfg["gray_upper"]:
                return True
            if score <= cfg["gray_lower"]:
                return False
            return await self._ai_same_topic(new_title, rep_title, cfg)
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
