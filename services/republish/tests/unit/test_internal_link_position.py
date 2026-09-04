"""서론·본문 링크 위치 회귀 테스트.

예전에는 "헤딩 중 두 번째" 를 첫 섹션으로 봤다. 첫 헤딩이 H1 타이틀이라는
전제였는데, 본문 H1 이 제목과 겹칠 때 제거되면서(quality_gate) 그 전제가
깨졌다.

실측: 최근 30일 글 639건 중 476건(75%)에 H1 이 없었고, 그 글들은 서론
링크 앞에 H2 가 평균 0.96개 있었다 — 한 섹션씩 밀린 것이다.

**레벨로 판단하면 H1 유무와 무관하게 같은 자리에 들어간다.**
"""
from app.services.generation.internal_linker import InternalLinker

WITH_H1 = ("# 제목\n\n서론입니다.\n\n## 첫 섹션\n\n내용\n\n"
           "## 둘째 섹션\n\n내용\n\n## 마치며\n\n정리\n")
WITHOUT_H1 = "\n".join(WITH_H1.split("\n")[2:])


def _first(body: str) -> str:
    sections = InternalLinker._section_headings(body)
    return sections[0].group().strip() if sections else ""


class TestSectionDetection:
    def test_same_position_with_or_without_h1(self):
        """H1 제거 여부가 링크 위치를 바꾸면 안 된다."""
        assert _first(WITH_H1) == _first(WITHOUT_H1) == "## 첫 섹션"

    def test_h1_excluded_from_sections(self):
        """H1 은 글 타이틀이지 본문 섹션이 아니다."""
        for body in (WITH_H1, WITHOUT_H1):
            heads = InternalLinker._section_headings(body)
            assert all(not h.group().startswith("# ") for h in heads)
            assert len(heads) == 3

    def test_subheadings_do_not_shift_position(self):
        """### 하위 항목은 그 섹션의 일부다."""
        body = "서론\n\n## 첫 섹션\n\n### 하위\n\n내용\n\n## 둘째\n\n내용\n"
        assert _first(body) == "## 첫 섹션"

    def test_no_heading_returns_empty(self):
        assert InternalLinker._section_headings("헤딩 없는 글") == []

    def test_all_h1_falls_back(self):
        """비정상 구조에서도 첫 헤딩을 타이틀로 보고 나머지를 쓴다."""
        body = "# 타이틀\n\n서론\n\n# 첫 섹션\n\n내용\n"
        heads = InternalLinker._section_headings(body)
        assert len(heads) == 1 and heads[0].group().strip() == "# 첫 섹션"


class TestBothLinksAgree:
    def test_intro_and_body_use_same_rule(self):
        """따로 판단하면 두 링크가 서로 다른 섹션을 가리킨다."""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[2]
               / "app/services/generation/internal_linker.py").read_text(
            encoding="utf-8")
        # 순번 기반 판정이 남아 있으면 안 된다
        assert "headings[1].start()" not in src
        assert src.count("self._section_headings(content)") == 2


class TestConclusionRelatedness:
    """결론 링크가 관련 없는 글을 끌어오던 자리.

    결론 링크는 유사도 순으로 줄세우지 않는다 — 미색인 글을 밀어 주는
    것이 목적이라 무작위성이 필요하다. 하지만 **아무 글이나 붙이면**
    홈트 글 끝에 '일본여행 환전' 이 온다. 개수를 채우려고 무관한 글을
    끌어오면 독자에게도 검색엔진에도 손해다.
    """

    def _linker(self):
        return InternalLinker(db=None)

    def _sim(self):
        import os
        import sys

        for path in ("/app/shared", "/home/jteen/blogauto_v2/shared"):
            if os.path.exists(path) and path not in sys.path:
                sys.path.insert(0, path)
        from services.similarity_service import SimilarityService

        return SimilarityService()

    def _posts(self, *titles):
        from types import SimpleNamespace

        return [SimpleNamespace(title=t, url=f"http://x/{i}")
                for i, t in enumerate(titles)]

    def test_unrelated_posts_dropped(self):
        posts = self._posts("홈트레이닝 초보 루틴 정리",
                            "일본여행 환전 수수료 비교")
        kept = self._linker()._filter_related(
            "홈트레이닝 어깨 운동 방법", posts, self._sim())
        titles = [p.title for p in kept]
        assert "홈트레이닝 초보 루틴 정리" in titles
        assert "일본여행 환전 수수료 비교" not in titles

    def test_no_keywords_keeps_everything(self):
        """판단 근거가 없는데 막으면 결론 링크가 통째로 사라진다."""
        posts = self._posts("아무 글", "다른 글")
        assert len(self._linker()._filter_related("", posts, self._sim())) == 2

    def test_shortage_is_not_padded(self):
        """관련 글이 2개뿐이면 2개만 넣는다."""
        src = (__import__("pathlib").Path(__file__).resolve().parents[2]
               / "app/services/generation/internal_linker.py").read_text(
            encoding="utf-8")
        assert "_filter_related(current_title, remaining, sim_service)" in src
        assert "결론 링크 %d/%d — 관련 글이 부족해" in src

    def test_index_priority_kept(self):
        """미색인 글 밀어주기(S7)는 유지한다."""
        src = (__import__("pathlib").Path(__file__).resolve().parents[2]
               / "app/services/generation/internal_linker.py").read_text(
            encoding="utf-8")
        block = src[src.index("# 3. 결론 뒤 링크 삽입"):
                    src.index("link_count = len(used_urls)")]
        assert "prioritize_by_index" in block
        assert "random.shuffle(related)" in block

    def test_intro_shortage_already_handled(self):
        """서론은 2026-08-30 에 이미 fallback 을 없앴다."""
        src = (__import__("pathlib").Path(__file__).resolve().parents[2]
               / "app/services/generation/internal_linker.py").read_text(
            encoding="utf-8")
        assert "서론 링크 %d/%d — 관련 글이 부족해" in src
