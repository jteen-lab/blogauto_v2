"""
키워드 추출 서비스

제목에서 키워드를 추출하는 4가지 방법을 제공합니다:
1. KoNLPy 형태소 분석 (명사 추출)
2. TF-IDF 기반 핵심 키워드
3. N-gram 빈도 분석
4. 불용어 필터링

임시 제목(TempTitle)에서 지정 수량의 제목을 선정하여
키워드를 추출하고 정본(keyword_candidates)에 저장합니다.
"""
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.title import TempTitle
from ..models.keyword_candidate import KeywordCandidate, VERDICT_PENDING
from ..models.content_filter import ContentFilter
from ..core.logger import get_logger
from .category_matcher_service import CategoryMatcherService

logger = get_logger("keyword_extractor", "keyword_extractor.log")


# 한국어 불용어 목록
KOREAN_STOPWORDS: Set[str] = {
    # 조사
    "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "으로",
    "에서", "까지", "부터", "만", "뿐", "밖에", "처럼", "같이", "대로",
    # 대명사
    "나", "너", "우리", "저", "그", "이것", "저것", "그것", "여기", "저기",
    # 부사/접속사
    "그리고", "하지만", "그러나", "또한", "또", "더", "매우", "아주", "너무",
    "정말", "진짜", "완전", "약간", "조금", "많이", "빨리", "천천히",
    # 동사/형용사 어미
    "하다", "되다", "있다", "없다", "이다", "아니다", "같다", "다르다",
    # 일반 불용어
    "것", "수", "등", "위", "및", "중", "내", "후", "전", "간", "때",
    "곳", "바", "점", "측", "편", "명", "원", "개", "년", "월", "일",
    # 뉴스 관련 불용어
    "기자", "뉴스", "보도", "속보", "단독", "종합", "영상", "사진",
    "취재", "인터뷰", "기사", "제보", "특종", "긴급", "속보",
    # 일반적인 표현
    "오늘", "어제", "내일", "지금", "현재", "최근", "다음", "이번",
    "대한", "관련", "통해", "따라", "위해", "때문", "이후", "가능",
}

# 추가 도메인별 불용어
NEWS_STOPWORDS: Set[str] = {
    "연합뉴스", "뉴시스", "이데일리", "머니투데이", "한경",
    "매일경제", "헤럴드경제", "서울경제", "파이낸셜뉴스",
}


class KeywordExtractorService:
    """키워드 추출 서비스"""

    def __init__(self, db: AsyncSession, user_id: int = 1):
        self.db = db
        self.user_id = user_id
        self._konlpy_available = False
        self._tagger = None
        self._filters_cache: Optional[List[ContentFilter]] = None
        self._category_matcher: Optional[CategoryMatcherService] = None
        self._init_konlpy()

    async def _init_category_matcher(self) -> None:
        """카테고리 매처 초기화"""
        if self._category_matcher is None:
            self._category_matcher = CategoryMatcherService(self.db)
            # 키워드 캐시 로드
            keywords = await self._category_matcher._load_keywords()
            logger.info(f"[EXTRACTOR] 카테고리 매처 초기화: {len(keywords)}개 키워드 로드")

    async def _load_filters(self) -> List[ContentFilter]:
        """활성 필터 로드 (캐시 사용)"""
        if self._filters_cache is None:
            query = select(ContentFilter).where(ContentFilter.is_active == True)
            result = await self.db.execute(query)
            self._filters_cache = list(result.scalars().all())
            logger.info(f"[EXTRACTOR] 필터 {len(self._filters_cache)}개 로드")
        return self._filters_cache

    async def _check_filter(self, text: str) -> Optional[ContentFilter]:
        """
        키워드가 필터에 걸리는지 확인

        Args:
            text: 확인할 키워드

        Returns:
            매칭된 필터 객체 (없으면 None)
        """
        filters = await self._load_filters()

        for filter_obj in filters:
            # keyword 또는 both 타입만 체크
            if filter_obj.target_type not in ["keyword", "both"]:
                continue

            filter_value = filter_obj.filter_value.lower()
            text_lower = text.lower()

            matched = False

            if filter_obj.filter_type == "keyword":
                if filter_value in text_lower:
                    matched = True
            elif filter_obj.filter_type == "pattern":
                try:
                    if re.search(filter_value, text_lower):
                        matched = True
                except re.error:
                    continue
            elif filter_obj.filter_type == "domain":
                if filter_value in text_lower:
                    matched = True

            if matched:
                filter_obj.increment_match()
                logger.debug(f"[EXTRACTOR] 필터 매칭: '{text}' → 필터 '{filter_obj.name}'")
                return filter_obj

        return None

    def _init_konlpy(self) -> None:
        """KoNLPy 초기화 (설치되어 있는 경우)"""
        try:
            from konlpy.tag import Okt
            self._tagger = Okt()
            self._konlpy_available = True
            logger.info("[EXTRACTOR] KoNLPy(Okt) 초기화 성공")
        except ImportError:
            logger.warning("[EXTRACTOR] KoNLPy 미설치 - 정규식 기반 추출 사용")
            self._konlpy_available = False
        except Exception as e:
            # JVM 오류 등 다른 예외도 처리
            logger.warning(f"[EXTRACTOR] KoNLPy 초기화 실패: {e} - 정규식 기반 추출 사용")
            self._konlpy_available = False

    def extract_nouns_konlpy(self, text: str) -> List[str]:
        """
        KoNLPy를 사용한 명사 추출

        Args:
            text: 분석할 텍스트

        Returns:
            추출된 명사 리스트
        """
        if not self._konlpy_available or not self._tagger:
            return self._extract_nouns_regex(text)

        try:
            nouns = self._tagger.nouns(text)
            # 2글자 이상 명사만 필터링
            return [n for n in nouns if len(n) >= 2]
        except Exception as e:
            logger.error(f"[EXTRACTOR] KoNLPy 명사 추출 실패: {e}")
            return self._extract_nouns_regex(text)

    def _extract_nouns_regex(self, text: str) -> List[str]:
        """
        정규식 기반 명사 추출 (KoNLPy 미설치 시 대체)

        Args:
            text: 분석할 텍스트

        Returns:
            추출된 단어 리스트
        """
        # 특수문자 제거
        text = re.sub(r'[^\w\s가-힣]', ' ', text)
        # 연속 공백 제거
        text = re.sub(r'\s+', ' ', text).strip()
        # 공백으로 분리
        words = text.split()
        # 2글자 이상 한글 단어만
        return [w for w in words if len(w) >= 2 and re.match(r'^[가-힣]+$', w)]

    def filter_stopwords(self, words: List[str]) -> List[str]:
        """
        불용어 필터링

        Args:
            words: 단어 리스트

        Returns:
            불용어가 제거된 단어 리스트
        """
        all_stopwords = KOREAN_STOPWORDS | NEWS_STOPWORDS
        return [w for w in words if w not in all_stopwords]

    def extract_ngrams(self, words: List[str], n: int = 2) -> List[str]:
        """
        N-gram 추출

        Args:
            words: 단어 리스트
            n: N-gram 크기 (기본 2)

        Returns:
            N-gram 리스트
        """
        if len(words) < n:
            return []
        return [' '.join(words[i:i+n]) for i in range(len(words) - n + 1)]

    def calculate_tfidf(
        self,
        documents: List[str],
        max_keywords: int = 10
    ) -> List[Dict[str, Any]]:
        """
        TF-IDF 기반 핵심 키워드 추출

        Args:
            documents: 문서 리스트 (각 제목)
            max_keywords: 최대 키워드 수

        Returns:
            TF-IDF 점수가 포함된 키워드 리스트
        """
        if not documents:
            return []

        # 문서별 단어 추출
        doc_words = []
        for doc in documents:
            words = self.extract_nouns_konlpy(doc)
            words = self.filter_stopwords(words)
            doc_words.append(words)

        # 전체 문서 수
        n_docs = len(documents)

        # 단어별 DF(Document Frequency) 계산
        df_counter: Counter = Counter()
        for words in doc_words:
            unique_words = set(words)
            df_counter.update(unique_words)

        # 전체 단어 TF 계산
        all_words: List[str] = []
        for words in doc_words:
            all_words.extend(words)
        tf_counter = Counter(all_words)

        # TF-IDF 계산
        tfidf_scores: Dict[str, float] = {}
        for word, tf in tf_counter.items():
            df = df_counter.get(word, 1)
            # IDF = log(N / DF)
            import math
            idf = math.log(n_docs / df) if df > 0 else 0
            tfidf_scores[word] = tf * idf

        # 상위 키워드 추출
        sorted_keywords = sorted(
            tfidf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:max_keywords]

        return [
            {"keyword": kw, "score": round(score, 4)}
            for kw, score in sorted_keywords
        ]

    def extract_keywords_from_titles(
        self,
        titles: List[str],
        method: str = "all",
        max_keywords: int = 50
    ) -> Dict[str, Any]:
        """
        제목 리스트에서 키워드 추출

        Args:
            titles: 제목 리스트
            method: 추출 방법
                - "konlpy": KoNLPy 명사 추출
                - "tfidf": TF-IDF 핵심 키워드
                - "ngram": N-gram 빈도 분석
                - "all": 모든 방법 통합
            max_keywords: 최대 키워드 수

        Returns:
            추출된 키워드 결과
        """
        if not titles:
            return {
                "success": False,
                "error": "제목이 없습니다",
                "keywords": []
            }

        logger.info(
            f"[EXTRACTOR] 키워드 추출 시작: "
            f"{len(titles)}개 제목, method={method}, max={max_keywords}"
        )

        result_keywords: List[Dict[str, Any]] = []

        try:
            if method in ["konlpy", "all"]:
                # KoNLPy 명사 추출
                all_nouns: List[str] = []
                for title in titles:
                    nouns = self.extract_nouns_konlpy(title)
                    nouns = self.filter_stopwords(nouns)
                    all_nouns.extend(nouns)

                noun_counter = Counter(all_nouns)
                top_nouns = noun_counter.most_common(max_keywords)

                for keyword, count in top_nouns:
                    result_keywords.append({
                        "keyword": keyword,
                        "method": "konlpy",
                        "score": count,
                        "frequency": count
                    })

            if method in ["tfidf", "all"]:
                # TF-IDF 핵심 키워드
                tfidf_keywords = self.calculate_tfidf(titles, max_keywords)
                for kw_data in tfidf_keywords:
                    # 중복 체크
                    existing = next(
                        (k for k in result_keywords if k["keyword"] == kw_data["keyword"]),
                        None
                    )
                    if existing:
                        existing["tfidf_score"] = kw_data["score"]
                    else:
                        result_keywords.append({
                            "keyword": kw_data["keyword"],
                            "method": "tfidf",
                            "score": kw_data["score"],
                            "tfidf_score": kw_data["score"]
                        })

            if method in ["ngram", "all"]:
                # N-gram 빈도 분석 (2-gram)
                all_bigrams: List[str] = []
                for title in titles:
                    words = self.extract_nouns_konlpy(title)
                    words = self.filter_stopwords(words)
                    bigrams = self.extract_ngrams(words, n=2)
                    all_bigrams.extend(bigrams)

                bigram_counter = Counter(all_bigrams)
                top_bigrams = bigram_counter.most_common(max_keywords // 2)

                for bigram, count in top_bigrams:
                    if count >= 2:  # 최소 2회 이상 출현
                        result_keywords.append({
                            "keyword": bigram,
                            "method": "ngram",
                            "score": count,
                            "frequency": count
                        })

            # 점수 기준 정렬 및 중복 제거
            seen_keywords: Set[str] = set()
            unique_keywords: List[Dict[str, Any]] = []

            # 점수 기준 정렬
            sorted_keywords = sorted(
                result_keywords,
                key=lambda x: x.get("score", 0),
                reverse=True
            )

            for kw in sorted_keywords:
                keyword = kw["keyword"]
                if keyword not in seen_keywords and len(unique_keywords) < max_keywords:
                    seen_keywords.add(keyword)
                    unique_keywords.append(kw)

            logger.info(
                f"[EXTRACTOR] 키워드 추출 완료: {len(unique_keywords)}개"
            )

            return {
                "success": True,
                "total_titles": len(titles),
                "keywords": unique_keywords,
                "extracted_count": len(unique_keywords)
            }

        except Exception as e:
            logger.error(f"[EXTRACTOR] 키워드 추출 실패: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }

    async def extract_and_save_keywords(
        self,
        title_limit: int = 100,
        keyword_limit: int = 50,
        method: str = "all",
        title_status: str = "new"
    ) -> Dict[str, Any]:
        """
        TempTitle에서 제목을 선정하여 키워드 추출 후 정본에 저장

        Args:
            title_limit: 분석할 제목 수량
            keyword_limit: 추출할 최대 키워드 수
            method: 추출 방법 (konlpy, tfidf, ngram, all)
            title_status: 처리할 제목 상태 (기본: new)

        Returns:
            추출 및 저장 결과
        """
        logger.info(
            f"[EXTRACTOR] 키워드 추출 및 저장 시작: "
            f"title_limit={title_limit}, keyword_limit={keyword_limit}, method={method}"
        )

        try:
            # 1. TempTitle에서 제목 조회
            query = (
                select(TempTitle)
                .where(TempTitle.status == title_status)
                .order_by(TempTitle.created_at.desc())
                .limit(title_limit)
            )
            result = await self.db.execute(query)
            temp_titles = result.scalars().all()

            if not temp_titles:
                return {
                    "success": False,
                    "error": f"상태가 '{title_status}'인 제목이 없습니다",
                    "titles_processed": 0,
                    "keywords_saved": 0
                }

            titles = [t.title for t in temp_titles]
            logger.info(f"[EXTRACTOR] {len(titles)}개 제목 조회 완료")

            # 2. 키워드 추출
            extract_result = self.extract_keywords_from_titles(
                titles=titles,
                method=method,
                max_keywords=keyword_limit
            )

            if not extract_result.get("success"):
                return extract_result

            keywords = extract_result.get("keywords", [])

            # 3. 카테고리 매처 초기화
            await self._init_category_matcher()

            # 4. 정본에 저장 (중복 체크 및 재활성화 포함)
            saved_count = 0
            reactivated_count = 0
            skipped_count = 0
            filtered_count = 0
            category_matched_count = 0

            for kw_data in keywords:
                keyword = kw_data["keyword"]

                # 1. 필터 체크 (가장 먼저!)
                matched_filter = await self._check_filter(keyword)
                if matched_filter:
                    filtered_count += 1
                    logger.debug(
                        f"[EXTRACTOR] 키워드 필터링: '{keyword}' → "
                        f"필터 '{matched_filter.name}'"
                    )
                    continue

                # 2. 중복 체크
                existing_query = (
                    select(KeywordCandidate)
                    .where(KeywordCandidate.user_id == self.user_id,
                           KeywordCandidate.keyword == keyword)
                    .limit(1)
                )
                existing_result = await self.db.execute(existing_query)
                existing = existing_result.scalars().first()

                if existing:
                    # 비활성화된 키워드 재활성화 (use_count >= 4로 비활성화된 경우)
                    if not existing.is_active:
                        existing.is_active = True
                        existing.use_count = 0  # 사용 횟수 리셋
                        existing.last_used_at = datetime.now()
                        reactivated_count += 1
                        logger.info(
                            f"[EXTRACTOR] 비활성화 키워드 재활성화: '{keyword}'"
                        )
                    else:
                        # 이미 활성 상태면 스킵 (중복)
                        skipped_count += 1
                    continue

                # 3. 카테고리 매칭
                topic_id, subtopic_id, matched_keyword_id = None, None, None
                try:
                    if self._category_matcher:
                        topic_id, subtopic_id, matched_keyword_id = \
                            await self._category_matcher.match_and_apply_to_keyword(keyword)
                        if topic_id:
                            category_matched_count += 1
                            logger.debug(
                                f"[EXTRACTOR] 카테고리 매칭: '{keyword}' → "
                                f"topic={topic_id}, subtopic={subtopic_id}"
                            )
                except Exception as cat_err:
                    logger.warning(f"[EXTRACTOR] 카테고리 매칭 오류: {cat_err}")

                # 4. 새 키워드 저장
                # 전역 풀(blog_id NULL)에 넣는다. 니치가 붙으면 그 니치를
                # 가진 블로그가 가져다 쓴다(scope.usable_by).
                new_keyword = KeywordCandidate(
                    user_id=self.user_id,
                    keyword=keyword,
                    blog_id=None,
                    source="extracted",
                    verdict=VERDICT_PENDING,
                    verdict_reason="제목에서 추출 — 아직 재지 않음",
                    is_active=True,
                    use_count=0,
                    priority=int(kw_data.get("score", 0)),
                    topic_id=topic_id,
                    subtopic_id=subtopic_id,
                )
                self.db.add(new_keyword)
                saved_count += 1

            await self.db.commit()

            logger.info(
                f"[EXTRACTOR] 키워드 저장 완료: "
                f"{len(keywords)}개 추출, {saved_count}개 신규 저장, "
                f"{reactivated_count}개 재활성화, {skipped_count}개 중복 스킵, "
                f"{filtered_count}개 필터링, {category_matched_count}개 카테고리 매칭"
            )

            return {
                "success": True,
                "titles_processed": len(titles),
                "keywords_extracted": len(keywords),
                "keywords_saved": saved_count,
                "keywords_reactivated": reactivated_count,
                "keywords_skipped": skipped_count,
                "keywords_filtered": filtered_count,
                "keywords_category_matched": category_matched_count,
                "method": method,
                "keywords": keywords[:20]
            }

        except Exception as e:
            logger.error(f"[EXTRACTOR] 키워드 추출 및 저장 실패: {e}", exc_info=True)
            await self.db.rollback()
            return {
                "success": False,
                "error": str(e),
                "titles_processed": 0,
                "keywords_saved": 0
            }

    async def get_extraction_stats(self) -> Dict[str, Any]:
        """추출 통계 조회"""
        try:
            # 추출된 키워드 수
            extracted_query = (
                select(func.count(KeywordCandidate.id))
                .where(KeywordCandidate.source == "extracted")
            )
            extracted_result = await self.db.execute(extracted_query)
            extracted_count = extracted_result.scalar() or 0

            # 처리 가능한 제목 수
            available_query = (
                select(func.count(TempTitle.id))
                .where(TempTitle.status == "new")
            )
            available_result = await self.db.execute(available_query)
            available_titles = available_result.scalar() or 0

            return {
                "extracted_keywords": extracted_count,
                "available_titles": available_titles,
                "konlpy_available": self._konlpy_available
            }

        except Exception as e:
            logger.error(f"[EXTRACTOR] 통계 조회 실패: {e}")
            return {
                "extracted_keywords": 0,
                "available_titles": 0,
                "konlpy_available": self._konlpy_available
            }
