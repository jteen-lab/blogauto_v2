"""복사용 HTML — 로컬 이미지를 올려 절대주소로 바꾼다(서버 쪽)."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from types import SimpleNamespace

from app.core.database import Base
from app.models.blog import Blog, BlogPlatform
from app.models.user import User
from app.services.workbench import copy_html as svc

LOCAL = "/static/generated/images/21_1789.png"
REMOTE = "https://i.ibb.co/abc/image.webp"
BODY = (f'<div class="separator"><img src="{LOCAL}" alt="제목"></div>'
        f'<p>본문</p><a href="{LOCAL}">같은 파일</a>')


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Base.metadata.tables[n] for n in ("users", "blogs")]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


async def _seed(db):
    me = User(email="me@x.com", hashed_password="x")
    other = User(email="o@x.com", hashed_password="x")
    db.add_all([me, other]); await db.flush()
    mine = Blog(user_id=me.id, name="이사노트", url="https://a",
                platform=BlogPlatform.BLOGGER)
    theirs = Blog(user_id=other.id, name="남의것", url="https://b",
                  platform=BlogPlatform.BLOGGER)
    db.add_all([mine, theirs]); await db.commit()
    return me, mine, theirs


class _Uploader:
    """업로드 흉내. 몇 번 불렸는지 센다."""

    def __init__(self, ok=True, url=REMOTE, error=""):
        self.ok, self.url, self.error, self.calls = ok, url, error, []

    async def upload_image(self, blog, image_path, title=""):
        self.calls.append((blog.id, image_path, title))
        return SimpleNamespace(success=self.ok, platform_url=self.url,
                               error=self.error, media_id=None)


@pytest.fixture
def patched(monkeypatch):
    """파일이 있다고 보고, 업로더를 흉내로 바꾼다."""
    def _apply(uploader, path="/tmp/a.png"):
        monkeypatch.setattr(svc, "resolve_image_path", lambda url: path)
        monkeypatch.setattr(svc, "ImageUploader", lambda: uploader)
        return uploader
    return _apply


class TestLocalImages:
    def test_같은_파일은_한_번만_센다(self):
        assert svc.local_images(BODY) == [LOCAL]

    def test_원격_주소는_건드리지_않는다(self):
        assert svc.local_images(f'<img src="{REMOTE}">') == []


@pytest.mark.asyncio
class TestAbsolutize:
    async def test_로컬_이미지를_올려_바꾼다(self, db, patched):
        me, blog, _ = await _seed(db)
        up = patched(_Uploader())
        got = await svc.absolutize(db, me.id, blog.id, BODY, title="제목")
        assert got["error"] is None
        assert got["uploaded"] == 1 and got["total"] == 1
        assert LOCAL not in got["html"]
        # src 와 href 두 자리 모두 바뀐다
        assert got["html"].count(REMOTE) == 2
        assert len(up.calls) == 1, "같은 파일을 두 번 올리지 않는다"

    async def test_원격_주소만_있으면_아무것도_하지_않는다(self, db, patched):
        me, blog, _ = await _seed(db)
        up = patched(_Uploader())
        body = f'<img src="{REMOTE}">'
        got = await svc.absolutize(db, me.id, blog.id, body)
        assert got == {"html": body, "uploaded": 0, "total": 0, "error": None}
        assert up.calls == []

    async def test_블로그를_안_담으면_올릴_곳이_없다(self, db, patched):
        me, _blog, _ = await _seed(db)
        patched(_Uploader())
        got = await svc.absolutize(db, me.id, None, BODY)
        assert got["html"] == BODY and "블로그를 담아야" in got["error"]

    async def test_남의_블로그로는_올리지_않는다(self, db, patched):
        me, _blog, theirs = await _seed(db)
        up = patched(_Uploader())
        got = await svc.absolutize(db, me.id, theirs.id, BODY)
        assert "찾을 수 없습니다" in got["error"] and up.calls == []

    async def test_파일이_없으면_바꾸지_않고_알린다(self, db, monkeypatch):
        me, blog, _ = await _seed(db)
        monkeypatch.setattr(svc, "resolve_image_path", lambda url: None)
        got = await svc.absolutize(db, me.id, blog.id, BODY)
        assert got["html"] == BODY
        assert "찾을 수 없습니다" in got["error"]

    async def test_업로드_실패는_원본을_돌려준다(self, db, patched):
        """반쪽만 바뀐 본문을 붙이면 어느 이미지가 깨졌는지 알기 어렵다."""
        me, blog, _ = await _seed(db)
        patched(_Uploader(ok=False, url="", error="imgbb 키가 없습니다"))
        got = await svc.absolutize(db, me.id, blog.id, BODY)
        assert got["html"] == BODY and got["uploaded"] == 0
        assert "imgbb 키가 없습니다" in got["error"]

    async def test_예외도_원본을_돌려준다(self, db, monkeypatch):
        me, blog, _ = await _seed(db)
        monkeypatch.setattr(svc, "resolve_image_path", lambda url: "/tmp/a.png")

        class _Boom:
            async def upload_image(self, *a, **kw):
                raise RuntimeError("연결 끊김")

        monkeypatch.setattr(svc, "ImageUploader", lambda: _Boom())
        got = await svc.absolutize(db, me.id, blog.id, BODY)
        assert got["html"] == BODY and "연결 끊김" in got["error"]
