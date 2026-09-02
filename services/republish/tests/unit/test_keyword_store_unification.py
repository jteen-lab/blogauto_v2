"""S1 — 키워드 저장소 일원화 회귀 테스트.

배경(docs/plans/keyword_pipeline_restructure_review.md §6):
    같은 개념이 세 테이블에 나뉘어 있었다. seed_keywords 에는 지표 컬럼이
    아예 없어 데이터 관리 키워드 탭이 검색량조차 보여줄 수 없었다.
    지표가 이미 있는 keyword_candidates 를 정본으로 삼는다.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.keyword_candidate import KeywordCandidate
from app.services.keyword_lab import legacy_bridge

BASE = Path(__file__).resolve().parents[2]


class TestCanonicalColumns:
    """운영 상태 컬럼이 정본으로 넘어왔다."""

    @pytest.mark.parametrize("name", [
        "is_active", "use_count", "last_used_at", "priority",
        "legacy_seed_id",
    ])
    def test_column_exists(self, name):
        assert name in KeywordCandidate.__table__.columns

    def test_metrics_stay(self):
        # 일원화의 이유 자체가 지표다. 같이 있어야 의미가 있다
        for name in ("search_volume", "monthly_pub_count", "saturation",
                     "verdict", "intent", "cluster_id", "perf_score"):
            assert name in KeywordCandidate.__table__.columns


class TestMigration:
    def _src(self):
        return (BASE / "alembic/versions/062_unify_keyword_store.py").read_text(
            encoding="utf-8")

    def test_global_pool_uniqueness(self):
        src = self._src()
        # (user_id, blog_id, keyword) 유니크는 blog_id 가 NULL 이면
        # NULL 끼리 서로 다르다고 보아 중복을 못 막는다
        assert "uq_keyword_candidate_global" in src
        assert "blog IS NULL" in src or "blog_id IS NULL" in src

    def test_skips_existing_case_insensitively(self):
        src = self._src()
        assert "lower(k.keyword) = lower(s.keyword)" in src

    def test_keeps_legacy_table(self):
        # 기존 수집 모듈이 아직 seed_keywords 를 쓴다
        src = self._src()
        assert "DROP TABLE" not in src.upper()
        assert "지우지 않는다" in src

    def test_downgrade_only_removes_migrated(self):
        src = self._src()
        assert "legacy_seed_id IS NOT NULL" in src

    def test_marks_origin(self):
        assert 'LEGACY_SOURCE = "legacy_seed"' in self._src()


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    async def execute(self, *a, **k):
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)


class TestBridge:
    """전환기 이중 기록 — 새 키워드가 화면에서 빠지지 않게."""

    @pytest.mark.asyncio
    async def test_writes_when_absent(self):
        db = _FakeDb(existing=None)
        assert await legacy_bridge.mirror_keyword(db, "전기기사", "google_trends")
        row = db.added[0]
        assert row.keyword == "전기기사"
        assert row.blog_id is None          # 전역 풀
        assert row.verdict == "pending"     # 아직 재지 않음
        assert row.source == "google_trends"

    @pytest.mark.asyncio
    async def test_skips_when_present(self):
        db = _FakeDb(existing=(1,))
        assert await legacy_bridge.mirror_keyword(db, "전기기사", "x") is False
        assert db.added == []

    @pytest.mark.asyncio
    async def test_ignores_blank(self):
        db = _FakeDb(existing=None)
        assert await legacy_bridge.mirror_keyword(db, "   ", "x") is False
        assert db.added == []

    @pytest.mark.asyncio
    async def test_carries_category(self):
        db = _FakeDb(existing=None)
        await legacy_bridge.mirror_keyword(db, "전기기사", "x",
                                           topic_id=3, subtopic_id=7)
        assert (db.added[0].topic_id, db.added[0].subtopic_id) == (3, 7)

    @pytest.mark.asyncio
    async def test_long_source_is_trimmed(self):
        db = _FakeDb(existing=None)
        await legacy_bridge.mirror_keyword(db, "가나다", "x" * 80)
        assert len(db.added[0].source) <= 30


class TestCollectorHook:
    """기존 수집 모듈이 정본에도 적는다."""

    def _src(self):
        return (BASE / "app/services/keyword_collector_service.py").read_text(
            encoding="utf-8")

    def test_bridge_called(self):
        src = self._src()
        assert "from .keyword_lab.legacy_bridge import mirror_keyword" in src
        assert "await mirror_keyword(" in src

    def test_failure_does_not_break_collection(self):
        # 다리가 막혀도 기존 수집은 계속돼야 한다
        src = self._src()
        assert "[BRIDGE] 정본 기록 실패" in src

    def test_still_writes_legacy_table(self):
        # 전환기에는 양쪽에 적는다
        assert "self.db.add(new_keyword)" in self._src()
