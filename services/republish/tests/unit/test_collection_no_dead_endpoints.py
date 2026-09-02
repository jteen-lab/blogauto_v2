"""데이터 관리 화면이 사라진 API 를 부르지 않는지 지킨다.

배경: 저장소 일원화(alembic 062~065)로 `seed_keywords` 와
    `/data/keywords/seed*` 를 없앴는데, `collection/index.html` 에 옛
    키워드 탭 코드가 남아 페이지 진입마다 404 를 받았다. 응답이 HTML
    이라 `res.json()` 이 터지고 콘솔에 "키워드 로드 실패" 가 찍혔다.
    화면은 멀쩡해 보여서 오래 눈에 띄지 않았다.
"""
import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
APP = BASE / "app"

# 제거된 엔드포인트. 프런트가 여전히 부르면 콘솔 오류로 되돌아온다.
GONE = ("/data/keywords/seed",)


def _front_files():
    for pat in ("templates/**/*.html", "static/js/**/*.js"):
        yield from APP.glob(pat)


@pytest.mark.parametrize("path", sorted(GONE))
def test_no_frontend_calls_removed_api(path):
    hits = [f.relative_to(BASE).as_posix() for f in _front_files()
            if path in f.read_text(encoding="utf-8")]
    assert not hits, f"{path} 를 아직 부르는 파일: {hits}"


def test_router_drops_removed_column():
    """`collected_keywords.seed_keyword_id` 는 alembic 065 에서 사라졌다.

    응답 스키마에 남아 있으면 목록 조회가 통째로 500 이 된다.
    """
    src = (APP / "routers/data_keywords.py").read_text(encoding="utf-8")
    assert "seed_keyword_id" not in src

    from app.routers.data_keywords import CollectedKeywordResponse

    assert "seed_keyword_id" not in CollectedKeywordResponse.model_fields


def test_keyword_tab_delegates_to_pool_component():
    """키워드 탭은 keyword_pool.js 가 맡는다 — index.html 은 상태를 갖지 않는다."""
    src = (APP / "templates/collection/index.html").read_text(encoding="utf-8")
    assert "_keyword_pool.html" in src
    # 옛 컴포넌트 상태가 남아 있으면 죽은 함수가 다시 붙는다
    for gone in ("loadKeywords", "keywordSortField", "selectedKeywords"):
        assert not re.search(rf'\b{gone}\b', src), gone
