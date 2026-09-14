"""작업대 — 리허설 세션과 실행 가드."""
import pytest

from app.services.workbench import capture as C
from app.services.workbench.runner import EXCLUDED, WorkbenchRunner
from app.services.workbench.session_guard import rehearse


class FakeInner:
    def __init__(self):
        self.flushes = 0
        self.rollbacks = 0
        self.commits = 0
        self.added = []

    async def flush(self):
        self.flushes += 1

    async def rollback(self):
        self.rollbacks += 1

    async def commit(self):
        self.commits += 1

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
class TestRehearsalSession:
    async def test_커밋은_flush로_보류된다(self):
        inner = FakeInner()
        rs = rehearse(inner)
        await rs.commit()
        await rs.commit()
        assert inner.commits == 0          # 진짜 커밋은 한 번도 안 감
        assert inner.flushes == 2
        assert rs.commit_calls == 2

    async def test_폐기하면_전부_되돌린다(self):
        inner = FakeInner()
        rs = rehearse(inner)
        await rs.commit()
        await rs.discard()
        assert inner.rollbacks == 1
        assert inner.commits == 0

    async def test_다른_동작은_그대로_위임한다(self):
        inner = FakeInner()
        rs = rehearse(inner)
        rs.add("행")
        await rs.flush()
        assert inner.added == ["행"]
        assert inner.flushes == 1


class FakeDB:
    """runner 가드 검증용 — get 만 흉내낸다."""

    def __init__(self, module=None):
        self._module = module

    async def get(self, model, pk):
        return self._module


@pytest.mark.asyncio
class TestRunnerGuards:
    async def test_되돌릴_수_없는_모듈은_거부한다(self):
        runner = WorkbenchRunner(FakeDB(), user_id=1)
        for kind in EXCLUDED:
            got = await runner.run(kind, module_id=1)
            assert not got.success
            assert "지원하지 않" in got.message

    async def test_모르는_타입은_거부한다(self):
        got = await WorkbenchRunner(FakeDB(), 1).run("정체불명", module_id=1)
        assert not got.success

    async def test_모듈이_없으면_사유를_남긴다(self):
        got = await WorkbenchRunner(FakeDB(module=None), 1).run(
            "keyword", module_id=99)
        assert not got.success
        assert "찾을 수 없습니다" in got.message


class TestCaptureSummarize:
    def test_전체_채택_제외를_센다(self):
        captured = {"total": 3, "items": [
            {"excluded": False}, {"excluded": True}, {"excluded": False}]}
        got = C.summarize(captured)
        assert got == {"total": 3, "kept": 2, "excluded": 1}

    def test_생성_결과는_그대로_항목이_된다(self):
        class R:
            success = True
            recombined_title = "제목"
            final_html = "<p>본문</p>"
            image_url = "img"
            reference_count = 3
            content_length = 100
            body_chars = 80
        got = C.capture_generation(R())
        assert got["total"] == 1
        assert got["items"][0]["text"] == "제목"
        assert not got["items"][0]["excluded"]

    def test_표시_상한을_넘으면_자른다(self):
        rows = [{"excluded": False}] * (C.DISPLAY_LIMIT + 20)
        got = C._clip(rows)
        assert got["total"] == C.DISPLAY_LIMIT + 20
        assert len(got["items"]) == C.DISPLAY_LIMIT
        assert got["clipped"] == 20
