"""저자성(E-E-A-T) 바이라인/편집감독 문구 주입 (F2).

블로그에 author_profile(이름)이 설정된 경우에만 본문 하단에 저자 바이라인과
편집 감독 문구를 주입한다. 미설정 블로그는 기존 동작과 동일(주입 없음) —
옵트인 방식이라 운영 중인 기존 발행 흐름에는 영향이 없다.

설계 문서: docs/flowcharts/adsense_sprint1_p1.md - F2
"""
from ...models.blog import Blog

EDITORIAL_NOTICE = (
    '<p style="font-size:0.85em;color:#777;">'
    "본 콘텐츠는 사람이 검수·편집합니다.</p>"
)


def inject_author_signal(html: str, blog: Blog) -> str:
    """author_profile이 설정된 블로그의 본문 하단에 저자 바이라인을 추가한다.

    Args:
        html: 치환/이미지 처리까지 끝난 최종 본문 HTML
        blog: 발행 대상 블로그

    Returns:
        author_profile.name이 없으면 원본 html 그대로, 있으면 바이라인 블록이
        추가된 HTML
    """
    profile = blog.author_profile or {}
    name = (profile.get("name") or "").strip()
    if not name:
        return html

    bio = (profile.get("bio") or "").strip()
    expertise = (profile.get("expertise") or "").strip()

    byline = f"<p><strong>글쓴이: {name}</strong>"
    if expertise:
        byline += f" ({expertise})"
    byline += "</p>"

    block = f"<hr>{byline}"
    if bio:
        block += f"<p>{bio}</p>"
    block += EDITORIAL_NOTICE

    return f"{html}\n{block}"
