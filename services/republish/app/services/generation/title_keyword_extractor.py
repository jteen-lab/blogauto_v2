"""
제목 키워드 자동 추출 (KoNLPy 기반)

재조합된 working_title 에서 핵심 명사를 뽑아 `{keywords}` 플레이스홀더
치환에 사용. MainTitle.keywords 가 비어있는 transfer 경로 케이스를 메운다.

설계 의도:
- 제목이 짧으므로(보통 30~80자) 빈도 정렬보다 등장 순서가 더 의미있다.
- JVM 초기화 실패·KoNLPy 미설치 등 어떤 사유로 실패해도 글 생성을 막지
  않는다. 호출자가 빈 문자열을 받아 평소대로 진행한다.
- Okt 인스턴스는 프로세스당 1회 lazy 초기화(JVM 시작 비용 절감).
"""
from __future__ import annotations

import logging
import re
import threading
from typing import List, Optional

# 불용어 사전 재사용. keyword_extractor_service 가 KoNLPy/Java 등 무거운
# import 를 모듈 로드 시점에 트리거하지 않도록 lazy import.
KOREAN_STOPWORDS: set = set()

def _ensure_stopwords() -> set:
    global KOREAN_STOPWORDS
    if KOREAN_STOPWORDS:
        return KOREAN_STOPWORDS
    try:
        from ..keyword_extractor_service import KOREAN_STOPWORDS as KW
        KOREAN_STOPWORDS = KW
    except Exception:
        # 최소 안전망: import 실패 시 빈 set 으로도 동작
        KOREAN_STOPWORDS = set()
    return KOREAN_STOPWORDS

logger = logging.getLogger(__name__)

# 기본 추출 개수 (모듈 설정 미지정 시)
DEFAULT_TOP_N: int = 5

# 의미 없는 1자 명사 제거 기준
MIN_KEYWORD_LENGTH: int = 2

# 영문/숫자 토큰 보존용 정규식 (KoNLPy 가 영문/숫자를 누락하는 경우 보완)
ALNUM_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")

# Okt 인스턴스 lazy 초기화 (스레드 안전)
_okt_instance = None
_okt_lock = threading.Lock()
_okt_init_failed: bool = False  # JVM 부재 등으로 영구 실패한 경우 재시도 안 함


def _get_okt():
    """Okt 인스턴스를 lazy 초기화하여 반환.

    JVM 미설치 등으로 한 번 실패하면 이후 호출은 즉시 None 을 반환해
    매 호출마다 비싼 ImportError/JVMNotFoundException 을 반복하지 않는다.
    """
    global _okt_instance, _okt_init_failed
    if _okt_instance is not None:
        return _okt_instance
    if _okt_init_failed:
        return None
    with _okt_lock:
        if _okt_instance is not None:
            return _okt_instance
        if _okt_init_failed:
            return None
        try:
            from konlpy.tag import Okt
            _okt_instance = Okt()
            logger.info("[TITLE_KW] Okt 형태소 분석기 초기화 완료")
            return _okt_instance
        except Exception as e:
            _okt_init_failed = True
            logger.warning(
                "[TITLE_KW] KoNLPy Okt 초기화 실패 — 키워드 자동 추출 비활성. "
                "원인: %s",
                e,
            )
            return None


def extract_keywords(title: str, top_n: int = DEFAULT_TOP_N) -> List[str]:
    """제목에서 핵심 키워드를 추출.

    Args:
        title: 대상 제목(보통 재조합된 working_title).
        top_n: 최대 반환 개수. 1 이상.

    Returns:
        등장 순서를 보존한 키워드 리스트(중복 제거, 불용어 제거 후).
        추출 실패 또는 결과가 0개면 빈 리스트.
    """
    if not title or not title.strip():
        return []
    if top_n < 1:
        return []

    okt = _get_okt()
    nouns: List[str] = []
    if okt is not None:
        try:
            nouns = okt.nouns(title)
        except Exception as e:
            logger.warning("[TITLE_KW] nouns() 호출 실패: %s | title=%r", e, title[:30])
            nouns = []

    # 영문/숫자 토큰은 KoNLPy 가 누락하기 쉬워 정규식으로 보완
    alnum_tokens = ALNUM_TOKEN_RE.findall(title)

    # 등장 순서 보존 + 중복 제거 + 불용어/짧은 토큰 제거
    stopwords = _ensure_stopwords()
    seen: set = set()
    result: List[str] = []
    for token in [*nouns, *alnum_tokens]:
        word = token.strip()
        if len(word) < MIN_KEYWORD_LENGTH:
            continue
        if word in stopwords:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(word)
        if len(result) >= top_n:
            break

    return result


def extract_keywords_text(title: str, top_n: int = DEFAULT_TOP_N) -> str:
    """추출 결과를 프롬프트 치환용 콤마 구분 문자열로 반환.

    Returns:
        "광안리, 맛집, 추천" 형태. 결과 없으면 빈 문자열.
    """
    keywords = extract_keywords(title, top_n=top_n)
    return ", ".join(keywords)


def resolve_top_n(settings: Optional[dict]) -> int:
    """모듈 설정에서 키워드 추출 개수를 결정.

    우선순위: content_generation.keyword_extract_count -> DEFAULT_TOP_N.
    잘못된 값(음수, 비정수)은 기본값으로 폴백.
    """
    if not settings:
        return DEFAULT_TOP_N
    cg = settings.get("content_generation") or {}
    raw = cg.get("keyword_extract_count")
    try:
        n = int(raw)
        return n if n >= 1 else DEFAULT_TOP_N
    except (TypeError, ValueError):
        return DEFAULT_TOP_N
