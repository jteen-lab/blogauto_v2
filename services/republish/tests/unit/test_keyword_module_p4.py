"""키워드 모듈 P4 — 클러스터 생산·검색 의도 테스트.

계획서: docs/plans/keyword_module_redesign_plan.md §2 B4/B6

핵심:
    키워드 1개 = 제목 1개는 대량 발행에 맞지 않는다.
    묶음 하나에서 대표 글 1편 + 곁가지 글 N편이 나온다.
    같은 주제라도 묻는 것(의도)이 다르면 다른 글이다.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.keyword_cluster import CLUSTER_NEW, CLUSTER_TITLED, KeywordCluster
from app.services.keyword_lab import clustering
from app.services.keyword_lab import intent as it
from app.services.keyword_lab.settings import KeywordModuleSettings

BASE = Path(__file__).resolve().parents[2]


def _kw(keyword, volume=100, topic=None, sub=None):
    return SimpleNamespace(keyword=keyword, search_volume=volume,
                           topic_id=topic, subtopic_id=sub)


class TestIntent:
    @pytest.mark.parametrize("keyword,expected", [
        ("전기기사 실기 방법", it.INTENT_HOWTO),
        ("에어컨 설치 비용", it.INTENT_PRICE),
        ("아이폰 vs 갤럭시", it.INTENT_COMPARE),
        ("로봇청소기 추천", it.INTENT_REVIEW),
        ("프린터 오류 해결", it.INTENT_TROUBLE),
        ("컴활 접수기간", it.INTENT_SCHEDULE),
        ("블로그 뜻", it.INTENT_INFO),
    ])
    def test_classify(self, keyword, expected):
        assert it.classify(keyword) == expected

    def test_price_wins_over_howto(self):
        # "설치 비용" 은 방법이 아니라 비용 질문이다
        assert it.classify("에어컨 설치 방법 비용") == it.INTENT_PRICE

    def test_unknown_defaults_to_info(self):
        assert it.classify("마라탕") == it.INTENT_INFO

    def test_empty(self):
        assert it.classify("") == it.INTENT_INFO

    def test_questions_are_distinct(self):
        asked = it.questions("전기기사 실기", it.INTENT_HOWTO)
        assert len(asked) == len(set(asked)) == 3

    def test_questions_contain_keyword(self):
        for q in it.questions("전기기사"):
            assert "전기기사" in q

    def test_dominant_picks_majority(self):
        assert it.dominant(["a 방법", "b 방법", "c 후기"]) == it.INTENT_HOWTO

    def test_dominant_empty(self):
        assert it.dominant([]) == it.INTENT_INFO

    def test_spread_groups(self):
        out = it.spread(["a 방법", "b 비용"])
        assert set(out) == {it.INTENT_HOWTO, it.INTENT_PRICE}


class TestSimilarity:
    def test_same_topic_is_similar(self):
        assert clustering.similarity("전기기사 실기", "전기기사 실기 방법") > 0.3

    def test_spacing_variants_match(self):
        # 한국어는 띄어쓰기가 일정하지 않다
        assert clustering.similarity("전기기사 실기", "전기기사실기") > 0.5

    def test_unrelated_is_zero(self):
        assert clustering.similarity("전기기사 실기", "마라탕 맛집") == 0.0

    def test_empty_is_zero(self):
        assert clustering.similarity("", "전기기사") == 0.0

    def test_stopword_only_overlap_is_weak(self):
        # '추천' 만 겹치는 것은 같은 주제가 아니다
        assert clustering.similarity("노트북 추천", "치킨 추천") < 0.34


class TestBuildClusters:
    def _pool(self):
        return [
            _kw("전기기사 실기", 900), _kw("전기기사 실기 방법", 500),
            _kw("전기기사 실기 일정", 300), _kw("마라탕 맛집", 800),
            _kw("마라탕 맛집 추천", 400), _kw("마라탕 맛집 후기", 200),
        ]

    def test_splits_into_two(self):
        groups = clustering.build(self._pool(), min_size=2)
        assert len(groups) == 2

    def test_representative_is_highest_volume(self):
        groups = clustering.build(self._pool(), min_size=2)
        assert groups[0][0].keyword == "전기기사 실기"

    def test_min_size_drops_small_groups(self):
        assert clustering.build(self._pool(), min_size=5) == []

    def test_max_size_caps(self):
        pool = [_kw(f"전기기사 실기 {i}", 100 - i) for i in range(20)]
        groups = clustering.build(pool, min_size=2, max_size=4)
        assert all(len(g) <= 4 for g in groups)

    def test_no_keyword_used_twice(self):
        groups = clustering.build(self._pool(), min_size=2)
        seen = [k.keyword for g in groups for k in g]
        assert len(seen) == len(set(seen))

    def test_empty_pool(self):
        assert clustering.build([], min_size=2) == []


class TestDescribe:
    def test_summary_fields(self):
        group = [_kw("마라탕 맛집", 800), _kw("마라탕 맛집 후기", 200)]
        out = clustering.describe(group)
        assert out["name"] == "마라탕 맛집"
        assert out["size"] == 2
        assert out["total_volume"] == 1000
        assert out["intent"] in it.INTENTS

    def test_takes_first_classified_niche(self):
        group = [_kw("a", 10, topic=None), _kw("b", 5, topic=7, sub=9)]
        out = clustering.describe(group)
        assert (out["topic_id"], out["subtopic_id"]) == (7, 9)

    def test_no_volume(self):
        group = [_kw("a", None), _kw("b", None)]
        assert clustering.describe(group)["total_volume"] is None


class TestClusterModel:
    def test_status_values(self):
        assert CLUSTER_NEW == "new" and CLUSTER_TITLED == "titled"

    def test_unique_per_user_blog_name(self):
        uniques = [c for c in KeywordCluster.__table__.constraints
                   if c.__class__.__name__ == "UniqueConstraint"]
        assert {c.name for c in uniques[0].columns} == {"user_id", "blog_id",
                                                        "name"}


class TestSettings:
    def test_cluster_defaults(self):
        cfg = KeywordModuleSettings.parse({})
        assert cfg.cluster_enabled is True
        assert cfg.cluster_min_size == 3 and cfg.cluster_max_size == 12
        assert cfg.titles_per_cluster == 0

    def test_threshold_out_of_range_falls_back(self):
        for bad in (0, -1, 5, "x"):
            cfg = KeywordModuleSettings.parse(
                {"keyword": {"cluster_threshold": bad}})
            assert cfg.cluster_threshold == 0.34

    def test_min_size_floor(self):
        cfg = KeywordModuleSettings.parse({"keyword": {"cluster_min_size": 0}})
        assert cfg.cluster_min_size == 2

    def test_round_trip(self):
        cfg = KeywordModuleSettings.parse(
            {"keyword": {"cluster_enabled": False}})
        assert cfg.to_dict()["cluster_enabled"] is False


class TestWiring:
    def test_single_path_skips_clustered_keywords(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        # 묶음에 든 키워드를 단독으로도 쓰면 같은 키워드로 두 번 만든다
        assert "KeywordCandidate.cluster_id.is_(None)" in src
        assert "run_clusters" in src

    def test_cluster_prompt_demands_distinct_questions(self):
        src = (BASE / "app/services/keyword_lab/title_maker.py").read_text(
            encoding="utf-8")
        assert "서로 다른 질문" in src
        assert "대표 글" in src and "곁가지" in src

    def test_runner_builds_then_titles(self):
        src = (BASE / "app/services/keyword_lab/runner.py").read_text(
            encoding="utf-8")
        assert "ClusterBuilder" in src
        assert src.index("run_clusters") < src.index("maker.run(cfg, blog)")

    def test_form_serializes_cluster_settings(self):
        js = (BASE / "app/static/js/modules/form.js").read_text(
            encoding="utf-8")
        assert "cluster_enabled: !!k.cluster_enabled" in js
        assert "titles_per_cluster" in js

    @pytest.mark.parametrize("path", [
        "app/services/keyword_lab/clustering.py",
        "app/services/keyword_lab/cluster_builder.py",
        "app/services/keyword_lab/intent.py",
        "app/services/keyword_lab/title_maker.py",
    ])
    def test_files_under_500_lines(self, path):
        lines = (BASE / path).read_text(encoding="utf-8").count("\n")
        assert lines <= 500, f"{path} = {lines}줄"
