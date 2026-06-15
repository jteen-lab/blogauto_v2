"""임시/정식 제목 단어 치환 미리보기 계산 테스트.

_build_replace_previews 의 핵심 계약 검증:
- temp(임시): existing_titles 빈 집합 → 결과가 기존 제목과 같아도 치환(중복 허용)
- main(정식): existing_titles 채움 → 중복 결과 스킵(uq 제약 보호)
- preview/apply 일관성(동일 existing_titles면 동일 결과)
"""
from types import SimpleNamespace

from app.routers.data_titles import _build_replace_previews


def _t(id_, title):
    return SimpleNamespace(id=id_, title=title)


def test_temp_replaces_even_if_result_duplicates_existing():
    """임시제목: existing 비어있으면 결과 중복이어도 모두 치환."""
    titles = [_t(1, "서울 포장이사 비용"), _t(2, "부산 포장이사 비용")]
    previews, dup, empty = _build_replace_previews(
        titles, "포장이사", "이사", False, set(),
    )
    assert len(previews) == 2
    assert dup == 0 and empty == 0
    assert previews[0]["replaced"] == "서울 이사 비용"


def test_main_skips_when_result_exists():
    """정식제목: 결과가 기존 제목 집합에 있으면 중복 스킵."""
    titles = [_t(1, "서울 포장이사 비용")]
    existing = {"서울 이사 비용"}  # 치환 결과가 이미 존재
    previews, dup, empty = _build_replace_previews(
        titles, "포장이사", "이사", False, existing,
    )
    assert len(previews) == 0
    assert dup == 1


def test_intra_batch_duplicate_skipped():
    """같은 배치에서 두 제목이 동일 결과면 두 번째는 스킵."""
    titles = [_t(1, "이사 안내 A"), _t(2, "이사 안내 A")]
    previews, dup, empty = _build_replace_previews(
        titles, "안내 A", "안내 B", False, set(),
    )
    assert len(previews) == 1
    assert dup == 1


def test_unchanged_when_find_equals_replace():
    """find==replace 등 변화 없으면 미리보기에서 제외(스킵)."""
    titles = [_t(1, "이사 비용 안내")]
    previews, dup, empty = _build_replace_previews(
        titles, "이사", "이사", False, set(),
    )
    assert len(previews) == 0
    assert dup == 0 and empty == 0


def test_empty_result_skipped():
    """치환 결과가 2자 미만이면 빈 제목으로 스킵."""
    titles = [_t(1, "이사")]
    previews, dup, empty = _build_replace_previews(
        titles, "이사", "", False, set(),
    )
    assert len(previews) == 0
    assert empty == 1


def test_delete_word_replaces():
    """치환어 빈 문자열(삭제)도 정상 치환."""
    titles = [_t(1, "서울 포장이사 비용 견적")]
    previews, dup, empty = _build_replace_previews(
        titles, "견적", "", False, set(),
    )
    assert len(previews) == 1
    assert previews[0]["replaced"] == "서울 포장이사 비용"
