"""리뉴얼 실행 계획 결정 (P2b 결정 로직, 순수 함수).

제목 모드 + 글/이미지 양식으로 "재조합 여부"와 "이미지 재사용 vs 새 생성"을
결정한다. 규칙(사용자 합의):
- 제목: keep(유지) | recombine(재조합).
- 이미지: 새로 생성. 단 (제목 keep AND blogauto 글 AND blogauto 이미지)이면
  기존 이미지 URL 재사용. 재조합이거나 레거시(비-양식) 글/이미지면 새 생성.
"""
from dataclasses import dataclass


@dataclass
class RenewalPlan:
    """리뉴얼 실행 계획."""

    recombine_title: bool      # True=재조합, False=기존 제목 유지
    image_action: str          # "reuse" | "new"
    reuse_image_url: str = ""  # image_action="reuse"일 때 사용할 기존 이미지 URL


def decide_renewal_plan(
    title_mode: str,
    is_blogauto_post: bool,
    image_origin: str,
    featured_image_url: str = "",
) -> RenewalPlan:
    """리뉴얼 계획 결정.

    Args:
        title_mode: "keep" | "recombine".
        is_blogauto_post: 우리 DB(CrawledPost)에 있는 blogauto 발행글 여부.
        image_origin: "blogauto" | "legacy" | "none" (RenewalSource 판별).
        featured_image_url: 라이브 글의 대표이미지 URL.

    Returns:
        RenewalPlan.
    """
    recombine = title_mode == "recombine"
    can_reuse = (
        not recombine
        and is_blogauto_post
        and image_origin == "blogauto"
        and bool(featured_image_url)
    )
    if can_reuse:
        return RenewalPlan(
            recombine_title=False,
            image_action="reuse",
            reuse_image_url=featured_image_url,
        )
    return RenewalPlan(recombine_title=recombine, image_action="new")
