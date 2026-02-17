"""
내부링크 삽입 서비스

생성된 마크다운 글에 내부링크를 삽입합니다.

위치별 규칙:
- 서론 뒤: 유사 제목 글 (버튼/일반 선택, 최대 5개)
- 본문 섹션 뒤: 섹션 제목과 유사한 글 (일반 링크, 섹션당 0~1개)
- 결론 뒤: 랜덤 글 (리스트 스타일 선택)

유사도 매칭: shared SimilarityService 사용 (token_sort_ratio + 키워드 보너스)
"""
import logging
import os
import random
import re
import sys
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.blog import Blog
from ...models.crawled_post import CrawledPost

# shared SimilarityService 임포트 (Docker/로컬 환경 모두 지원)
_shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
for _path in _shared_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
        break

from services.similarity_service import SimilarityService

logger = logging.getLogger(__name__)

# 내부링크 기본 설정
DEFAULT_INTRO_LINK_COUNT = 3
DEFAULT_CONCLUSION_LINK_COUNT = 3
DEFAULT_SIMILARITY_THRESHOLD = 75
MAX_INTRO_LINKS = 5


class InternalLinker:
    """
    생성된 글에 내부링크를 삽입하는 서비스

    마크다운 상태에서 링크를 삽입합니다.
    HTML 변환은 SubstitutionProcessor에서 처리합니다.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def insert_links(
        self,
        content: str,
        blog_id: int,
        current_title: str,
        module_settings: Optional[dict] = None,
    ) -> str:
        """
        마크다운 글에 내부링크 삽입

        Args:
            content: 마크다운 글 본문
            blog_id: 블로그 ID
            current_title: 현재 글 제목 (중복 방지)
            module_settings: 모듈 설정 (Module.settings)

        Returns:
            내부링크가 삽입된 마크다운 글
        """
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

        # SimilarityService 인스턴스 생성
        sim_service = SimilarityService(threshold=similarity_threshold)

        # 블로그 내 전체 포스트 1회 로드
        all_posts = await self._load_blog_posts(blog_id, current_title)
        if not all_posts:
            logger.info("[INTERNAL_LINK] 삽입 가능한 포스트 없음")
            return content

        used_urls: set = set()

        # 1. 서론 뒤 링크 삽입 (유사도 기반 매칭)
        intro_similar = self._find_similar_by_score(
            current_title, all_posts, sim_service, limit=intro_count
        )
        content = self._insert_intro_links(
            content, intro_similar, used_urls, intro_count, intro_link_type
        )

        # 2. 본문 섹션 링크 삽입 (섹션 제목별 유사도 매칭)
        section_headings = self._extract_section_headings(content)
        content = self._insert_section_links(
            content, all_posts, section_headings, used_urls, sim_service
        )

        # 3. 결론 뒤 링크 삽입 (랜덤 포스트)
        remaining = [p for p in all_posts if p.url not in used_urls]
        random.shuffle(remaining)
        conclusion_posts = remaining[:conclusion_count]
        content = self._insert_conclusion_links(
            content, conclusion_posts, used_urls, conclusion_list_style
        )

        link_count = len(used_urls)
        logger.info(f"[INTERNAL_LINK] 완료 | 삽입={link_count}개")
        return content

    # ── 포스트 검색 ──────────────────────────────────

    async def _load_blog_posts(
        self, blog_id: int, current_title: str
    ) -> List[CrawledPost]:
        """블로그 내 URL이 있는 포스트 전체 로드"""
        query = (
            select(CrawledPost)
            .where(
                CrawledPost.blog_id == blog_id,
                CrawledPost.url.isnot(None),
                CrawledPost.title != current_title,
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _find_similar_by_score(
        self,
        target_title: str,
        posts: List[CrawledPost],
        sim_service: SimilarityService,
        limit: int = 10,
    ) -> List[CrawledPost]:
        """유사도 점수 기반 포스트 매칭 (threshold 이상만, 점수 내림차순)"""
        scored = []
        for post in posts:
            score = sim_service.calculate_text_similarity(
                target_title, post.title
            )
            if score >= sim_service.threshold:
                scored.append((post, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [post for post, _ in scored[:limit]]

    def _find_best_match_for_section(
        self,
        section_title: str,
        posts: List[CrawledPost],
        sim_service: SimilarityService,
    ) -> Optional[CrawledPost]:
        """섹션 제목과 가장 유사한 포스트 1개 반환 (threshold 이상만)"""
        best_post = None
        best_score = 0.0

        for post in posts:
            score = sim_service.calculate_text_similarity(
                section_title, post.title
            )
            if score >= sim_service.threshold and score > best_score:
                best_score = score
                best_post = post

        if best_post:
            logger.debug(
                f"[INTERNAL_LINK] 섹션 매칭: '{section_title[:20]}' "
                f"→ '{best_post.title[:20]}' (score={best_score:.1f})"
            )
        return best_post

    # ── 헤딩 추출 ──────────────────────────────────

    def _extract_section_headings(self, content: str) -> List[str]:
        """본론 ## 헤딩 텍스트 추출 (서론 첫번째/결론 마지막 제외)"""
        headings = re.findall(r'\n## (.+)', content)
        if len(headings) <= 2:
            return []
        return headings[1:-1]

    # ── 링크 삽입 ──────────────────────────────────

    def _insert_intro_links(
        self,
        content: str,
        posts: List[CrawledPost],
        used_urls: set,
        max_count: int,
        link_type: str = "button",
    ) -> str:
        """서론 뒤에 링크 삽입 (버튼 또는 일반)"""
        available = [p for p in posts if p.url and p.url not in used_urls]
        if not available:
            return content

        links_to_insert = available[:max_count]

        if link_type == "button":
            link_block = self._build_button_links(links_to_insert)
        else:
            link_block = self._build_normal_links(links_to_insert)

        for post in links_to_insert:
            used_urls.add(post.url)

        # 첫 번째 ## 헤딩 앞에 삽입 (서론 끝)
        match = re.search(r'\n(## .+)', content)
        if match:
            insert_pos = match.start()
            content = (
                content[:insert_pos]
                + "\n\n" + link_block + "\n"
                + content[insert_pos:]
            )
        else:
            content += "\n\n" + link_block

        return content

    def _insert_section_links(
        self,
        content: str,
        all_posts: List[CrawledPost],
        section_headings: List[str],
        used_urls: set,
        sim_service: SimilarityService,
    ) -> str:
        """본문 섹션 뒤에 유사 링크 삽입 (섹션당 0~1개, 유사도 기반)"""
        if not section_headings or not all_posts:
            return content

        headings = list(re.finditer(r'\n(## .+)', content))
        if len(headings) < 3:
            return content

        # 본론 섹션 인덱스 (첫 번째=서론 뒤 첫 섹션, 마지막=결론 제외)
        body_indices = list(range(1, len(headings) - 1))
        offset = 0

        for idx, heading_idx in enumerate(body_indices):
            if idx >= len(section_headings):
                break

            section_title = section_headings[idx]
            available = [
                p for p in all_posts
                if p.url and p.url not in used_urls
            ]

            best_post = self._find_best_match_for_section(
                section_title, available, sim_service
            )
            if not best_post:
                continue

            link_text = (
                f"\n\n> 관련 글: [{best_post.title}]({best_post.url})\n"
            )

            # 다음 헤딩 바로 앞에 삽입
            next_heading_pos = (
                headings[heading_idx + 1].start() + offset
                if heading_idx + 1 < len(headings)
                else len(content)
            )
            content = (
                content[:next_heading_pos]
                + link_text
                + content[next_heading_pos:]
            )
            offset += len(link_text)
            used_urls.add(best_post.url)

        return content

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

        link_lines = []
        for i, post in enumerate(available):
            if post.url not in used_urls:
                if list_style == "number":
                    link_lines.append(
                        f"{i + 1}. [{post.title}]({post.url})"
                    )
                elif list_style == "dash":
                    link_lines.append(f"- [{post.title}]({post.url})")
                else:  # "none"
                    link_lines.append(f"[{post.title}]({post.url})")
                used_urls.add(post.url)

        if not link_lines:
            return content

        link_block = (
            "\n\n---\n\n**함께 보면 좋은 글**\n\n"
            + "\n".join(link_lines)
        )
        content += link_block
        return content

    # ── 링크 블록 빌더 ──────────────────────────────

    def _build_button_links(self, posts: List[CrawledPost]) -> str:
        """버튼 스타일 링크 블록 생성 (마크다운)"""
        lines = []
        for post in posts:
            lines.append(
                f'<center><a href="{post.url}">{post.title}</a></center>'
            )
        return "\n".join(lines)

    def _build_normal_links(self, posts: List[CrawledPost]) -> str:
        """일반 인용 스타일 링크 블록 생성"""
        lines = []
        for post in posts:
            lines.append(f"> 관련 글: [{post.title}]({post.url})")
        return "\n\n".join(lines)
