"""표지 이미지가 두 번 들어가던 문제.

2026-09-24 실측(이사노트·수작남): 모듈 테스터에서 조립해 반영한 글은
본문 맨 앞에 표지가 들어 있는데, 발행 파이프라인이 대표 이미지를 또
얹어 **같은 이미지가 둘 연속으로** 발행됐다.

    저장된 본문   [고지문][표지(/static/...)][본문]
    발행된 글     [표지(ibb)][고지문][표지(ibb)][본문]   ← 둘 연속

자동 발행 글은 본문에 표지가 없어(대표 이미지만) 멀쩡했다 — 그래서
모듈 테스터로 만든 블로그에서만 나타났다.
"""
import pytest

from app.services.publishing.html_injector import HtmlInjector

LOCAL = "/static/generated/images/21_1789996279_4c62542b.png"
REMOTE = "https://i.ibb.co/MxDVZ4MF/7.webp"
BODY_WITH_COVER = (
    '<p style="font-size:15px;color:#8a8a8a;">이 포스팅은 애드릭스 '
    '수익을 위해 작성되었습니다.</p>\n'
    '<div class="separator" style="clear:both;text-align:center;">\n'
    f'    <img border="0" src="{LOCAL}" alt="제목" '
    'style="max-width:100%;height:auto;">\n'
    '</div>\n<br/>\n<p>본문입니다.</p>'
)
PLAIN_BODY = "<p>본문입니다.</p>\n<h2>소제목</h2>\n<p>더 있습니다.</p>"


def _imgs(html: str) -> int:
    return html.count("<img")


class TestHasImage:
    def test_로컬_경로로_들어_있어도_찾는다(self):
        """발행 전 본문에는 아직 로컬 경로로 들어 있다."""
        assert HtmlInjector().has_image(BODY_WITH_COVER, REMOTE, LOCAL) is True

    def test_올린_주소로_들어_있어도_찾는다(self):
        body = BODY_WITH_COVER.replace(LOCAL, REMOTE)
        assert HtmlInjector().has_image(body, REMOTE, None) is True

    def test_이미지가_없으면_없다고_한다(self):
        assert HtmlInjector().has_image(PLAIN_BODY, REMOTE, LOCAL) is False

    def test_주소만_글자로_있고_img_가_없으면_아니다(self):
        """본문에 주소만 적혀 있는 것은 이미지가 아니다."""
        assert HtmlInjector().has_image(f"<p>{REMOTE}</p>", REMOTE) is False


class TestInjectFeaturedImage:
    @pytest.mark.parametrize("platform", ["blogger", "wordpress"])
    def test_본문에_이미_있으면_넣지_않는다(self, platform):
        out = HtmlInjector().inject_featured_image(
            html=BODY_WITH_COVER, image_url=REMOTE, title="제목",
            platform=platform, source_url=LOCAL)
        assert out == BODY_WITH_COVER
        assert _imgs(out) == 1

    @pytest.mark.parametrize("platform", ["blogger", "wordpress"])
    def test_없으면_예전처럼_맨_위에_넣는다(self, platform):
        out = HtmlInjector().inject_featured_image(
            html=PLAIN_BODY, image_url=REMOTE, title="제목",
            platform=platform, source_url=LOCAL)
        assert _imgs(out) == 1
        assert out.index("<img") < out.index("<p>본문입니다.</p>")

    def test_같은_주소가_이미_있으면_넣지_않는다(self):
        """재발행(리뉴얼)은 기존 주소를 그대로 다시 주입한다."""
        body = BODY_WITH_COVER.replace(LOCAL, REMOTE)
        out = HtmlInjector().inject_featured_image(
            html=body, image_url=REMOTE, title="제목", platform="blogger")
        assert _imgs(out) == 1

    def test_주소가_없으면_본문_그대로(self):
        assert HtmlInjector().inject_featured_image(
            html=PLAIN_BODY, image_url="") == PLAIN_BODY


class TestPipelineSkipsUpload:
    """올린 다음 버리면 imgbb 호출만 낭비된다 — 올리기 전에 가른다."""

    def test_파이프라인이_업로드_전에_본문을_본다(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[2]
               / "app/services/publishing/publisher_pipeline.py"
               ).read_text(encoding="utf-8")
        head = src[:src.index("# Step 2: HTML 가공")]
        assert "has_image(" in head, "대표이미지 업로드 전에 본문을 봐야 한다"
        assert "source_url=post.image_url" in src, \
            "주입 단계도 로컬 경로 형태를 함께 봐야 한다"


class TestMissingFileStillBlocksPublish:
    """표지 파일이 사라진 글은 그냥 나가면 안 된다.

    본문 쪽 이미지는 발행 직전 조용히 지워진다(파일이 없으면). 그래서
    업로드를 건너뛰면 **이미지 없는 글**이 나간다. 파일이 있을 때만
    건너뛴다 — 없으면 업로드를 태워 '이미지 없는 발행 금지' 관문에 걸린다.
    """

    def test_파일이_있어야_건너뛴다(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[2]
               / "app/services/publishing/publisher_pipeline.py"
               ).read_text(encoding="utf-8")
        head = src[:src.index("# Step 2: HTML 가공")]
        assert "resolve_image_path" in head, \
            "본문에 있다는 것만으로 건너뛰면 이미지 없는 글이 나간다"
