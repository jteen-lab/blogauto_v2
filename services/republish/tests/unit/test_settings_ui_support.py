"""UI 지원 백엔드 — 설정 보존과 템플릿 슬롯."""
import pytest

from app.services.blog_settings_template_slots import (
    drop, entries, filename_for, for_picker, next_slot, path_of, put,
    slot_drop, slot_path, slot_put,
)
from app.services.modules.settings_merge import merge, preserved_keys


class TestSettingsMerge:
    def test_화면이_모르는_키를_살린다(self):
        cur = {"keyword": {"a": 1}, "prompt_rotation": {"enabled": True}}
        new = {"keyword": {"a": 2}}
        got = merge(cur, new)
        assert got["keyword"] == {"a": 2}
        assert got["prompt_rotation"] == {"enabled": True}

    def test_보낸_키는_통째로_덮는다(self):
        # 깊게 병합하면 "체크를 껐는데 안 꺼진다" 가 된다
        cur = {"keyword": {"a": 1, "b": 2}}
        got = merge(cur, {"keyword": {"a": 9}})
        assert got["keyword"] == {"a": 9}
        assert "b" not in got["keyword"]

    def test_빈_값을_보내면_지울_수_있다(self):
        cur = {"prompt_rotation": {"enabled": True}}
        assert merge(cur, {"prompt_rotation": {}})["prompt_rotation"] == {}

    def test_기존이_비면_들어온_것을_쓴다(self):
        assert merge(None, {"a": 1}) == {"a": 1}
        assert merge({}, {"a": 1}) == {"a": 1}

    def test_들어온_것이_없으면_기존을_지킨다(self):
        assert merge({"a": 1}, None) == {"a": 1}

    def test_둘_다_비면_빈_설정(self):
        assert merge(None, None) == {}

    def test_보존된_키를_보고한다(self):
        got = preserved_keys({"a": 1, "b": 2}, {"a": 9})
        assert got == ["b"]


class TestFilename:
    def test_기본_슬롯은_기존_이름_그대로(self):
        assert filename_for("template", 21, ".png", 0) == "template_21.png"

    def test_추가_슬롯은_이름이_갈린다(self):
        assert filename_for("template", 21, ".png", 2) == "template_21_2.png"

    def test_폰트는_슬롯을_타지_않는다(self):
        assert filename_for("font", 21, ".ttf", 3) == "font_21.ttf"


class TestSlots:
    def _cfg(self):
        return {"template_image": "blogs/21/template/t.png"}

    def test_기본_슬롯은_단수_키를_읽는다(self):
        assert path_of(self._cfg(), 0) == "blogs/21/template/t.png"

    def test_없는_슬롯은_None(self):
        assert path_of(self._cfg(), 3) is None

    def test_추가_슬롯을_넣는다(self):
        got = put(self._cfg(), 1, "blogs/21/template/t_1.png")
        assert got["template_image"] == "blogs/21/template/t.png"   # 불변
        assert len(entries(got)) == 1
        assert path_of(got, 1) == "blogs/21/template/t_1.png"

    def test_같은_슬롯은_갈아끼운다(self):
        got = put(put(self._cfg(), 1, "a.png"), 1, "b.png")
        assert len(entries(got)) == 1
        assert path_of(got, 1) == "b.png"

    def test_원본을_건드리지_않는다(self):
        cfg = self._cfg()
        put(cfg, 1, "a.png")
        assert "template_images" not in cfg

    def test_슬롯을_지운다(self):
        got = drop(put(self._cfg(), 1, "a.png"), 1)
        assert "template_images" not in got
        assert got["template_image"] == "blogs/21/template/t.png"

    def test_기본_슬롯을_지우면_단수_키가_빠진다(self):
        assert "template_image" not in drop(self._cfg(), 0)

    def test_다음_빈_슬롯을_찾는다(self):
        assert next_slot(self._cfg()) == 1
        assert next_slot(put(self._cfg(), 1, "a.png")) == 2

    def test_꽉_차면_None(self):
        cfg = self._cfg()
        for i in range(1, 10):
            cfg = put(cfg, i, f"{i}.png")
        assert next_slot(cfg) is None


class TestForPicker:
    def test_추가_배경이_없으면_빈_목록(self):
        # 빈 목록이라야 호출부가 기존 단수 경로로 폴백한다
        assert for_picker({"template_image": "t.png"}) == []

    def test_기본_배경도_후보에_넣는다(self):
        cfg = put({"template_image": "t.png"}, 1, "t_1.png")
        got = for_picker(cfg)
        assert [r["path"] for r in got] == ["t.png", "t_1.png"]

    def test_조건을_그대로_넘긴다(self):
        cfg = put({"template_image": "t.png"}, 1, "t_1.png")
        cfg["template_images"][0]["topic_ids"] = [24]
        got = for_picker(cfg)
        assert got[1]["topic_ids"] == [24]


class TestRouterGlue:
    def test_폰트는_슬롯을_무시한다(self):
        cfg = {"font_file": "f.ttf"}
        assert slot_path(cfg, "font", 3) == "f.ttf"
        assert slot_put(cfg, "font", 3, "g.ttf")["font_file"] == "g.ttf"
        assert "font_file" not in slot_drop(cfg, "font", 3)

    def test_템플릿은_슬롯을_탄다(self):
        cfg = slot_put({}, "template", 2, "a.png")
        assert slot_path(cfg, "template", 2) == "a.png"
        assert slot_path(cfg, "template", 0) is None


class TestImageServiceUsesSlots:
    def _svc(self):
        from app.services.generation.template_image_service import (
            TemplateImageService,
        )
        return TemplateImageService()

    def test_단수만_있으면_폴백(self):
        got = self._svc()._pick_template({"template_image": "t.png"},
                                         None, "", 0)
        assert got is None

    def test_슬롯이_있으면_고른다(self):
        cfg = put({"template_image": "t.png"}, 1, "t_1.png")
        cfg["template_image_mode"] = "sequential"
        got = self._svc()._pick_template(cfg, None, "", 1)
        assert got["path"] == "t_1.png"

    def test_주제_조건이_걸린_배경만_고른다(self):
        cfg = put({"template_image": "t.png"}, 1, "t_1.png")
        cfg["template_images"][0]["topic_ids"] = [24]
        cfg["template_image_mode"] = "by_niche"
        # 기본 배경은 조건이 없어 24 에도 후보다 — 둘 중 하나가 나온다
        got = self._svc()._pick_template(cfg, 24, "", 0)
        assert got["path"] in ("t.png", "t_1.png")
        # 99 는 슬롯1 조건에 안 맞아 기본만 남는다
        got = self._svc()._pick_template(cfg, 99, "", 0)
        assert got["path"] == "t.png"
