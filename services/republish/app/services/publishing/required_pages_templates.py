"""애드센스 필수 페이지 4종 템플릿 (F1).

개인정보처리방침/이용약관/소개/문의 페이지의 HTML 본문을 블로그별
변수(이름/URL/저자 프로필/연락처)로 치환해 생성한다. 발행 자체는
required_pages_service.py가 담당하며, 이 모듈은 순수 템플릿 렌더링만 한다.

설계 문서: docs/flowcharts/adsense_sprint1_p1.md - F1
"""
from datetime import date
from typing import Any, Dict, Tuple

from ...models.blog import Blog

REQUIRED_PAGE_TYPES = ("privacy", "terms", "about", "contact")


def build_required_pages(
    blog: Blog,
    owner_email: str,
) -> Dict[str, Tuple[str, str]]:
    """4종 필수 페이지의 (제목, HTML 본문)을 생성한다.

    Args:
        blog: 대상 블로그 (name, url 사용)
        owner_email: 문의 페이지에 노출할 연락처 (블로그 소유자 이메일)

    Returns:
        {page_type: (title, html)} — page_type은 REQUIRED_PAGE_TYPES 값
    """
    profile = blog.author_profile or {}
    ctx = {
        "blog_name": blog.name,
        "blog_url": blog.url,
        "operator": profile.get("name") or blog.name,
        "contact_email": owner_email,
        "today": date.today().isoformat(),
    }
    return {
        "privacy": _privacy_page(ctx),
        "terms": _terms_page(ctx),
        "about": _about_page(ctx, profile),
        "contact": _contact_page(ctx),
    }


def _privacy_page(ctx: Dict[str, str]) -> Tuple[str, str]:
    """개인정보처리방침 페이지."""
    html = f"""
<h2>개인정보처리방침</h2>
<p>{ctx['blog_name']}("{ctx['blog_url']}", 이하 "본 사이트")는 이용자의 개인정보를
소중히 여기며 관련 법령을 준수합니다.</p>
<h3>1. 수집하는 정보</h3>
<p>본 사이트는 별도의 회원가입 절차 없이 운영되며, 방문 시 광고 서비스(Google
AdSense 등) 제공을 위해 쿠키·기기 정보 등이 자동으로 수집될 수 있습니다.</p>
<h3>2. 광고 서비스(Google AdSense)</h3>
<p>본 사이트는 Google을 포함한 제3자 광고 사업자가 쿠키를 사용해 이용자의
방문 이력을 기반으로 광고를 게재할 수 있습니다. 이용자는 Google 광고 설정
페이지에서 맞춤 광고를 비활성화할 수 있습니다.</p>
<h3>3. 문의</h3>
<p>개인정보 관련 문의는 <a href="mailto:{ctx['contact_email']}">{ctx['contact_email']}</a>
로 연락 바랍니다.</p>
<p>최종 수정일: {ctx['today']}</p>
""".strip()
    return "개인정보처리방침", html


def _terms_page(ctx: Dict[str, str]) -> Tuple[str, str]:
    """이용약관 페이지."""
    html = f"""
<h2>이용약관</h2>
<p>본 약관은 {ctx['blog_name']}("{ctx['blog_url']}")이 제공하는 콘텐츠 이용에
관한 조건을 규정합니다.</p>
<h3>1. 콘텐츠 이용</h3>
<p>본 사이트의 게시물은 정보 제공 목적으로 작성되며, 무단 복제 및 재배포를
금지합니다.</p>
<h3>2. 책임의 한계</h3>
<p>본 사이트는 게시된 정보의 정확성을 위해 노력하나, 정보 이용으로 발생한
손해에 대해 법적 책임을 지지 않습니다.</p>
<h3>3. 약관 변경</h3>
<p>본 약관은 운영자의 판단에 따라 사전 고지 없이 변경될 수 있습니다.</p>
<p>최종 수정일: {ctx['today']}</p>
""".strip()
    return "이용약관", html


def _about_page(ctx: Dict[str, str], profile: Dict[str, Any]) -> Tuple[str, str]:
    """소개(About) 페이지 — author_profile이 있으면 저자 소개를 포함(F2 연동)."""
    bio = profile.get("bio")
    expertise = profile.get("expertise")
    author_block = ""
    if bio or expertise:
        author_block = "<h3>운영자 소개</h3>"
        if bio:
            author_block += f"<p>{bio}</p>"
        if expertise:
            author_block += f"<p><strong>전문 분야:</strong> {expertise}</p>"
    html = f"""
<h2>{ctx['blog_name']} 소개</h2>
<p>{ctx['blog_name']}은(는) 방문자에게 유용한 정보를 전달하기 위해 운영되는
블로그입니다. 콘텐츠는 운영자({ctx['operator']})의 검수를 거쳐 발행됩니다.</p>
{author_block}
<p>문의: <a href="mailto:{ctx['contact_email']}">{ctx['contact_email']}</a></p>
""".strip()
    return "소개", html


def _contact_page(ctx: Dict[str, str]) -> Tuple[str, str]:
    """문의(Contact) 페이지."""
    html = f"""
<h2>문의하기</h2>
<p>{ctx['blog_name']} 관련 문의사항은 아래 이메일로 연락 주시기 바랍니다.</p>
<p><strong>이메일:</strong>
<a href="mailto:{ctx['contact_email']}">{ctx['contact_email']}</a></p>
<p>운영자: {ctx['operator']}</p>
""".strip()
    return "문의", html
