"""
내부링크 삽입 서비스

생성된 마크다운 글에 내부링크를 삽입합니다.

위치별 규칙:
- 서론 뒤: 유사 제목 글 (버튼/일반 선택, 최대 5개)
- 본문 섹션 뒤: 섹션 제목과 유사한 글 (일반 링크, 섹션당 0~1개)
- 결론 뒤: 관련 글 (리스트 스타일 선택, 점수순 + 미색인 우선)

관련성 판정: link_relevance (조사·불용어 제거 토큰, 공통 2개 이상, 같은 topic 우선)
본문 섹션 유사도: shared SimilarityService (토큰화된 제목끼리 비교)
순서도: docs/flowcharts/internal_link_relevance.md
"""
import logging
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost
from ...models.title import MainTitle

# shared SimilarityService 임포트 (Docker/로컬 환경 모두 지원)
_shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
for _path in _shared_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
        break

from services.similarity_service import SimilarityService

from .index_priority import prioritize as prioritize_by_index
from .link_relevance import rank_related, restrict_by_category, tokenize

logger = logging.getLogger(__name__)

# 내부링크 기본 설정
# 도입부 링크는 적을수록 낫다. 5개씩 박히던 것이 색인 실패의
# 한 원인이었다(진단: search_visibility_all_blogs.md).
DEFAULT_INTRO_LINK_COUNT = 2
DEFAULT_CONCLUSION_LINK_COUNT = 3
DEFAULT_SIMILARITY_THRESHOLD = 75
MAX_INTRO_LINKS = 5
# 정리로 초안·비공개로 돌린 글(10/7·10/8). status 는 DB 에만 있고 모델에 없다.
NOT_UNPUBLISHED = text("coalesce(crawled_posts.status, '') <> 'unpublished'")


class InternalLinker:
    """
    생성된 글에 내부링크를 삽입하는 서비스

    마크다운 상태에서 링크를 삽입합니다.
    HTML 변환은 SubstitutionProcessor에서 처리합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # 글 id → (topic_id, subtopic_id). _load_blog_posts 가 채운다.
        self._post_cats: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
        # 현재 글의 (topic_id, subtopic_id). 모르면 (None, None) → 전체 후보
        self._current_cat: Tuple[Optional[int], Optional[int]] = (None, None)

    async def insert_links(
        self,
        content: str,
        blog_id: int,
        current_title: str,
        module_settings: Optional[dict] = None,
        source_title_id: Optional[int] = None,
        category: Optional[Tuple[Optional[int], Optional[int]]] = None,
    ) -> str:
        """
        마크다운 글에 내부링크 삽입. 실패해도 글 생성은 막지 않는다(링크 0개).

        Args:
            content: 마크다운 글 본문
            blog_id: 블로그 ID
            current_title: 현재 글 제목 (중복 방지)
            module_settings: 모듈 설정 (Module.settings)
            source_title_id: 원래 정식제목 번호 — 이 제목의 topic/subtopic 으로
                주제를 찾는다(재조합 제목으로는 못 찾아 블로그 전체가 후보가 됐다)
            category: (topic_id, subtopic_id) 를 이미 알면 그대로 쓴다(리뉴얼)

        Returns:
            내부링크가 삽입된 마크다운 글
        """
        try:
            return await self._insert_links(
                content, blog_id, current_title, module_settings,
                source_title_id, category)
        except Exception as e:  # noqa: BLE001 — 링크 실패가 생성 실패로 번지지 않게
            logger.warning(f"[INTERNAL_LINK] 삽입 실패 → 링크 0개로 진행: {e}")
            return content

    async def _insert_links(
        self,
        content: str,
        blog_id: int,
        current_title: str,
        module_settings: Optional[dict],
        source_title_id: Optional[int],
        category: Optional[Tuple[Optional[int], Optional[int]]],
    ) -> str:
        """insert_links 본체(설정 읽기 → 후보 로드 → 서론·본문·결론 삽입)."""
        blog = await self.db.get(Blog, blog_id)
        if not blog:
            logger.warning(f"[INTERNAL_LINK] 블로그 없음: id={blog_id}")
            return content

        # 모듈 설정에서 내부링크 설정을 우선 사용, 없으면 블로그 설정 폴백
        if module_settings and "internal_links" in module_settings:
            link_settings = module_settings.get("internal_links", {})
        else:
            settings = blog.placeholders or {}
            link_settings = settings.get("internal_links", {})

        if not link_settings.get("enabled", False):
            logger.info("[INTERNAL_LINK] 내부링크 비활성화")
            return content

        # 설정 추출
        intro_count = min(
            link_settings.get("intro_count", DEFAULT_INTRO_LINK_COUNT),
            MAX_INTRO_LINKS,
        )
        intro_link_type = link_settings.get("intro_link_type", "button")
        conclusion_count = link_settings.get(
            "conclusion_count", DEFAULT_CONCLUSION_LINK_COUNT
        )
        conclusion_list_style = link_settings.get(
            "conclusion_list_style", "dash"
        )
        similarity_threshold = link_settings.get(
            "similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD
        )
        body_count = link_settings.get("body_count", 1)
        body_link_type = link_settings.get("body_link_type", "quote")

        # 버튼 클래스: 블로그 placeholders.link_styles 기준 (CSS 치환자와 일치).
        # 버튼 링크는 div 래퍼로 생성해야 .button-link 블록 스타일이 적용된다.
        blog_link_styles = (blog.placeholders or {}).get("link_styles") or {}
        button_class = blog_link_styles.get("button_class") or "button-link"

        # SimilarityService 인스턴스 생성
        sim_service = SimilarityService(threshold=similarity_threshold)

        logger.info(
            f"[INTERNAL_LINK] 설정 | intro={intro_count} "
            f"| type={intro_link_type} | body={body_count} "
            f"| body_type={body_link_type} | conclusion={conclusion_count} "
            f"| style={conclusion_list_style} | threshold={similarity_threshold}"
        )

        # 블로그 내 전체 포스트 1회 로드
        all_posts = await self._load_blog_posts(blog_id, current_title)
        if not all_posts:
            logger.info("[INTERNAL_LINK] 삽입 가능한 포스트 없음")
            return content
        self._current_cat = await self._load_current_category(
            current_title, source_title_id, category)

        used_urls: set = set()

        # 1. 서론 뒤 링크 삽입 (키워드 매칭 + 최신순/랜덤 fallback)
        # 글 제목 전체 유사도(≥임계값)는 긴 SEO 제목 간에는 거의 0건이라,
        # 서론은 공통 핵심 키워드 기반으로 매칭하고 부족분을 보충한다.
        intro_posts = self._find_intro_posts(
            current_title, all_posts, used_urls, intro_count, sim_service
        )
        content = self._insert_intro_links(
            content, intro_posts, used_urls, intro_count, intro_link_type,
            button_class=button_class,
        )

        # 2. 본문 섹션 링크 삽입 (각 ## 섹션 끝, 섹션 제목별 유사도 매칭)
        content = self._insert_section_links(
            content, all_posts, used_urls, sim_service,
            body_count=body_count, body_link_type=body_link_type,
            button_class=button_class,
        )

        # 3. 결론 뒤 링크 삽입
        # 관련 글만 점수순으로 고른 뒤 **미색인 글을 앞으로 당긴다**(S7,
        # 안정 정렬이라 같은 색인상태 안에서는 점수순 유지).
        # 2026-09-29: 무작위 셔플 제거 — 여드름 글 끝에 '하나카드 분실신고'
        # 가 붙던 원인 중 하나. 관련 글이 부족하면 그만큼만 넣는다.
        remaining = [p for p in all_posts if p.url not in used_urls]
        related = self._filter_related(current_title, remaining, sim_service)
        related = await prioritize_by_index(self.db, blog_id, related)
        conclusion_posts = related[:conclusion_count]
        if len(conclusion_posts) < conclusion_count:
            logger.info(
                "[INTERNAL_LINK] 결론 링크 %d/%d — 관련 글이 부족해 "
                "채우지 않음(무관한 링크 방지)",
                len(conclusion_posts), conclusion_count)
        content = self._insert_conclusion_links(
            content, conclusion_posts, used_urls, conclusion_list_style
        )

        link_count = len(used_urls)
        logger.info(f"[INTERNAL_LINK] 완료 | 삽입={link_count}개")
        return content

    # ── 포스트 검색 ──────────────────────────────────

    async def _load_current_category(
        self,
        current_title: str,
        source_title_id: Optional[int] = None,
        category: Optional[Tuple[Optional[int], Optional[int]]] = None,
    ) -> Tuple[Optional[int], Optional[int]]:
        """현재 글의 (topic_id, subtopic_id).

        순서: 넘겨받은 category → 원래 정식제목 번호(source_title_id) →
        제목이 같은 MainTitle. 못 찾거나 조회에 실패하면 (None, None) —
        카테고리 제한 없이 전체 후보(관련성 토큰 기준은 그대로 적용).
        """
        if category and category[0] is not None:
            return (category[0], category[1])
        cond = (MainTitle.id == source_title_id if source_title_id
                else MainTitle.title == current_title)
        try:
            row = (await self.db.execute(
                select(MainTitle.topic_id, MainTitle.subtopic_id)
                .where(cond)
                .limit(1)
            )).first()
        except Exception as e:  # noqa: BLE001 — 링크 삽입을 막지 않는다
            logger.warning(f"[INTERNAL_LINK] 현재 글 카테고리 조회 실패: {e}")
            return (None, None)
        return (row[0], row[1]) if row else (None, None)

    async def _load_blog_posts(
        self, blog_id: int, current_title: str
    ) -> List[CrawledPost]:
        """블로그 내 URL이 있는 포스트 전체 로드 (+ 카테고리 맵 갱신).

        MainTitle 을 outer join 해 topic/subtopic 을 컬럼으로 함께 가져온다.
        relationship lazy load 를 쓰지 않아 async 에서 MissingGreenlet 이
        나지 않는다.
        """
        query = (
            select(CrawledPost, MainTitle.topic_id, MainTitle.subtopic_id)
            .outerjoin(
                MainTitle,
                CrawledPost.matched_main_title_id == MainTitle.id,
            )
            .where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.url.isnot(None),
                CrawledPost.url != "",
                ~CrawledPost.url.startswith("https://pending-content"),
                CrawledPost.title != current_title,
                # 정리로 비공개·초안으로 돌린 글(10/7·10/8)은 링크하지 않는다
                NOT_UNPUBLISHED,
            )
        )
        result = await self.db.execute(query)
        posts: List[CrawledPost] = []
        self._post_cats = {}
        for post, topic_id, subtopic_id in result.all():
            posts.append(post)
            self._post_cats[post.id] = (topic_id, subtopic_id)
        logger.debug(
            f"[INTERNAL_LINK] 포스트 로드 | blog_id={blog_id} "
            f"| count={len(posts)}"
        )
        return posts

    def _find_similar_by_score(
        self,
        target_title: str,
        posts: List[CrawledPost],
        sim_service: SimilarityService,
        limit: int = 10,
    ) -> List[CrawledPost]:
        """본문 섹션용 유사도 매칭 (threshold 이상만, 점수 내림차순).

        서론·결론과 **같은 토큰화**(조사·불용어 제거)를 거친 문자열끼리
        비교하고, 공통 의미토큰이 1개도 없으면 점수와 무관하게 제외한다.
        """
        target_kw = tokenize(target_title)
        if not target_kw:
            return []
        target_norm = " ".join(sorted(target_kw))
        scored = []
        for post in posts:
            post_kw = tokenize(post.title)
            if not (target_kw & post_kw):
                continue
            score = sim_service.calculate_text_similarity(
                target_norm, " ".join(sorted(post_kw))
            )
            if score >= sim_service.threshold:
                scored.append((post, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [post for post, _ in scored[:limit]]

    def _extract_keywords(
        self, text: str, sim_service: Optional[SimilarityService] = None
    ) -> set:
        """제목에서 의미토큰 집합 추출 (link_relevance.tokenize 위임).

        Args:
            text: 원본 제목
            sim_service: 하위호환용(미사용)

        Returns:
            조사·어미·불용어·1글자·숫자를 뺀 토큰 집합
        """
        return tokenize(text)

    def _find_intro_posts(
        self,
        current_title: str,
        posts: List[CrawledPost],
        used_urls: set,
        count: int,
        sim_service: SimilarityService,
    ) -> List[CrawledPost]:
        """서론 링크 후보 선정: 관련 글만 점수순 상위 count 개.

        관련 = 같은 topic 우선 + 공통 의미토큰 2개 이상
        (link_relevance.rank_related). 부족분을 최신/랜덤 글로 채우지
        않는다 — 0개여도 정상이다.

        Args:
            current_title: 현재 글 제목
            posts: 블로그 내 발행 포스트 목록
            used_urls: 이미 사용된 URL 집합(중복 방지)
            count: 채울 링크 개수
            sim_service: 하위호환용(미사용)

        Returns:
            서론에 삽입할 포스트 목록 (최대 count 개)
        """
        if count <= 0:
            return []
        available = [p for p in posts if p.url and p.url not in used_urls]
        matched = rank_related(
            current_title, available, self._post_cats, self._current_cat
        )[:count]
        if len(matched) < count:
            logger.info(
                "[INTERNAL_LINK] 서론 링크 %d/%d — 관련 글이 부족해 "
                "채우지 않음(무관한 링크 방지)",
                len(matched), count,
            )
        return matched

    def _filter_related(
        self,
        current_title: str,
        posts: List[CrawledPost],
        sim_service: Optional[SimilarityService] = None,
    ) -> List[CrawledPost]:
        """현재 글과 **주제가 닿는** 글만 점수순으로 남긴다(결론 링크용).

        서론과 같은 기준(같은 topic 우선 + 공통 의미토큰 2개 이상).
        현재 글에서 토큰을 충분히 못 뽑으면 **빈 목록** — 판단 근거 없이
        아무 글이나 붙이지 않는다(2026-09-29 변경).
        """
        return rank_related(
            current_title, posts, self._post_cats, self._current_cat
        )

    def _find_best_match_for_section(
        self,
        section_title: str,
        posts: List[CrawledPost],
        sim_service: SimilarityService,
    ) -> Optional[CrawledPost]:
        """섹션 제목과 가장 유사한 포스트 1개 반환 (threshold 이상만)"""
        matched = self._find_similar_by_score(
            section_title, posts, sim_service, limit=1
        )
        return matched[0] if matched else None

    # ── 헤딩 추출 ──────────────────────────────────

    # ── 링크 삽입 ──────────────────────────────────

    @staticmethod
    def _section_headings(content: str) -> list:
        """본문 섹션 헤딩 목록. **H1(글 타이틀)은 제외한다.**

        예전에는 "헤딩 중 두 번째" 를 첫 섹션으로 봤다. 첫 헤딩이 H1
        타이틀이라는 전제였는데, 본문 H1 이 제목과 겹칠 때 제거되면서
        (quality_gate.strip_duplicate_h1) 그 전제가 깨졌다. 실측으로 최근
        30일 글 639건 중 476건(75%)에 H1 이 없었고, 그 글들은 서론 링크가
        한 섹션씩 밀려 있었다.

        레벨로 판단하면 H1 유무와 무관하게 같은 자리에 들어간다.
        """
        heads = list(re.finditer(
            r'^(#{1,6})[ \t]+(.+?)[ \t]*$', content, re.MULTILINE))
        sections = [m for m in heads if len(m.group(1)) > 1]
        # 모두 H1 이면(비정상 구조) 첫 헤딩만 타이틀로 보고 나머지를 쓴다
        return sections if sections else heads[1:]

    def _insert_intro_links(
        self,
        content: str,
        posts: List[CrawledPost],
        used_urls: set,
        max_count: int,
        link_type: str = "button",
        button_class: str = "button-link",
    ) -> str:
        """서론(도입부) 끝에 링크 삽입 (버튼 또는 일반).

        서론은 글 타이틀(# H1) 다음, 첫 본문 섹션(## H2) 직전까지다.
        따라서 첫 본문 섹션 헤딩 '앞'에 링크 블록을 삽입한다.
        """
        available = [p for p in posts if p.url and p.url not in used_urls]
        if not available:
            logger.debug("[INTERNAL_LINK] 서론: 삽입 가능한 포스트 없음")
            return content

        links_to_insert = available[:max_count]

        if link_type == "button":
            link_block = self._build_button_links(
                links_to_insert, button_class
            )
        else:
            link_block = self._build_normal_links(links_to_insert)

        for post in links_to_insert:
            used_urls.add(post.url)

        # **첫 본문 섹션 헤딩 앞**에 삽입한다(= 서론 끝).
        # 헤딩 순번이 아니라 레벨로 찾는다 — H1 이 제거된 글에서 한 섹션씩
        # 밀리던 자리다.
        sections = self._section_headings(content)
        if sections:
            insert_pos = sections[0].start()
            content = (
                content[:insert_pos]
                + link_block + "\n\n"
                + content[insert_pos:]
            )
        else:
            # 섹션 헤딩이 없으면 본문 구분이 없어 끝에 추가
            content += "\n\n" + link_block

        logger.debug(
            f"[INTERNAL_LINK] 서론 링크 {len(links_to_insert)}개 삽입"
        )
        return content

    def _insert_section_links(
        self,
        content: str,
        all_posts: List[CrawledPost],
        used_urls: set,
        sim_service: SimilarityService,
        body_count: int = 1,
        body_link_type: str = "quote",
        button_class: str = "button-link",
    ) -> str:
        """본문 각 섹션 끝에 유사 링크 삽입 (섹션 제목별 유사도 매칭).

        글 구조는 '# 타이틀 / 서론 / ## 섹션들 / ## 결론'. 본문 섹션은
        첫 헤딩(타이틀) 다음의 '섹션 레벨' 헤딩들 중 마지막(결론)을 제외한
        것이다. 각 본문 섹션 제목과 유사도 매칭되는 포스트가 있을 때만
        해당 섹션 끝(다음 섹션 헤딩 직전)에 링크를 삽입한다.

        Args:
            content: 마크다운 본문
            all_posts: 전체 포스트 목록
            used_urls: 이미 사용된 URL 집합
            sim_service: 유사도 서비스
            body_count: 섹션당 삽입할 링크 수 (0이면 스킵)
            body_link_type: 링크 유형 ("quote" | "normal" | "button")
            button_class: 버튼형일 때 div 래퍼에 적용할 CSS 클래스

        Returns:
            링크가 삽입된 마크다운 글
        """
        if body_count <= 0:
            logger.debug("[INTERNAL_LINK] 본론: body_count=0, 스킵")
            return content
        if not all_posts:
            return content

        # 서론 링크와 **같은 기준**으로 섹션을 찾는다. 따로 판단하면
        # H1 유무에 따라 두 링크가 서로 다른 섹션을 가리킨다.
        sections = self._section_headings(content)
        if not sections:
            return content

        # 섹션 레벨 = 첫 본문 섹션의 레벨(보통 ## H2). 더 깊은 헤딩은
        # 그 섹션의 하위 항목이므로 섹션으로 세지 않는다.
        section_level = len(sections[0].group(1))
        section_heads = [
            m for m in sections if len(m.group(1)) == section_level
        ]
        if len(section_heads) < 2:
            # 본문 섹션(결론 제외)이 없으면 스킵
            logger.debug("[INTERNAL_LINK] 본론: 본문 섹션 부족, 스킵")
            return content

        body_heads = section_heads[:-1]  # 마지막=결론 제외

        # 각 섹션 끝(다음 섹션 헤딩 직전)에 삽입. 뒤에서부터 적용해 위치
        # 오프셋 관리를 피한다. used_urls 는 루프 중 즉시 갱신해 중복 방지.
        insertions: list = []
        inserted = 0
        for i, head in enumerate(body_heads):
            section_title = head.group(2).strip()
            next_start = section_heads[i + 1].start()
            available = restrict_by_category(
                [p for p in all_posts if p.url and p.url not in used_urls],
                self._post_cats, self._current_cat)
            matched_posts = self._find_similar_by_score(
                section_title, available, sim_service, limit=body_count
            )
            if not matched_posts:
                continue
            link_lines = [
                self._format_body_link(p, body_link_type, button_class)
                for p in matched_posts
            ]
            for post in matched_posts:
                used_urls.add(post.url)
            link_text = "\n\n" + "\n\n".join(link_lines) + "\n"
            insertions.append((next_start, link_text))
            inserted += len(matched_posts)

        for pos, text in sorted(insertions, key=lambda x: x[0], reverse=True):
            content = content[:pos] + text + content[pos:]

        logger.debug(
            f"[INTERNAL_LINK] 본론 링크 {inserted}개 삽입 "
            f"(본문 섹션 {len(body_heads)}개 중)"
        )
        return content

    def _format_body_link(
        self,
        post: CrawledPost,
        link_type: str,
        button_class: str = "button-link",
    ) -> str:
        """본론 링크 한 줄 포맷 (버튼 / 일반 / 인용).

        - button: div 래퍼 버튼 (서론 버튼과 동일, .button-link 블록 스타일)
        - normal: 일반 마크다운 링크
        - quote(기본): 인용문 형태
        """
        if link_type == "button":
            return (
                f'<div class="{button_class}">'
                f'<a href="{post.url}">{post.title}</a></div>'
            )
        if link_type == "normal":
            return f"[{post.title}]({post.url})"
        return f"> 관련 글: [{post.title}]({post.url})"

    def _insert_conclusion_links(
        self,
        content: str,
        posts: List[CrawledPost],
        used_urls: set,
        list_style: str = "dash",
    ) -> str:
        """결론 뒤에 랜덤 링크 삽입 (리스트 스타일 선택 가능)"""
        available = [p for p in posts if p.url and p.url not in used_urls]
        if not available:
            return content

        if list_style == "none":
            # "none" 은 각 링크가 별도 단락으로 변환되어 한 줄씩 띄어
            # 출력되는 문제가 있어 한 단락 안에 <br> 로 줄바꿈만 처리.
            inline_parts = []
            for post in available:
                if post.url in used_urls:
                    continue
                inline_parts.append(
                    f"[{post.title}]({post.url})"
                )
                used_urls.add(post.url)
            if not inline_parts:
                return content
            link_block = (
                "\n\n---\n\n### 함께 보면 좋은 글\n\n"
                + "<br>".join(inline_parts)
            )
            content += link_block
            return content

        link_lines = []
        for i, post in enumerate(available):
            if post.url not in used_urls:
                if list_style == "number":
                    link_lines.append(
                        f"{i + 1}. [{post.title}]({post.url})"
                    )
                elif list_style == "dash":
                    link_lines.append(f"- [{post.title}]({post.url})")
                else:
                    link_lines.append(f"[{post.title}]({post.url})")
                used_urls.add(post.url)

        if not link_lines:
            return content

        link_block = (
            "\n\n---\n\n### 함께 보면 좋은 글\n\n"
            + "\n".join(link_lines)
        )
        content += link_block
        return content

    # ── 링크 블록 빌더 ──────────────────────────────

    def _build_button_links(
        self, posts: List[CrawledPost], button_class: str = "button-link"
    ) -> str:
        """버튼 스타일 링크 블록 생성 (div 래퍼).

        CSS 치환자의 버튼 클래스(.button-link 등)는 블록 요소(div)를
        가정하므로 ``<div class="..."><a></div>`` 형태로 생성한다.
        과거 ``<center><a>`` 방식은 apply_placeholders 의 공통 center
        unwrap 으로 ``<a class="button-link">`` (inline) 만 남아 버튼
        스타일이 적용되지 않았다.
        """
        lines = []
        for post in posts:
            lines.append(
                f'<div class="{button_class}">'
                f'<a href="{post.url}">{post.title}</a></div>'
            )
        return "\n".join(lines)

    def _build_normal_links(self, posts: List[CrawledPost]) -> str:
        """일반 인용 스타일 링크 블록 생성"""
        lines = []
        for post in posts:
            lines.append(f"> 관련 글: [{post.title}]({post.url})")
        return "\n\n".join(lines)
