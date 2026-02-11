"""
비-AI 텍스트 요약 알고리즘

AI API 비용 없이 텍스트를 요약하는 알고리즘 3종을 제공합니다.
한국어에 최적화되어 있으며, KoNLPy 미설치 시 정규식 기반 폴백을 지원합니다.

알고리즘:
- TextRank: 문장 간 유사도 그래프 기반 핵심 문장 추출
- Frequency: 키워드 빈도 기반 문장 점수 계산
- Position: 도입부 + 결론부 문장 추출

Features:
- KoNLPy(Okt) 한국어 형태소 분석 지원
- KoNLPy 미설치 시 정규식 기반 폴백
- 문장 분리, 명사 추출, 유사도 계산 내장
"""
import re
import math
import logging
from typing import List, Dict, Set
from collections import Counter

logger = logging.getLogger(__name__)

# KoNLPy 사용 가능 여부
try:
    from konlpy.tag import Okt
    _okt = None
    HAS_KONLPY = True
except ImportError:
    HAS_KONLPY = False
    logger.info("[TEXT_SUMMARIZER] KoNLPy 미설치, 정규식 기반 폴백 사용")


def _get_okt():
    """Okt 인스턴스 싱글턴 반환 (초기화 비용 절감)"""
    global _okt
    if HAS_KONLPY and _okt is None:
        _okt = Okt()
    return _okt


class TextSummarizer:
    """
    비-AI 텍스트 요약기

    Args:
        max_summary_length: 요약 최대 길이 (기본 500자)
    """

    def __init__(self, max_summary_length: int = 500):
        self.max_length = max_summary_length

    def summarize(
        self,
        text: str,
        method: str = "textrank",
        max_length: int = 0
    ) -> str:
        """
        텍스트 요약 실행

        Args:
            text: 원본 텍스트
            method: 요약 알고리즘 (textrank/frequency/position)
            max_length: 최대 길이 (0이면 self.max_length 사용)

        Returns:
            요약된 텍스트
        """
        if not text or len(text.strip()) < 50:
            return text.strip()

        limit = max_length if max_length > 0 else self.max_length

        methods = {
            "textrank": self._textrank_summarize,
            "frequency": self._frequency_summarize,
            "position": self._position_summarize,
        }
        func = methods.get(method, self._textrank_summarize)

        try:
            result = func(text, limit)
            return result[:limit] if len(result) > limit else result
        except Exception as e:
            logger.warning(f"[TEXT_SUMMARIZER] {method} 실패: {e}")
            return self._position_summarize(text, limit)

    def _textrank_summarize(self, text: str, max_length: int) -> str:
        """TextRank: 문장 간 유사도 기반 핵심 문장 추출"""
        sentences = self._split_sentences(text)
        if len(sentences) <= 3:
            return " ".join(sentences)[:max_length]

        # 각 문장에서 명사 집합 추출
        noun_sets: List[Set[str]] = [
            set(self._extract_nouns(s)) for s in sentences
        ]

        # 문장 간 자카드 유사도 매트릭스 계산
        n = len(sentences)
        scores = [0.0] * n
        for i in range(n):
            for j in range(n):
                if i == j or not noun_sets[i] or not noun_sets[j]:
                    continue
                intersection = noun_sets[i] & noun_sets[j]
                union = noun_sets[i] | noun_sets[j]
                scores[i] += len(intersection) / len(union) if union else 0

        # 상위 문장 선택 (원본 순서 유지)
        ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
        top_count = max(2, min(n // 3, 5))
        selected = sorted(ranked[:top_count])

        result = " ".join(sentences[i] for i in selected)
        return result[:max_length]

    def _frequency_summarize(self, text: str, max_length: int) -> str:
        """빈도 기반: 키워드 빈도가 높은 문장 선택"""
        sentences = self._split_sentences(text)
        if len(sentences) <= 3:
            return " ".join(sentences)[:max_length]

        # 전체 텍스트에서 키워드 빈도 계산
        all_nouns = self._extract_nouns(text)
        freq = Counter(all_nouns)

        # 문장별 점수: 해당 문장 키워드 빈도 합
        scores: List[float] = []
        for sentence in sentences:
            nouns = self._extract_nouns(sentence)
            score = sum(freq.get(n, 0) for n in nouns)
            # 길이 정규화
            scores.append(score / max(len(nouns), 1))

        # 상위 문장 선택 (원본 순서 유지)
        ranked = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
        top_count = max(2, min(len(sentences) // 3, 5))
        selected = sorted(ranked[:top_count])

        result = " ".join(sentences[i] for i in selected)
        return result[:max_length]

    def _position_summarize(self, text: str, max_length: int) -> str:
        """위치 기반: 도입부 + 결론부 문장 추출"""
        sentences = self._split_sentences(text)
        if len(sentences) <= 4:
            return " ".join(sentences)[:max_length]

        # 앞 2-3문장 + 뒤 1-2문장
        head_count = min(3, len(sentences) // 2)
        tail_count = min(2, len(sentences) - head_count)

        selected = sentences[:head_count]
        if tail_count > 0:
            selected.extend(sentences[-tail_count:])

        result = " ".join(selected)
        return result[:max_length]

    def _split_sentences(self, text: str) -> List[str]:
        """
        한국어 문장 분리

        마침표/느낌표/물음표 + 공백 또는 줄바꿈 기준으로 분리합니다.
        """
        # 줄바꿈을 문장 구분자로 처리
        text = re.sub(r'\n+', '. ', text)
        # 문장 분리
        raw = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in raw if len(s.strip()) > 10]
        return sentences if sentences else [text.strip()]

    def _extract_nouns(self, text: str) -> List[str]:
        """
        한국어 명사 추출

        KoNLPy 사용 가능 시 Okt 형태소 분석기 사용,
        미설치 시 정규식 기반 2자 이상 한글 단어 추출.
        """
        if HAS_KONLPY:
            okt = _get_okt()
            if okt:
                try:
                    nouns = okt.nouns(text)
                    return [n for n in nouns if len(n) >= 2]
                except Exception:
                    pass

        # 폴백: 정규식으로 2자 이상 한글 단어 추출
        words = re.findall(r'[가-힣]{2,}', text)
        # 불용어 제거
        stopwords = {
            '그리고', '하지만', '그래서', '그러나', '때문에',
            '이것은', '그것은', '그것이', '이것이', '하는',
            '있는', '없는', '되는', '하고', '이런', '그런',
        }
        return [w for w in words if w not in stopwords]
