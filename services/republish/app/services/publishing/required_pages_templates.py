"""애드센스 필수 페이지 4종 템플릿 + 문체 프리셋 (F1 / 필수페이지 모듈).

개인정보처리방침/이용약관/소개/문의 페이지를 **토큰 기반 프리셋**으로 렌더한다.
프리셋 3종(표준/친근/간결) 중 선택하고, 페이지별 본문을 사용자가 직접 편집
(overrides)할 수 있다. 발행은 required_pages_service.py가 담당하며 이 모듈은
순수 렌더링만 한다.

토큰: {{blog_name}} {{blog_url}} {{operator}} {{today}} {{author_block}}
{{contact}}. `{{contact}}`는 author_profile.contact_form_url이 있으면 문의 폼
임베드, 없으면 mailto로 확장한다(동일 소유주 이메일 노출 방지).

설계: docs/plans/adsense_required_pages_module_plan.md,
docs/flowcharts/adsense_required_pages_module.md
"""
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ...models.blog import Blog

REQUIRED_PAGE_TYPES = ("privacy", "terms", "about", "contact")

DEFAULT_PRESET_CODE = "standard"


# ---------------------------------------------------------------------------
# 프리셋 정의: 각 페이지의 (title, body) 토큰 HTML
# ---------------------------------------------------------------------------
def _pages(privacy: str, terms: str, about: str, contact: str) -> Dict[str, Dict[str, str]]:
    """4종 페이지 body를 표준 제목과 묶어 반환(about 제목만 블로그명 포함)."""
    return {
        "privacy": {"title": "개인정보처리방침", "body": privacy.strip()},
        "terms": {"title": "이용약관", "body": terms.strip()},
        "about": {"title": "{{blog_name}} 소개", "body": about.strip()},
        "contact": {"title": "문의", "body": contact.strip()},
    }


_STANDARD = _pages(
    privacy="""
<h2>개인정보처리방침</h2>
<p>{{blog_name}}("{{blog_url}}", 이하 "본 사이트")는 이용자의 개인정보를 소중히 여기며
관련 법령을 준수합니다.</p>
<h3>1. 수집하는 정보</h3>
<p>본 사이트는 별도의 회원가입 절차 없이 운영되며, 방문 시 광고 서비스(Google
AdSense 등) 제공을 위해 쿠키·기기 정보 등이 자동으로 수집될 수 있습니다.</p>
<h3>2. 광고 서비스(Google AdSense)</h3>
<p>본 사이트는 Google을 포함한 제3자 광고 사업자가 쿠키를 사용해 이용자의 방문
이력을 기반으로 광고를 게재할 수 있습니다. 이용자는 Google 광고 설정 페이지에서
맞춤 광고를 비활성화할 수 있습니다.</p>
<h3>3. 문의</h3>
<p>개인정보 관련 문의는 아래 채널로 연락 바랍니다.</p>
{{contact}}
<p>최종 수정일: {{today}}</p>
""",
    terms="""
<h2>이용약관</h2>
<p>본 약관은 {{blog_name}}("{{blog_url}}")이 제공하는 콘텐츠 이용에 관한 조건을
규정합니다.</p>
<h3>1. 콘텐츠 이용</h3>
<p>본 사이트의 게시물은 정보 제공 목적으로 작성되며, 무단 복제 및 재배포를
금지합니다.</p>
<h3>2. 책임의 한계</h3>
<p>본 사이트는 게시된 정보의 정확성을 위해 노력하나, 정보 이용으로 발생한 손해에
대해 법적 책임을 지지 않습니다.</p>
<h3>3. 약관 변경</h3>
<p>본 약관은 운영자의 판단에 따라 사전 고지 없이 변경될 수 있습니다.</p>
<p>최종 수정일: {{today}}</p>
""",
    about="""
<h2>{{blog_name}} 소개</h2>
<p>{{blog_name}}은(는) 방문자에게 유용한 정보를 전달하기 위해 운영되는 블로그입니다.
콘텐츠는 운영자({{operator}})의 검수를 거쳐 발행됩니다.</p>
{{author_block}}
<h3>문의</h3>
{{contact}}
""",
    contact="""
<h2>문의하기</h2>
<p>{{blog_name}} 관련 문의사항은 아래 채널로 연락 주시기 바랍니다.</p>
{{contact}}
<p>운영자: {{operator}}</p>
""",
)

_FRIENDLY = _pages(
    privacy="""
<h2>개인정보처리방침</h2>
<p>안녕하세요, {{blog_name}}입니다. 저희는 방문해 주시는 분들의 개인정보를 무엇보다
소중하게 생각합니다.</p>
<h3>1. 어떤 정보를 모으나요?</h3>
<p>저희 블로그는 회원가입이 없어요. 다만 광고(Google AdSense 등)를 보여드리기 위해
쿠키나 기기 정보가 자동으로 수집될 수 있습니다.</p>
<h3>2. 광고 이야기</h3>
<p>Google을 비롯한 광고 파트너가 쿠키로 여러분의 방문 기록을 참고해 광고를 보여줄 수
있어요. 원치 않으시면 Google 광고 설정에서 맞춤 광고를 끄실 수 있습니다.</p>
<h3>3. 궁금한 점이 있다면</h3>
<p>개인정보와 관련해 궁금한 점은 언제든 아래로 연락 주세요.</p>
{{contact}}
<p>최종 수정일: {{today}}</p>
""",
    terms="""
<h2>이용약관</h2>
<p>{{blog_name}}에 오신 것을 환영합니다! 편하게 즐기시되 아래 내용만 기억해 주세요.</p>
<h3>1. 콘텐츠 이용</h3>
<p>저희 글은 정보를 나누려고 정성껏 쓴 것이에요. 무단으로 복사하거나 옮기는 건
삼가 주세요.</p>
<h3>2. 책임에 대해</h3>
<p>정확한 정보를 드리려 노력하지만, 정보 활용으로 생긴 손해까지 책임지긴 어렵다는 점
양해 부탁드립니다.</p>
<h3>3. 약관이 바뀔 수 있어요</h3>
<p>사정에 따라 약관이 조금씩 바뀔 수 있습니다.</p>
<p>최종 수정일: {{today}}</p>
""",
    about="""
<h2>{{blog_name}} 소개</h2>
<p>반갑습니다! {{blog_name}}은(는) 도움이 되는 이야기를 나누고 싶어 {{operator}}이(가)
직접 운영하는 블로그예요.</p>
{{author_block}}
<h3>문의</h3>
{{contact}}
""",
    contact="""
<h2>문의하기</h2>
<p>{{blog_name}}에 궁금한 점이 있으시면 편하게 연락 주세요. 최대한 빨리 답변드릴게요!</p>
{{contact}}
<p>운영자: {{operator}}</p>
""",
)

_CONCISE = _pages(
    privacy="""
<h2>개인정보처리방침</h2>
<p>{{blog_name}}({{blog_url}})의 개인정보 처리 기준입니다.</p>
<h3>수집 정보</h3>
<p>회원가입 없음. 광고(Google AdSense) 제공을 위한 쿠키·기기 정보가 자동 수집될 수
있습니다.</p>
<h3>광고</h3>
<p>제3자 광고 사업자가 쿠키로 맞춤 광고를 게재할 수 있으며, Google 광고 설정에서
비활성화할 수 있습니다.</p>
<h3>문의</h3>
{{contact}}
<p>최종 수정일: {{today}}</p>
""",
    terms="""
<h2>이용약관</h2>
<p>{{blog_name}} 이용 조건입니다.</p>
<h3>콘텐츠</h3>
<p>정보 제공 목적. 무단 복제·재배포 금지.</p>
<h3>책임</h3>
<p>정보 이용으로 발생한 손해에 책임지지 않습니다.</p>
<h3>변경</h3>
<p>약관은 사전 고지 없이 변경될 수 있습니다.</p>
<p>최종 수정일: {{today}}</p>
""",
    about="""
<h2>{{blog_name}} 소개</h2>
<p>{{blog_name}} — 운영자 {{operator}}가 검수·발행하는 정보 블로그입니다.</p>
{{author_block}}
<h3>문의</h3>
{{contact}}
""",
    contact="""
<h2>문의하기</h2>
<p>문의는 아래 채널로 연락 주세요.</p>
{{contact}}
<p>운영자: {{operator}}</p>
""",
)

PRESETS: List[Dict[str, Any]] = [
    {"code": "standard", "name": "표준(공식체)",
     "description": "격식 있는 표준 문체", "pages": _STANDARD},
    {"code": "friendly", "name": "친근체",
     "description": "부드럽고 친근한 말투", "pages": _FRIENDLY},
    {"code": "concise", "name": "간결체",
     "description": "짧고 핵심만", "pages": _CONCISE},
]


def get_preset(code: Optional[str]) -> Dict[str, Any]:
    """코드로 프리셋 조회(없으면 표준)."""
    for p in PRESETS:
        if p["code"] == code:
            return p
    return PRESETS[0]


def list_presets() -> List[Dict[str, Any]]:
    """UI용 프리셋 목록(코드·이름·설명 + 페이지별 기본 제목/본문 = 편집창 프리필)."""
    return [
        {
            "code": p["code"],
            "name": p["name"],
            "description": p["description"],
            "pages": {
                pt: {"title": p["pages"][pt]["title"], "body": p["pages"][pt]["body"]}
                for pt in REQUIRED_PAGE_TYPES
            },
        }
        for p in PRESETS
    ]


def _contact_section(ctx: Dict[str, str]) -> str:
    """연락 채널 HTML — 문의 폼 임베드(있으면) 또는 mailto(폴백)."""
    form_url = ctx.get("contact_form_url")
    if form_url:
        return (
            f'<p><a href="{form_url}" target="_blank" rel="noopener noreferrer">'
            f"문의 폼 바로가기</a></p>\n"
            f'<iframe src="{form_url}" width="100%" height="600" style="border:0;'
            f'max-width:640px;" title="문의 폼">로딩 중입니다…</iframe>'
        )
    return (
        f'<p><strong>이메일:</strong> '
        f'<a href="mailto:{ctx["contact_email"]}">{ctx["contact_email"]}</a></p>'
    )


def _author_block(profile: Dict[str, Any]) -> str:
    """운영자 소개 블록(bio/expertise 있으면) 또는 빈 문자열."""
    bio = profile.get("bio")
    expertise = profile.get("expertise")
    if not (bio or expertise):
        return ""
    block = "<h3>운영자 소개</h3>"
    if bio:
        block += f"<p>{bio}</p>"
    if expertise:
        block += f"<p><strong>전문 분야:</strong> {expertise}</p>"
    return block


def render_tokens(text: str, ctx: Dict[str, str]) -> str:
    """본문/제목의 {{토큰}}을 컨텍스트 값으로 치환(사용자 편집 본문에도 동일 적용)."""
    result = text
    for key, value in ctx.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def build_required_pages(
    blog: Blog,
    owner_email: str,
    preset_code: Optional[str] = None,
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Tuple[str, str]]:
    """4종 필수 페이지의 (제목, HTML 본문)을 생성한다.

    Args:
        blog: 대상 블로그(name/url/author_profile 사용)
        owner_email: contact_form_url 미설정 시 문의 채널에 노출할 이메일
        preset_code: 문체 프리셋 코드(없으면 표준)
        overrides: {page_type: 편집된 body} — 있으면 프리셋 본문 대신 사용

    Returns:
        {page_type: (title, html)} — page_type은 REQUIRED_PAGE_TYPES 값
    """
    profile = blog.author_profile or {}
    overrides = overrides or {}
    ctx: Dict[str, str] = {
        "blog_name": blog.name,
        "blog_url": blog.url or "",
        "operator": profile.get("name") or blog.name,
        "contact_email": owner_email,
        "contact_form_url": profile.get("contact_form_url") or "",
        "today": date.today().isoformat(),
    }
    # 파생 토큰(컨텍스트 값에 의존)
    ctx["author_block"] = _author_block(profile)
    ctx["contact"] = _contact_section(ctx)

    preset = get_preset(preset_code)
    pages: Dict[str, Tuple[str, str]] = {}
    for page_type in REQUIRED_PAGE_TYPES:
        spec = preset["pages"][page_type]
        body_src = overrides.get(page_type) or spec["body"]
        title = render_tokens(spec["title"], ctx)
        html = render_tokens(body_src, ctx).strip()
        pages[page_type] = (title, html)
    return pages
