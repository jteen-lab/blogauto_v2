"""코퍼스 토큰 문서빈도(DF) 계산·캐시.

주어(핵심어) 발산 게이트용. MainTitle 전체를 SimilarityService.content_tokens
로 토큰화해 DF/n_docs를 계산하고 인메모리 TTL 캐시한다. shared 계층은 앱 모델
의존이 없으므로, app 계층에서 계산해 SimilarityService에 주입한다.
"""
import os
import sys
import time
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import get_logger
from ..models.title import MainTitle

# shared 모듈 경로(Docker/로컬)
for _p in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
        break

from services.similarity_service import SimilarityService  # noqa: E402

logger = get_logger("token_df", "app.log")


class TokenDFService:
    """MainTitle 코퍼스 토큰 DF 계산 + TTL 캐시(클래스 레벨)."""

    _df: Dict[str, int] = None
    _n: int = 0
    _ts: float = 0.0
    _TTL = 600.0  # 10분

    @classmethod
    async def get(cls, db: AsyncSession, force: bool = False) -> Tuple[Dict[str, int], int]:
        """캐시된 DF/n_docs 반환(만료·강제 시 재계산)."""
        now = time.time()
        if not force and cls._df is not None and (now - cls._ts) < cls._TTL:
            return cls._df, cls._n
        df, n = await cls._compute(db)
        cls._df, cls._n, cls._ts = df, n, now
        logger.info(f"[TOKEN_DF] 갱신: 문서 {n}개, 고유토큰 {len(df)}개")
        return df, n

    @classmethod
    async def _compute(cls, db: AsyncSession) -> Tuple[Dict[str, int], int]:
        """MainTitle 전체로 토큰 DF 계산."""
        svc = SimilarityService()
        df: Dict[str, int] = {}
        n = 0
        rows = (await db.execute(select(MainTitle.title))).scalars().all()
        for title in rows:
            n += 1
            for tok in svc.content_tokens(title or ""):
                df[tok] = df.get(tok, 0) + 1
        return df, n

    @classmethod
    async def inject(cls, svc, db: AsyncSession) -> None:
        """SimilarityService에 코퍼스 DF 주입(실패 시 폴백 유지)."""
        try:
            df, n = await cls.get(db)
            svc.token_df = df
            svc.n_docs = n
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[TOKEN_DF] 주입 실패(폴백 사용): {e}")

    @classmethod
    def invalidate(cls) -> None:
        """캐시 무효화(대량 제목 변경 후 호출)."""
        cls._df = None
        cls._n = 0
        cls._ts = 0.0
