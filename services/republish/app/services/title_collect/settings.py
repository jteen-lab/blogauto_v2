"""제목 수집 모듈 설정.

수집은 두 기능으로 나뉜다. 하는 일이 다르고, 각자 켜고 끌 수 있다.

    ① 제목 수집  — 채택 키워드로 검색해 **제목을 얻고**, 그 제목이 있던
                   도메인을 니치도메인에 등록한다. 도메인에서 URL 을
                   캐지는 않는다.
    ② 도메인 추출 — 등록된 도메인의 **사이트맵을 읽어** URL 을 뽑고,
                   각 URL 에서 제목을 가져온다.

**상한을 두지 않는다.** 옛 설계에서 도메인당 URL 수·회차당 새 도메인·
미완료 도메인 상한을 걸었더니, 도메인 287개가 전부 미처리인 초기 상태에서
①이 영구히 건너뛰어지는 교착이 생겼다. 수집은 수집만 한다.

계획서: docs/plans/title_tab_workplan.md §2
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# ① 제목 수집
DEFAULT_SEED_LIMIT = 10          # 한 회차에 검색할 채택 키워드 수
DEFAULT_TITLES_PER_KEYWORD = 30  # 키워드 하나에서 가져올 제목 수

# ② 도메인 추출 — 한 회차의 **전체** 예산이다(도메인당이 아니다).
# 한 도메인에서 다 못 채우면 다음 도메인으로 넘어가 이어서 채운다.
DEFAULT_EXTRACT_URLS = 100

# 재고가 이보다 적은 니치를 '부족' 으로 본다. 화면과 같은 기준이다.
DEFAULT_LOW_NICHE = 20

# 니치 대조 모드. 초기에는 '표시' 가 안전하다 — 분류표가 얇은 상태에서
# 차단부터 켜면 살릴 수 있는 제목까지 막힌다.
NICHE_MARK = "mark"
NICHE_BLOCK = "block"
NICHE_MODES = (NICHE_MARK, NICHE_BLOCK)


def _int(source: dict, key: str, default: int, low: int = 1,
         high: int = 10_000) -> int:
    """범위를 벗어난 값은 기본값으로. 0을 넣어 회차가 멈추는 것을 막는다."""
    try:
        value = source.get(key)
        if value in (None, ""):
            return default
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _ids(value: Any) -> tuple:
    """정수 id 목록만 남긴다. 화면이 문자열을 보내도 받는다."""
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


@dataclass
class TitleCollectSettings:
    """수집 섹션 설정."""

    enabled: bool = True

    # ① 제목 수집 — 설정은 둘뿐이다
    search_enabled: bool = True
    seed_limit: int = DEFAULT_SEED_LIMIT
    titles_per_keyword: int = DEFAULT_TITLES_PER_KEYWORD

    # ② 도메인 추출 — 1회 추출 URL 수(전체 예산)
    extract_enabled: bool = True
    extract_urls: int = DEFAULT_EXTRACT_URLS

    # 재고가 부족한 니치의 키워드를 먼저 쓴다. 어디를 채울지 화면이
    # 보여 주는 것과 같은 기준이다(niche_demand).
    prioritize_low_niche: bool = True
    low_niche_threshold: int = DEFAULT_LOW_NICHE

    # 저장 시점 니치 대조
    niche_mode: str = NICHE_MARK

    # 이 니치만 채운다(요약탭에서 카드 하나를 눌러 돌릴 때).
    # 비면 전체 — 모듈·오토런은 늘 비어 있다.
    subtopic_ids: tuple = ()

    @classmethod
    def parse(cls, settings: Optional[dict]) -> "TitleCollectSettings":
        raw = settings or {}
        source = raw.get("collect") if isinstance(raw.get("collect"), dict) \
            else raw
        mode = str(source.get("niche_mode") or NICHE_MARK).strip()
        return cls(
            enabled=bool(source.get("enabled", True)),
            search_enabled=bool(source.get("search_enabled", True)),
            seed_limit=_int(source, "seed_limit", DEFAULT_SEED_LIMIT, 1, 100),
            titles_per_keyword=_int(source, "titles_per_keyword",
                                    DEFAULT_TITLES_PER_KEYWORD, 1, 100),
            extract_enabled=bool(source.get("extract_enabled", True)),
            extract_urls=_int(source, "extract_urls",
                              DEFAULT_EXTRACT_URLS, 1, 5000),
            prioritize_low_niche=bool(
                source.get("prioritize_low_niche", True)),
            low_niche_threshold=_int(source, "low_niche_threshold",
                                     DEFAULT_LOW_NICHE, 1, 1000),
            niche_mode=mode if mode in NICHE_MODES else NICHE_MARK,
            subtopic_ids=_ids(source.get("subtopic_ids")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "search_enabled": self.search_enabled,
            "seed_limit": self.seed_limit,
            "titles_per_keyword": self.titles_per_keyword,
            "extract_enabled": self.extract_enabled,
            "extract_urls": self.extract_urls,
            "prioritize_low_niche": self.prioritize_low_niche,
            "low_niche_threshold": self.low_niche_threshold,
            "niche_mode": self.niche_mode,
            "subtopic_ids": list(self.subtopic_ids),
        }
