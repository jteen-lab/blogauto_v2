"""
구글 트렌드 서비스

Features:
- 키워드 트렌드 조회
- 연관 검색어 수집
- 지역별 관심도 분석

Note:
- pytrends는 비공식 API로 Rate Limiting 주의
- 60초 간격 요청 권장
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TrendKeyword:
    """트렌드 키워드 데이터"""
    keyword: str
    trend_score: int  # 0-100 정규화된 관심도
    is_rising: bool = False  # 급상승 여부
    rising_percent: Optional[int] = None  # 급상승 퍼센트


class GoogleTrendsService:
    """구글 트렌드 서비스"""

    def __init__(self, language: str = "ko", timezone: int = 540):
        """
        Args:
            language: 언어 코드 (기본: ko)
            timezone: 타임존 오프셋 (기본: 540 = KST)
        """
        self._language = language
        self._timezone = timezone
        self._pytrends = None

    def _get_pytrends(self):
        """pytrends 인스턴스 생성 (지연 로딩)"""
        if self._pytrends is None:
            try:
                from pytrends.request import TrendReq
                # urllib3 2.x 호환성 문제로 retries 설정 제거
                self._pytrends = TrendReq(
                    hl=self._language,
                    tz=self._timezone,
                    timeout=(10, 25)
                )
            except ImportError:
                logger.error("[GOOGLE_TRENDS] pytrends 라이브러리가 설치되지 않았습니다")
                raise ImportError("pytrends 라이브러리를 설치해주세요: pip install pytrends")
            except Exception as e:
                logger.error(f"[GOOGLE_TRENDS] TrendReq 초기화 오류: {e}")
                raise
        return self._pytrends

    async def get_related_queries(
        self,
        keywords: List[str],
        timeframe: str = "today 3-m",
        geo: str = "KR"
    ) -> Dict[str, Any]:
        """
        연관 검색어 조회

        Args:
            keywords: 검색 키워드 목록 (최대 5개)
            timeframe: 기간 (today 3-m, today 12-m, today 5-y 등)
            geo: 지역 코드 (KR, US 등)

        Returns:
            연관 검색어 및 급상승 검색어
        """
        try:
            # 키워드 개수 제한
            if len(keywords) > 5:
                keywords = keywords[:5]
                logger.warning(f"[GOOGLE_TRENDS] 키워드가 5개로 제한됨: {keywords}")

            # 동기 작업을 비동기로 실행
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._fetch_related_queries,
                keywords,
                timeframe,
                geo
            )

            return result

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] 연관 검색어 조회 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }

    def _fetch_related_queries(
        self,
        keywords: List[str],
        timeframe: str,
        geo: str
    ) -> Dict[str, Any]:
        """연관 검색어 조회 (동기)"""
        try:
            pytrends = self._get_pytrends()
            pytrends.build_payload(
                kw_list=keywords,
                timeframe=timeframe,
                geo=geo
            )

            related = pytrends.related_queries()
            result = {
                "success": True,
                "keywords": [],
                "rising_keywords": []
            }

            for kw in keywords:
                if kw not in related:
                    continue

                kw_data = related[kw]

                # Top 연관 검색어
                if kw_data.get("top") is not None and not kw_data["top"].empty:
                    top_df = kw_data["top"]
                    for _, row in top_df.iterrows():
                        result["keywords"].append({
                            "keyword": row["query"],
                            "trend_score": int(row["value"]),
                            "source_keyword": kw,
                            "type": "related"
                        })

                # Rising 급상승 검색어
                if kw_data.get("rising") is not None and not kw_data["rising"].empty:
                    rising_df = kw_data["rising"]
                    for _, row in rising_df.iterrows():
                        value = row["value"]
                        # "Breakout" 또는 숫자 처리
                        if isinstance(value, str) and value.lower() == "breakout":
                            rising_percent = 5000  # 폭발적 증가
                        else:
                            rising_percent = int(value) if value else 0

                        result["rising_keywords"].append({
                            "keyword": row["query"],
                            "rising_percent": rising_percent,
                            "source_keyword": kw,
                            "type": "rising"
                        })

            logger.info(
                f"[GOOGLE_TRENDS] 연관 검색어 조회 완료: "
                f"related={len(result['keywords'])}, rising={len(result['rising_keywords'])}"
            )

            return result

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] _fetch_related_queries 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "keywords": [],
                "rising_keywords": []
            }

    async def get_trending_searches(
        self,
        country: str = "south_korea"
    ) -> Dict[str, Any]:
        """
        실시간 인기 검색어 조회

        Args:
            country: 국가 코드 (south_korea, united_states 등)

        Returns:
            인기 검색어 목록
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._fetch_trending_searches,
                country
            )
            return result

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] 인기 검색어 조회 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "trending": []
            }

    def _fetch_trending_searches(self, country: str) -> Dict[str, Any]:
        """실시간 인기 검색어 조회 (동기)"""
        trending_list = []

        try:
            pytrends = self._get_pytrends()

            # 방법 1: realtime_trending_searches 시도 (Google News 기반)
            try:
                logger.info("[GOOGLE_TRENDS] realtime_trending_searches 시도 중...")
                # 한국은 KR 코드 사용
                geo_code = "KR" if country == "south_korea" else "US"
                realtime_df = pytrends.realtime_trending_searches(pn=geo_code)

                if realtime_df is not None and not realtime_df.empty:
                    # title 컬럼에서 키워드 추출
                    if 'title' in realtime_df.columns:
                        for title in realtime_df['title'].tolist()[:20]:
                            if title and title not in [t['keyword'] for t in trending_list]:
                                trending_list.append({
                                    "keyword": str(title),
                                    "type": "realtime_trending"
                                })
                    logger.info(f"[GOOGLE_TRENDS] realtime_trending에서 {len(trending_list)}개 수집")
            except Exception as e1:
                logger.warning(f"[GOOGLE_TRENDS] realtime_trending_searches 실패: {e1}")

            # 방법 2: today_searches 시도
            if len(trending_list) < 5:
                try:
                    logger.info("[GOOGLE_TRENDS] today_searches 시도 중...")
                    today_df = pytrends.today_searches(pn=country)

                    if today_df is not None and not today_df.empty:
                        for keyword in today_df.tolist()[:20]:
                            if keyword and keyword not in [t['keyword'] for t in trending_list]:
                                trending_list.append({
                                    "keyword": str(keyword),
                                    "type": "today_trending"
                                })
                        logger.info(f"[GOOGLE_TRENDS] today_searches에서 추가 수집, 총 {len(trending_list)}개")
                except Exception as e2:
                    logger.warning(f"[GOOGLE_TRENDS] today_searches 실패: {e2}")

            # 방법 3: trending_searches 시도 (기존 방법, 실패할 수 있음)
            if len(trending_list) < 5:
                try:
                    logger.info("[GOOGLE_TRENDS] trending_searches 시도 중...")
                    trending_df = pytrends.trending_searches(pn=country)

                    if trending_df is not None and not trending_df.empty:
                        for keyword in trending_df[0].tolist()[:20]:
                            if keyword and keyword not in [t['keyword'] for t in trending_list]:
                                trending_list.append({
                                    "keyword": str(keyword),
                                    "type": "daily_trending"
                                })
                        logger.info(f"[GOOGLE_TRENDS] trending_searches에서 추가 수집, 총 {len(trending_list)}개")
                except Exception as e3:
                    logger.warning(f"[GOOGLE_TRENDS] trending_searches 실패 (예상된 오류): {e3}")

            # 방법 4: 기본 키워드로 연관 검색어 수집 (최후 수단)
            if len(trending_list) < 20:
                logger.info("[GOOGLE_TRENDS] 기본 키워드로 연관 검색어 수집 시도...")
                # 더 다양한 카테고리의 시드 키워드 사용
                default_keywords = [
                    "뉴스", "오늘", "실시간", "인기", "추천",
                    "맛집", "여행", "건강", "뷰티", "쇼핑"
                ]

                for seed in default_keywords:
                    try:
                        pytrends.build_payload(
                            kw_list=[seed],
                            timeframe="now 7-d",  # 7일로 확대
                            geo="KR"
                        )
                        related = pytrends.related_queries()

                        if seed in related and related[seed].get("top") is not None:
                            top_df = related[seed]["top"]
                            if not top_df.empty:
                                # 시드당 10개로 확대
                                for _, row in top_df.head(10).iterrows():
                                    kw = row["query"]
                                    if kw not in [t['keyword'] for t in trending_list]:
                                        trending_list.append({
                                            "keyword": kw,
                                            "type": "related_trending"
                                        })

                        # 급상승 키워드도 수집
                        if seed in related and related[seed].get("rising") is not None:
                            rising_df = related[seed]["rising"]
                            if not rising_df.empty:
                                for _, row in rising_df.head(5).iterrows():
                                    kw = row["query"]
                                    if kw not in [t['keyword'] for t in trending_list]:
                                        trending_list.append({
                                            "keyword": kw,
                                            "type": "rising_trending"
                                        })
                    except Exception:
                        continue

                logger.info(f"[GOOGLE_TRENDS] 연관 검색어로 추가 수집, 총 {len(trending_list)}개")

            logger.info(f"[GOOGLE_TRENDS] 인기 검색어 조회 완료: {len(trending_list)}개")

            return {
                "success": True if trending_list else False,
                "trending": trending_list,
                "error": None if trending_list else "트렌드 키워드를 수집할 수 없습니다"
            }

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] _fetch_trending_searches 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "trending": []
            }

    async def get_interest_over_time(
        self,
        keywords: List[str],
        timeframe: str = "today 3-m",
        geo: str = "KR"
    ) -> Dict[str, Any]:
        """
        시간에 따른 관심도 추이

        Args:
            keywords: 검색 키워드 목록
            timeframe: 기간
            geo: 지역 코드

        Returns:
            시간별 관심도 데이터
        """
        try:
            if len(keywords) > 5:
                keywords = keywords[:5]

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._fetch_interest_over_time,
                keywords,
                timeframe,
                geo
            )
            return result

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] 관심도 추이 조회 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }

    def _fetch_interest_over_time(
        self,
        keywords: List[str],
        timeframe: str,
        geo: str
    ) -> Dict[str, Any]:
        """시간에 따른 관심도 추이 (동기)"""
        try:
            pytrends = self._get_pytrends()
            pytrends.build_payload(
                kw_list=keywords,
                timeframe=timeframe,
                geo=geo
            )

            interest_df = pytrends.interest_over_time()

            if interest_df is None or interest_df.empty:
                return {
                    "success": True,
                    "data": [],
                    "message": "데이터 없음"
                }

            # DataFrame을 딕셔너리로 변환
            data = []
            for idx, row in interest_df.iterrows():
                entry = {"date": idx.strftime("%Y-%m-%d")}
                for kw in keywords:
                    if kw in interest_df.columns:
                        entry[kw] = int(row[kw])
                data.append(entry)

            logger.info(f"[GOOGLE_TRENDS] 관심도 추이 조회 완료: {len(data)}개 데이터포인트")

            return {
                "success": True,
                "data": data
            }

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] _fetch_interest_over_time 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }

    async def collect_keywords(
        self,
        seed_keywords: List[str],
        max_keywords: int = 50
    ) -> Dict[str, Any]:
        """
        시드 키워드로 연관 키워드 수집

        Args:
            seed_keywords: 시드 키워드 목록
            max_keywords: 최대 수집 키워드 수

        Returns:
            수집된 키워드 목록
        """
        all_keywords = []
        seen_keywords = set()

        try:
            # 연관 검색어 수집
            related_result = await self.get_related_queries(
                keywords=seed_keywords,
                timeframe="today 12-m",
                geo="KR"
            )

            if related_result.get("success"):
                # 일반 연관 키워드
                for kw in related_result.get("keywords", []):
                    keyword = kw["keyword"]
                    if keyword not in seen_keywords:
                        all_keywords.append({
                            "keyword": keyword,
                            "trend_score": kw.get("trend_score", 0),
                            "source": "google_trends",
                            "type": "related"
                        })
                        seen_keywords.add(keyword)

                # 급상승 키워드 (높은 우선순위)
                for kw in related_result.get("rising_keywords", []):
                    keyword = kw["keyword"]
                    if keyword not in seen_keywords:
                        all_keywords.append({
                            "keyword": keyword,
                            "trend_score": min(kw.get("rising_percent", 0), 100),
                            "source": "google_trends",
                            "type": "rising",
                            "rising_percent": kw.get("rising_percent", 0)
                        })
                        seen_keywords.add(keyword)

            # 트렌드 점수 기준 정렬
            all_keywords.sort(
                key=lambda x: x.get("trend_score", 0),
                reverse=True
            )

            # 최대 개수 제한
            all_keywords = all_keywords[:max_keywords]

            logger.info(
                f"[GOOGLE_TRENDS] 키워드 수집 완료: "
                f"total={len(all_keywords)}"
            )

            return {
                "success": True,
                "total_count": len(all_keywords),
                "keywords": all_keywords
            }

        except Exception as e:
            logger.error(f"[GOOGLE_TRENDS] 키워드 수집 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "keywords": []
            }

    async def test_connection(self) -> Dict[str, Any]:
        """
        API 연결 테스트

        Returns:
            연결 테스트 결과
        """
        try:
            # 연관 검색어로 테스트 (trending은 404 오류 발생 가능)
            result = await self.get_related_queries(
                keywords=["테스트"],
                timeframe="today 3-m",
                geo="KR"
            )

            if result.get("success"):
                keywords = result.get("keywords", [])
                sample = [{"keyword": k["keyword"]} for k in keywords[:3]]
                return {
                    "success": True,
                    "message": "구글 트렌드 연결 성공",
                    "sample_trending": sample
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "연관 검색어를 가져올 수 없습니다")
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
