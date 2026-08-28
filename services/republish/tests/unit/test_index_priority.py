"""S7 색인 우선순위 테스트.

결론 링크는 원래 순수 랜덤이었다. 무작위성을 유지한 채 미색인 글만 앞으로 당긴다.
"""
from types import SimpleNamespace

from app.models.search_visibility import IX_INDEXED, IX_NOT_INDEXED, IX_UNKNOWN
from app.services.generation import index_priority as ip


def _post(url):
    return SimpleNamespace(url=url, title=url)


def test_not_indexed_comes_first():
    posts = [_post("a"), _post("b"), _post("c")]
    states = {"a": IX_INDEXED, "b": IX_NOT_INDEXED, "c": IX_UNKNOWN}
    ordered = [p.url for p in ip.sort_by_index_priority(posts, states)]
    assert ordered == ["b", "c", "a"]


def test_stable_within_same_priority():
    """같은 우선순위면 입력 순서를 보존한다 — 앞서 섞은 무작위성이 유지된다."""
    posts = [_post("x"), _post("y"), _post("z")]
    states = {"x": IX_NOT_INDEXED, "y": IX_NOT_INDEXED, "z": IX_NOT_INDEXED}
    assert [p.url for p in ip.sort_by_index_priority(posts, states)] == [
        "x", "y", "z",
    ]


def test_unknown_url_uses_default_priority():
    """원장에 없는 URL 은 미확인 취급 — 색인된 글보다는 앞이다."""
    posts = [_post("indexed"), _post("absent")]
    ordered = ip.sort_by_index_priority(posts, {"indexed": IX_INDEXED})
    assert [p.url for p in ordered] == ["absent", "indexed"]


def test_trailing_slash_is_normalized():
    posts = [_post("https://x.com/1/")]
    states = {"https://x.com/1": IX_NOT_INDEXED}
    assert ip.sort_by_index_priority(posts, states)[0].url.endswith("1/")
    assert ip.PRIORITY[IX_NOT_INDEXED] == 0


def test_error_state_ranks_above_unknown():
    posts = [_post("u"), _post("e")]
    states = {"u": IX_UNKNOWN, "e": "error"}
    assert [p.url for p in ip.sort_by_index_priority(posts, states)] == ["e", "u"]


def test_empty_list():
    assert ip.sort_by_index_priority([], {}) == []
