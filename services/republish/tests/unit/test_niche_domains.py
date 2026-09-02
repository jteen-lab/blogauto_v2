"""니치 도메인 자산 회귀 테스트(alembic 066).

URL 12만 건은 소비되지 않았다(처리율 0.02%). 남길 가치가 있는 것은
도메인 단위 정보였다. 마이그레이션은 되돌릴 수 없으므로 요약 규칙이
바뀌지 않도록 고정한다.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

BASE = Path(__file__).resolve().parents[2]


def _load():
    path = BASE / "alembic/versions/066_niche_domains.py"
    spec = importlib.util.spec_from_file_location("m066", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(engine, rows):
    """운영과 같은 모양으로 만든다 — DB server_default 없음.

    검증 DDL 에 DEFAULT 를 주면 create_all 산물과의 차이를 못 잡는다
    (마이그레이션 062 에서 실제로 당했다).
    """
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)"))
        conn.execute(sa.text(
            "CREATE TABLE modules (id INTEGER PRIMARY KEY, "
            "user_id INTEGER NOT NULL)"))
        conn.execute(sa.text("""
            CREATE TABLE collected_urls (
                id INTEGER PRIMARY KEY, url VARCHAR NOT NULL,
                domain VARCHAR NOT NULL, platform VARCHAR NOT NULL,
                search_keyword VARCHAR, search_title VARCHAR,
                title VARCHAR, created_at TIMESTAMP,
                source_module_id INTEGER)"""))
        conn.execute(sa.text("INSERT INTO users (id) VALUES (1), (2)"))
        conn.execute(sa.text(
            "INSERT INTO modules (id, user_id) VALUES (180, 2)"))
        for url, dom, plat, kw, title, mod in rows:
            conn.execute(sa.text("""
                INSERT INTO collected_urls
                  (url, domain, platform, search_keyword, title, created_at,
                   source_module_id)
                VALUES (:u,:d,:p,:k,:t,'2026-01-01 00:00:00',:m)"""),
                {"u": url, "d": dom, "p": plat, "k": kw, "t": title, "m": mod})


def _upgrade(engine, mod):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with ctx.begin_transaction():
            mod.op = Operations(ctx)
            mod.upgrade()
        conn.commit()


def _run(rows):
    mod = _load()
    engine = sa.create_engine("sqlite://")
    _fixture(engine, rows)
    _upgrade(engine, mod)
    with engine.connect() as conn:
        out = conn.execute(sa.text(
            "SELECT user_id, domain, platform, url_count, sample_titles, "
            "top_keywords FROM niche_domains ORDER BY domain")).fetchall()
        left = conn.execute(
            sa.text("SELECT count(*) FROM collected_urls")).scalar()
    return out, left, engine, mod


def test_summarises_by_domain():
    rows = [(f"https://a.com/{i}", "a.com", "tistory", "전기기사",
             f"전기기사 실기 {i}", 180) for i in range(50)]
    rows += [("https://b.com/1", "b.com", "unknown", "컴활", "컴활 후기", 180)]
    out, left, _, _ = _run(rows)

    assert len(out) == 2
    a = [r for r in out if r.domain == "a.com"][0]
    assert a.url_count == 50
    assert left == 0, "원본 URL 이 남으면 요약한 의미가 없다"


def test_sample_titles_are_capped():
    mod = _load()
    rows = [(f"https://a.com/{i}", "a.com", "tistory", "전기기사",
             f"제목 {i}", 180) for i in range(100)]
    out, _, _, _ = _run(rows)
    titles = out[0].sample_titles.split("\n")
    assert len(titles) == mod.SAMPLE_TITLES, "샘플이 무한정 늘면 요약이 아니다"


def test_owner_from_module():
    """소유자는 source_module_id → modules 로 역추적한다."""
    rows = [("https://a.com/1", "a.com", "tistory", "kw", "t", 180)]
    out, _, _, _ = _run(rows)
    assert out[0].user_id == 2, "모듈 소유자에게 귀속돼야 한다"


def test_legacy_rows_fall_back_to_first_user():
    """모듈이 없는 레거시 행은 가장 오래된 사용자에게 준다."""
    rows = [("https://a.com/1", "a.com", "tistory", None, None, None)]
    out, _, _, _ = _run(rows)
    assert out[0].user_id == 1
    assert out[0].sample_titles is None


def test_idempotent():
    """두 번 돌려도 깨지지 않는다."""
    rows = [("https://a.com/1", "a.com", "tistory", "kw", "t", 180)]
    _, _, engine, mod = _run(rows)
    _upgrade(engine, mod)
    with engine.connect() as conn:
        n = conn.execute(sa.text("SELECT count(*) FROM niche_domains")).scalar()
    assert n == 1


def test_model_splits_samples():
    from app.models.niche_domain import NicheDomain

    row = NicheDomain(sample_titles="가\n나\n", top_keywords="키워드")
    assert row.titles() == ["가", "나"]
    assert row.keywords() == ["키워드"]


def test_router_registered():
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/v1/data/domains" in paths
    assert "/api/v1/data/domains/stats" in paths


def test_collection_tab_replaced():
    """옛 URL 탭은 사라지고 도메인 탭이 들어왔다."""
    src = (BASE / "app/templates/collection/index.html").read_text(
        encoding="utf-8")
    assert "_niche_domains.html" in src
    assert "_urls.html" not in src
    assert "loadUrls" not in src, "죽은 URL 함수가 남으면 404 를 부른다"
