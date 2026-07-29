"""텍스트 정규화·유사도·차별토큰 믹스인 + 관련 상수.

SimilarityService에서 분리(파일 크기 규칙). 지역/캐노니컬 무관한 순수
텍스트 처리와 핵심어 발산 판정을 담당한다.
"""
import re
import html
import unicodedata
from difflib import SequenceMatcher

# rapidfuzz 사용 (설치된 경우)
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


KOREAN_STOPWORDS = [
    # 조사
    '및', '과', '에', '에서', '으로', '와', '은', '는', '이', '가', '을', '를',
    '의', '로', '라', '고', '도', '만', '에게', '께', '한테', '보다',
    # 수식어
    '대한', '관한', '위한', '통한', '따른', '인한', '등', '또는', '그리고',
    # 일반 키워드 (정보성)
    '방법', '원인', '증상', '치료', '효과', '정보', '종류', '가격', '비교', '정리',
    '추천', '순위', '후기', '리뷰', '총정리', '완벽정리', '알아보기', '소개',
    # 브랜드/도메인
    'tistory', 'naver', 'blog', 'daum', 'kakao', 'google',
]

# 도메인 골격어(카테고리 공통어) — '핵심어 발산 가드' 판정에서만 제외한다.
# 점수/보너스 계산에는 사용하지 않으므로 점수를 올리지 않고, 캡 판정만 좌우한다.
GENERIC_KEYWORDS = frozenset([
    # 여행 가이드 골격
    '여행', '여행지', '여행기', '숙소', '호텔', '호스텔', '게스트하우스', '리조트',
    '명소', '관광', '관광지', '관광명소', '가볼만한곳', '볼거리', '즐길거리', '먹거리',
    '날씨', '계절', '계절별', '대중교통', '대중', '교통', '코스', '일정', '지역', '지역별',
    '특징', '준비', '사항', '방문', '기초', '필수', '가이드', '팁',
    '음식', '맛집', '카페', '경비', '예상', '시간표', '예매',
    # 블로그 일반 골격
    '베스트', '리스트', '모음', '가지', '개', '곳',
])

# 조사/접미 경량 제거용(형태소 분석 없이 토큰 끝 처리)
PARTICLE_SUFFIXES = (
    '으로', '에서', '에게', '한테', '과의', '와의', '에는', '에서의',
    '과', '와', '을', '를', '이', '가', '은', '는', '의', '에', '로', '도', '만',
    '별', '들',
)

# 핵심어 발산 시 점수 상한(회색지대 하한 미만으로 눌러 하드 분리)
CORE_DIVERGENCE_CAP = 55.0

# 제거할 패턴
BRACKET_PATTERN = re.compile(r'^[\[\(\{<【「『].*?[\]\)\}>】」』]\s*|\s*[\[\(\{<【「『].*?[\]\)\}>】」』]$')
SEPARATOR_PATTERN = re.compile(r'[\|\-:／/·•]')
MULTI_SPACE_PATTERN = re.compile(r'\s+')


class TextSimilarityMixin:
    """텍스트 정규화·유사도·차별토큰 메서드 모음."""

    def normalize_text(self, text: str, remove_stopwords: bool = False) -> str:
        """
        텍스트 정규화

        Args:
            text: 원본 텍스트
            remove_stopwords: 불용어 제거 여부

        Returns:
            정규화된 텍스트
        """
        if not text:
            return ""

        result = text

        # 1. HTML 엔티티 디코드
        result = html.unescape(result)

        # 2. NFKC 유니코드 정규화 (전각/반각 통일)
        result = unicodedata.normalize('NFKC', result)

        # 3. 제어문자 및 제로폭 문자 제거
        result = re.sub(r'[\u0000-\u001F\u200B-\u200D\uFEFF]', '', result)

        # 4. 앞/뒤 괄호 태그 제거 (최대 2회)
        for _ in range(2):
            result = BRACKET_PATTERN.sub('', result)

        # 5. 구분자를 공백으로 변환
        result = SEPARATOR_PATTERN.sub(' ', result)

        # 6. 소문자 변환
        result = result.lower()

        # 7. 공백 압축
        result = MULTI_SPACE_PATTERN.sub(' ', result).strip()

        # 8. 불용어 제거 (선택적)
        if remove_stopwords:
            words = result.split()
            words = [w for w in words if w not in KOREAN_STOPWORDS]
            result = ' '.join(words)

        return result

    def _token_sort_ratio_difflib(self, s1: str, s2: str) -> float:
        """
        토큰 정렬 후 유사도 계산 (difflib 버전)
        rapidfuzz.token_sort_ratio와 유사한 동작
        """
        # 토큰 정렬
        tokens1 = sorted(s1.split())
        tokens2 = sorted(s2.split())
        sorted1 = ' '.join(tokens1)
        sorted2 = ' '.join(tokens2)

        # SequenceMatcher로 유사도 계산
        matcher = SequenceMatcher(None, sorted1, sorted2)
        return matcher.ratio() * 100

    def _calculate_keyword_bonus(self, text1: str, text2: str) -> float:
        """
        공통 핵심 키워드에 대한 보너스 점수 계산

        두 텍스트에 공통으로 포함된 의미있는 키워드 비율에 따라 보너스 부여
        """
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())

        # 불용어 및 짧은 토큰 제거
        meaningful1 = {t for t in tokens1 if len(t) > 1 and t not in KOREAN_STOPWORDS}
        meaningful2 = {t for t in tokens2 if len(t) > 1 and t not in KOREAN_STOPWORDS}

        if not meaningful1 or not meaningful2:
            return 0.0

        # 공통 키워드 비율 계산
        common = meaningful1 & meaningful2
        total = meaningful1 | meaningful2

        if not total:
            return 0.0

        overlap_ratio = len(common) / len(total)

        # 최대 15점 보너스 (Jaccard 유사도 기반)
        return overlap_ratio * 15.0

    def _containment_ratio(self, text1: str, text2: str) -> float:
        """짧은 제목의 토큰(불용어 포함)이 긴 제목에 얼마나 포함되는지(0~1).

        불용어 제거로 짧은 유사 제목을 놓치던 문제 보완용. 원문 토큰을 쓰고,
        조사/어미 차이는 부분문자열 매칭으로 흡수한다(가격 ⊆ 가격과,
        비교 ⊆ 비교하는). len<=1 토큰은 제외.
        """
        t1 = [t for t in text1.split() if len(t) > 1]
        t2 = [t for t in text2.split() if len(t) > 1]
        if not t1 or not t2:
            return 0.0
        short, long_ = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
        long_set = set(long_)
        matched = sum(
            1 for s in short
            if s in long_set or any(s in lt for lt in long_)
        )
        return matched / len(short)

    def _strip_token(self, tok: str) -> str:
        """토큰에서 구두점·조사/접미를 경량 제거(형태소 분석 없이)."""
        tok = tok.strip(",.·、，。！!?？:;\"'()[]{}")
        for suf in PARTICLE_SUFFIXES:
            if len(tok) > len(suf) + 1 and tok.endswith(suf):
                return tok[:-len(suf)]
        return tok

    def _distinctive_tokens(self, text: str) -> set:
        """제목의 '차별 토큰' 집합.

        불용어·도메인 골격어(GENERIC_KEYWORDS)·짧은 토큰을 제외해
        제목을 구분짓는 핵심어(지명·제품명·주제어)만 남긴다.
        """
        norm = self.normalize_text(text)
        result = set()
        # 콤마 등 구두점도 토큰 경계로 분리(공백 없는 "정보,계절별" 방지).
        for raw in re.split(r'[\s,，、;/·•()\[\]{}]+', norm):
            t = self._strip_token(raw)
            if len(t) <= 1:
                continue
            if t in KOREAN_STOPWORDS or t in GENERIC_KEYWORDS:
                continue
            result.add(t)
        return result

    def _core_divergence(self, title1: str, title2: str) -> bool:
        """두 제목의 핵심어가 완전히 발산하는지 판정.

        양쪽 모두 차별 토큰이 있고, 서로 공유하는 차별 토큰이
        (부분문자열 허용) 하나도 없으면 → 서로 다른 핵심 주제로 본다.
        """
        d1 = self._distinctive_tokens(title1)
        d2 = self._distinctive_tokens(title2)
        if not d1 or not d2:
            return False
        for a in d1:
            for b in d2:
                if a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)):
                    return False  # 공유 차별 토큰 존재 → 발산 아님
        return True

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        순수 텍스트 유사도 계산 (지역명 처리 없음)

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 점수 (0-100)
        """
        # 정규화
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)

        if not norm1 or not norm2:
            return 0.0

        # 완전 일치
        if norm1 == norm2:
            return 100.0

        # 포함 관계 검사
        if norm1 in norm2 or norm2 in norm1:
            longer = max(len(norm1), len(norm2))
            shorter = min(len(norm1), len(norm2))
            ratio = shorter / longer if longer > 0 else 0
            return 85.0 + (ratio * 10.0)

        # rapidfuzz 또는 difflib (토큰 정렬 적용)
        if HAS_RAPIDFUZZ:
            base_score = fuzz.token_sort_ratio(norm1, norm2)
        else:
            base_score = self._token_sort_ratio_difflib(norm1, norm2)

        # 키워드 보너스 적용
        bonus = self._calculate_keyword_bonus(norm1, norm2)
        score = min(100.0, base_score + bonus)

        # 포함도(부분집합) 보정: 짧은 제목이 긴 제목에 대부분 포함되면
        # 점수를 회색지대(68~74)까지만 끌어올려 AI가 최종 판정하게 한다.
        # (자동 그룹이 아니라 회색지대 진입까지만 — 오그룹 위험 최소화)
        contain = self._containment_ratio(norm1, norm2)
        if len(norm1.split()) >= 2 and len(norm2.split()) >= 2 and contain >= 0.6:
            contain_score = 68.0 + (contain - 0.6) * 15.0  # 0.6→68 ~ 1.0→74
            score = max(score, contain_score)

        return round(score, 2)

