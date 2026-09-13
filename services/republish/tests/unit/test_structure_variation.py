"""구조 다양화 — 같은 블로그·같은 니치라도 글마다 다르게."""
import pytest

from app.services.generation import module_scope as MS
from app.services.generation import prompt_rotation as PR
from app.services.generation import variant_picker as VP


def _v(**kw):
    base = {"template": kw.pop("template", "프롬프트 본문")}
    base.update(kw)
    return base


class TestVariantPicker:
    def test_후보가_없으면_None(self):
        assert VP.pick([], VP.MODE_RANDOM) is None

    def test_모르는_모드는_무작위로(self):
        assert VP.normalize_mode("이상한모드") == VP.MODE_RANDOM

    def test_순번은_커서를_따른다(self):
        items = [_v(label="A"), _v(label="B"), _v(label="C")]
        assert VP.pick(items, VP.MODE_SEQUENTIAL, cursor=0).index == 0
        assert VP.pick(items, VP.MODE_SEQUENTIAL, cursor=1).index == 1
        assert VP.pick(items, VP.MODE_SEQUENTIAL, cursor=4).index == 1  # 순환

    def test_순번은_다음_커서를_돌려준다(self):
        got = VP.pick([_v(), _v()], VP.MODE_SEQUENTIAL, cursor=3)
        assert got.next_cursor == 4

    def test_주제별_고정은_같은_주제면_같은_변형(self):
        items = [_v(label="A"), _v(label="B"), _v(label="C")]
        a = VP.pick(items, VP.MODE_BY_NICHE, topic_id=24)
        b = VP.pick(items, VP.MODE_BY_NICHE, topic_id=24)
        assert a.index == b.index

    def test_주제가_다르면_변형도_갈린다(self):
        items = [_v(label=c) for c in "ABCDEFGH"]
        picks = {VP.pick(items, VP.MODE_BY_NICHE, topic_id=i).index
                 for i in range(1, 20)}
        assert len(picks) > 1

    def test_키워드별_고정(self):
        items = [_v(label="A"), _v(label="B"), _v(label="C")]
        a = VP.pick(items, VP.MODE_BY_KEYWORD, keyword="이사 견적")
        b = VP.pick(items, VP.MODE_BY_KEYWORD, keyword="이사 견적")
        assert a.index == b.index


class TestCandidates:
    def test_주제_지정이_없으면_모든_주제에_쓴다(self):
        assert len(VP.candidates([_v()], topic_id=24)) == 1

    def test_주제_지정은_일치할_때만(self):
        items = [_v(topic_ids=[24]), _v(topic_ids=[99])]
        got = VP.candidates(items, topic_id=24)
        assert len(got) == 1 and got[0]["topic_ids"] == [24]

    def test_목적이_다르면_뺀다(self):
        items = [_v(purpose="cpa"), _v(purpose="adsense")]
        got = VP.candidates(items, purpose="cpa")
        assert len(got) == 1

    def test_키워드_패턴으로_거른다(self):
        items = [_v(keywords=["청소"]), _v(keywords=["이사"])]
        got = VP.candidates(items, keyword="원룸 이사 견적")
        assert len(got) == 1 and got[0]["keywords"] == ["이사"]

    def test_하나도_안_맞으면_공용으로_물러선다(self):
        items = [_v(topic_ids=[99]), _v(label="공용")]
        got = VP.candidates(items, topic_id=24)
        assert len(got) == 1 and got[0].get("label") == "공용"


class TestPromptRotation:
    def _settings(self, **cfg):
        base = {"enabled": True, "mode": "sequential",
                "variants": [_v(template="첫째"), _v(template="둘째")]}
        base.update(cfg)
        return {"prompt_rotation": base}

    def test_변형이_하나면_켜지지_않는다(self):
        s = self._settings(variants=[_v()])
        assert not PR.is_enabled(s)

    def test_꺼져_있으면_원본을_돌려준다(self):
        s = self._settings(enabled=False)
        assert PR.apply(s, blog=None) is s

    def test_켜지면_프롬프트를_갈아끼운다(self):
        got = PR.apply(self._settings(), blog=None, cursor=1)
        assert got["content_generation"]["user_prompt_template"] == "둘째"
        assert got["_rotation"]["index"] == 1

    def test_원본은_건드리지_않는다(self):
        s = self._settings()
        PR.apply(s, blog=None)
        assert "content_generation" not in s

    def test_프리셋_코드로도_고른다(self):
        from app.services.prompt_builder.presets import PRESETS

        코드 = next((p["code"] for p in PRESETS if p.get("full_prompt")), None)
        if 코드 is None:
            pytest.skip("완성 프롬프트를 가진 프리셋이 없다")
        s = self._settings(variants=[{"code": 코드}, {"code": 코드}])
        got = PR.select(s, blog=None)
        assert got and got["template"]

    def test_프롬프트가_비면_None(self):
        s = self._settings(variants=[{"code": "없는코드"},
                                     {"code": "없는코드2"}])
        assert PR.select(s, blog=None) is None

    def test_목적_추정_CPA(self):
        class B:
            cpa_enabled = True
        assert PR.resolve_purpose(B(), {}) == PR.PURPOSE_CPA

    def test_목적_추정_애드센스(self):
        class B:
            cpa_enabled = False
            adsense_status = "pending"
        assert PR.resolve_purpose(B(), {}) == PR.PURPOSE_ADSENSE

    def test_설정이_추정을_이긴다(self):
        class B:
            cpa_enabled = True
        s = {"prompt_rotation": {"purpose": "info"}}
        assert PR.resolve_purpose(B(), s) == PR.PURPOSE_INFO

    def test_요약_문구(self):
        assert "변형 2개" in PR.describe(self._settings())
        assert PR.describe({}) == "로테이션 꺼짐"


class TestModuleScope:
    class M:
        def __init__(self, mid, settings):
            self.id, self.settings = mid, settings

    def _dedicated(self, mid, ids):
        return self.M(mid, {"niche_enabled": True, "niche_topic_ids": ids})

    def _shared(self, mid):
        return self.M(mid, {"niche_enabled": False})

    def test_니치_강제가_꺼지면_공용이다(self):
        assert MS.is_shared({"niche_enabled": False})

    def test_전담은_지정_주제만_맡는다(self):
        s = {"niche_enabled": True, "niche_topic_ids": [24]}
        assert MS.handles(s, 24)
        assert not MS.handles(s, 99)

    def test_공용은_전부_맡는다(self):
        assert MS.handles({"niche_enabled": False}, 99)

    def test_모듈이_하나면_그것을_쓴다(self):
        mod = self._shared(1)
        assert MS.pick([mod], 24)[0] is mod

    def test_전담이_공용을_이긴다(self):
        공용, 전담 = self._shared(1), self._dedicated(2, [24])
        got, reason = MS.pick([공용, 전담], 24)
        assert got.id == 2 and "전담" in reason

    def test_전담이_없으면_공용이_받는다(self):
        공용, 전담 = self._shared(1), self._dedicated(2, [24])
        got, reason = MS.pick([공용, 전담], 99)
        assert got.id == 1 and "공용" in reason

    def test_모듈이_하나면_니치와_무관하게_쓴다(self):
        # 라우팅이 필요 없는 상황이다. 어느 제목이 이 모듈에 오는지는
        # 기존 니치 강제(resolve_module_niche)가 이미 거른다.
        전담 = self._dedicated(2, [24])
        got, reason = MS.pick([전담], 99)
        assert got is 전담
        assert "하나뿐" in reason

    def test_전담만_여럿인데_아무도_안_맡으면_사유를_남긴다(self):
        got, reason = MS.pick([self._dedicated(2, [24]),
                               self._dedicated(3, [25])], 99)
        assert got is None and "맡는 모듈이 없" in reason

    def test_모듈이_없으면_사유를_남긴다(self):
        got, reason = MS.pick([], 24)
        assert got is None and "연결된 생성 모듈이 없" in reason

    def test_공용이_없으면_경고한다(self):
        got = MS.coverage([self._dedicated(2, [24])])
        assert got["warning"] and not got["has_shared"]

    def test_공용이_있으면_경고하지_않는다(self):
        got = MS.coverage([self._shared(1), self._dedicated(2, [24])])
        assert got["warning"] is None
        assert got["covered_topic_ids"] == [24]


class TestTemplateImages:
    def _svc(self):
        from app.services.generation.template_image_service import (
            TemplateImageService,
        )
        return TemplateImageService()

    def test_복수_키가_없으면_None(self):
        got = self._svc()._pick_template(
            {"template_image": "blogs/21/t.png"}, None, "", 0)
        assert got is None          # 단수 키로 폴백된다

    def test_복수_키가_있으면_고른다(self):
        cfg = {"template_images": [{"path": "a.png"}, {"path": "b.png"}],
               "template_image_mode": "sequential"}
        got = self._svc()._pick_template(cfg, None, "", 1)
        assert got["path"] == "b.png"
        assert got["next_cursor"] == 2

    def test_path_가_없는_항목은_무시한다(self):
        cfg = {"template_images": [{"label": "빈 것"}]}
        assert self._svc()._pick_template(cfg, None, "", 0) is None

    def test_주제별_고정도_된다(self):
        cfg = {"template_images": [{"path": "a.png"}, {"path": "b.png"}],
               "template_image_mode": "by_niche"}
        a = self._svc()._pick_template(cfg, 24, "", 0)
        b = self._svc()._pick_template(cfg, 24, "", 0)
        assert a["path"] == b["path"]
