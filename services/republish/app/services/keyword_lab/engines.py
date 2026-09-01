"""블로그별 타깃 검색 엔진.

지금까지 수요는 네이버로 재고 글은 워드프레스·블로거(주로 구글 색인)로
내보냈다. 서울 손님 취향을 조사해 부산에 가게를 낸 셈이다.

블로그마다 "어디 노출을 노리는가" 를 정하고, 키워드 판정·색인 점검이 그 값을
따르게 한다. 값은 `Blog.seo_config` 에 둔다 — 블로그 테이블은 운영 핵심이라
컬럼 추가를 최소로 한다.

**플랫폼 제약**: 네이버에 자동으로 색인을 알리는 유일한 길은 IndexNow 인데,
키 파일을 호스트 루트에 올려야 한다. 블로거는 그걸 못 한다. 그래서 블로거로
네이버를 노리면 발행해도 알릴 방법이 없다 — 경고로 알려 준다.

계획서: docs/plans/keyword_module_redesign_plan.md §5-3
"""
from __future__ import annotations

from typing import Any, Dict, List

from ...core.logger import get_logger

logger = get_logger("keyword_engines", "app.log")

ENGINE_GOOGLE = "google"
ENGINE_NAVER = "naver"
ENGINE_BING = "bing"

SUPPORTED = (ENGINE_GOOGLE, ENGINE_NAVER, ENGINE_BING)

ENGINE_LABEL = {
    ENGINE_GOOGLE: "구글",
    ENGINE_NAVER: "네이버",
    ENGINE_BING: "빙",
}

# 기본값. 워드프레스·블로거는 구글 색인 대상이다.
DEFAULT_ENGINES = [ENGINE_GOOGLE]

# seo_config 안의 키
CONFIG_KEY = "target_engines"

# 지표를 어느 엔진에서 볼지. 빙은 자체 키워드 지표가 없어 구글을 따른다.
METRIC_ENGINE = {
    ENGINE_GOOGLE: "google",
    ENGINE_NAVER: "naver",
    ENGINE_BING: "google",
}


def target_engines(blog: Any) -> List[str]:
    """이 블로그가 노리는 검색 엔진 목록."""
    config = getattr(blog, "seo_config", None) or {}
    raw = config.get(CONFIG_KEY) if isinstance(config, dict) else None
    picked = [e for e in (raw or []) if e in SUPPORTED]
    return picked or list(DEFAULT_ENGINES)


def set_target_engines(blog: Any, engines: List[str]) -> List[str]:
    """타깃 엔진을 저장한다. 모르는 값은 버리고, 비면 기본값으로 둔다."""
    picked = [e for e in (engines or []) if e in SUPPORTED]
    if not picked:
        picked = list(DEFAULT_ENGINES)
    config = dict(getattr(blog, "seo_config", None) or {})
    config[CONFIG_KEY] = picked
    blog.seo_config = config
    return picked


def metric_engine(blog: Any) -> str:
    """판정에 쓸 지표 엔진.

    여러 엔진을 노리면 첫 번째를 기준으로 삼는다. 우선순위는 사용자가
    목록 순서로 정한다.
    """
    return METRIC_ENGINE.get(target_engines(blog)[0], "naver")


def is_wordpress(blog: Any) -> bool:
    """플랫폼이 워드프레스인지(IndexNow 키 파일을 올릴 수 있는지)."""
    platform = getattr(blog, "platform", None)
    value = getattr(platform, "value", platform)
    return str(value or "").lower() == "wordpress"


def naver_notify_supported(blog: Any) -> bool:
    """네이버에 색인을 자동으로 알릴 수 있는지.

    IndexNow 가 유일한 자동 경로이고, 키 파일을 호스트 루트에 올려야 한다.
    블로거는 불가능하다.
    """
    return is_wordpress(blog)


def warnings(blog: Any) -> List[str]:
    """타깃 엔진과 플랫폼이 어긋날 때 알려 줄 말."""
    out: List[str] = []
    engines = target_engines(blog)

    if ENGINE_NAVER in engines and not naver_notify_supported(blog):
        out.append(
            "블로거는 IndexNow 키 파일을 올릴 수 없어 네이버에 색인을 "
            "자동으로 알릴 수 없습니다. 네이버 타깃은 워드프레스에 배정하세요."
        )
    if ENGINE_NAVER in engines:
        out.append(
            "외부 사이트는 네이버 '블로그 탭'이 아니라 '웹사이트 탭'에 "
            "노출됩니다. 등록 후 노출까지 통상 2주가 걸립니다."
        )
    return out


def describe(blog: Any) -> Dict[str, Any]:
    """화면에 줄 요약."""
    engines = target_engines(blog)
    return {
        "engines": engines,
        "labels": [ENGINE_LABEL[e] for e in engines],
        "metric_engine": metric_engine(blog),
        "naver_notify": naver_notify_supported(blog),
        "warnings": warnings(blog),
    }
