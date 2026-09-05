"""리뉴얼 실행 계획 결정 (P2b 결정 로직, 순수 함수).

제목 모드 + 글/이미지 양식으로 "재조합 여부"와 "이미지 재사용 vs 새 생성"을
결정한다. 규칙(사용자 합의):
- 제목: keep(유지) | recombine(재조합).
- 이미지: 새로 생성. 단 (제목 keep AND blogauto 글 AND blogauto 이미지)이면
  기존 이미지 URL 재사용. 재조합이거나 레거시(비-양식) 글/이미지면 새 생성.

여기에 **성과 축**이 붙는다(analytics P4). 유입을 보고 글마다 동작을 정한다.
같은 블로그의 모든 글을 똑같이 갈아엎던 것이 문제였다.

    keep     들어오는 사람이 유지된다 → 아무것도 하지 않는다
    augment  줄고 있다               → 기존 본문을 살려 확장
    title    노출은 되는데 안 들어온다 → 제목·도입부만, 본문 유지
    rewrite  노출도 유입도 없다        → 전면 재작성(지금 동작)
    legacy   판단 근거 없음            → 지금 동작
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RenewalPlan:
    """리뉴얼 실행 계획."""

    recombine_title: bool      # True=재조합, False=기존 제목 유지
    image_action: str          # "reuse" | "new"
    reuse_image_url: str = ""  # image_action="reuse"일 때 사용할 기존 이미지 URL
    # 성과 판정(analytics). 미연동이면 legacy — 지금 동작 그대로다.
    action: str = "legacy"
    action_reason: str = ""

    @property
    def skip(self) -> bool:
        """건드리지 말아야 하는가."""
        return self.action == "keep"

    @property
    def content_mode(self) -> str:
        """본문 생성 모드. renewal_generator 의 renewal_prompt.mode 로 간다.

        title 은 본문을 새로 쓰지 않는다 — 노출이 쌓인 글의 본문을 갈아엎으면
        순위를 잃는다. 제목만 바꾸고 본문은 확장 쪽으로 둔다.
        """
        if self.action in ("augment", "title"):
            return "additional"
        if self.action == "rewrite":
            return "new"
        return ""      # legacy: 모듈 설정을 그대로 따른다


def decide_renewal_plan(
    title_mode: str,
    is_blogauto_post: bool,
    image_origin: str,
    featured_image_url: str = "",
    action: str = "legacy",
    action_reason: str = "",
) -> RenewalPlan:
    """리뉴얼 계획 결정.

    Args:
        title_mode: "keep" | "recombine".
        is_blogauto_post: 우리 DB(CrawledPost)에 있는 blogauto 발행글 여부.
        image_origin: "blogauto" | "legacy" | "none" (RenewalSource 판별).
        featured_image_url: 라이브 글의 대표이미지 URL.
        action: 성과 판정(keep/augment/title/rewrite/legacy).
        action_reason: 그 판정의 근거(로그·화면용).

    Returns:
        RenewalPlan.
    """
    # 노출이 쌓인 글은 제목을 손대야 하므로 재조합을 강제한다. 반대로 유입이
    # 유지되는 글(keep)은 제목도 건드리지 않는다 — 어차피 실행 자체를 건너뛴다.
    if action == "title":
        title_mode = "recombine"
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
            action=action, action_reason=action_reason,
        )
    return RenewalPlan(recombine_title=recombine, image_action="new",
                       action=action, action_reason=action_reason)
