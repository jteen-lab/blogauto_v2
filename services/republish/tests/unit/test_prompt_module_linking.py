"""프롬프트 모듈 — 블로그 선택 시 카테고리 자동 연동 (2026-08-31).

수작남만 카테고리가 연동되지 않았다. 데이터는 정상이었다
(blog_categories 6건, is_active=true, 토픽·서브토픽 정합).

원인: 편집 화면이 **저장된 매핑에서만** 불러올 블로그를 뽑았다.
매핑이 빈 모듈은 카테고리를 불러오지 못하고, 카테고리가 안 보이니
매핑을 다시 만들 수도 없다 — 스스로 회복이 불가능한 상태였다.

순서도: docs/flowcharts/prompt_module_category_link.md
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LINKING_JS = ROOT / "app/static/js/modules/prompt-form-linking.js"

# 운영 데이터 그대로. 수작남(13)은 4개 토픽에 걸쳐 있고, 슈마즈(15)는 단일 토픽.
HARNESS = """
const fs = require('fs');
global.window = {};
eval(fs.readFileSync(SRC, 'utf8'));

const CATS = {
  13: [{topic_id:1,subtopic_id:18},{topic_id:8,subtopic_id:50},{topic_id:8,subtopic_id:44},
       {topic_id:12,subtopic_id:53},{topic_id:5,subtopic_id:51},{topic_id:5,subtopic_id:32}],
  15: [{topic_id:7,subtopic_id:33},{topic_id:7,subtopic_id:34},{topic_id:7,subtopic_id:35}],
};
let LOADED = [];
function makeApp(blogs, bcm, linkMode) {
  const app = Object.create(window.promptModuleLinkingMethods);
  app.isEdit = true;
  app.module = {settings: {link_mode: linkMode || 'blog', blogs, blog_category_map: bcm}};
  app.promptModule = {
    selectedBlogs: blogs.slice(), selectedCategories: [],
    matchedBlogs: [], unmatchedBlogs: [], blogs: [],
    linking: window.createPromptModuleLinkingState(),
  };
  app._loadBlogsForBlogMode = async () => {};
  app.loadUsedBlogCategories = async () => {};
  app.checkConflicts = () => {};
  app.loadBlogCategories = async (id) => {
    LOADED.push(id);
    app.promptModule.linking.blogCategories[id] = (CATS[id] || []).map(c => ({...c}));
  };
  return app;
}
"""


def _run(script: str) -> dict:
    program = f"const SRC = {str(LINKING_JS)!r};\n" + HARNESS + script
    result = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_empty_map_still_loads_the_blogs_categories() -> None:
    """매핑이 비어도 선택된 블로그의 카테고리를 불러와야 한다.

    고치기 전에는 매핑에서만 blog_id 를 뽑아 아무것도 불러오지 않았다.
    """
    data = _run("""
(async () => {
  LOADED = [];
  const app = makeApp([13], []);
  await app.initPromptModuleLinkingFromData();
  console.log(JSON.stringify({
    loaded: LOADED,
    shown: app.getAutoLinkedCategories(13).length,
    map: app.promptModule.linking.blogCategoryMap.length,
  }));
})();
""")
    assert data["loaded"] == [13], "선택된 블로그를 불러오지 않았다"
    assert data["shown"] == 6, "화면에 카테고리가 표시되지 않는다"


def test_empty_map_is_rebuilt_so_it_can_be_saved() -> None:
    """매핑이 비면 스스로 회복해야 한다.

    안 그러면 카테고리가 안 보이니 사용자가 다시 만들 방법이 없다.
    """
    data = _run("""
(async () => {
  const app = makeApp([13], []);
  await app.initPromptModuleLinkingFromData();
  const map = app.promptModule.linking.blogCategoryMap;
  console.log(JSON.stringify({
    count: map.length,
    blogIds: [...new Set(map.map(m => m.blog_id))],
    topics: [...new Set(map.map(m => m.topic_id))].sort((a,b) => a-b),
  }));
})();
""")
    assert data["count"] == 6
    assert data["blogIds"] == [13]
    assert data["topics"] == [1, 5, 8, 12], "여러 토픽에 걸친 카테고리가 모두 담겨야 한다"


def test_existing_map_is_not_overwritten() -> None:
    """정상 모듈의 매핑을 덮어쓰면 사용자가 뺀 카테고리가 되살아난다.

    제외 목록은 저장되지 않으므로 다시 만들면 전부 되돌아온다.
    """
    data = _run("""
(async () => {
  const bcm = [{blog_id:15,topic_id:7,subtopic_id:33},
               {blog_id:15,topic_id:7,subtopic_id:34}];   // 3개 중 2개만 연결
  const app = makeApp([15], bcm);
  await app.initPromptModuleLinkingFromData();
  const map = app.promptModule.linking.blogCategoryMap;
  console.log(JSON.stringify({
    count: map.length,
    subtopics: map.map(m => m.subtopic_id).sort((a,b) => a-b),
  }));
})();
""")
    assert data["count"] == 2, "저장된 매핑을 덮어썼다 — 뺀 카테고리가 되살아난다"
    assert data["subtopics"] == [33, 34]


def test_map_blogs_are_loaded_too() -> None:
    """매핑에만 있고 선택 목록에 없는 블로그도 불러와야 한다.

    둘을 합치지 않으면 어느 한쪽이 빠진다.
    """
    data = _run("""
(async () => {
  LOADED = [];
  const app = makeApp([13], [{blog_id:15,topic_id:7,subtopic_id:33}]);
  await app.initPromptModuleLinkingFromData();
  console.log(JSON.stringify({loaded: LOADED.sort((a,b) => a-b)}));
})();
""")
    assert data["loaded"] == [13, 15]


def test_no_duplicate_loads() -> None:
    """선택 목록과 매핑에 같은 블로그가 있어도 한 번만 불러온다."""
    data = _run("""
(async () => {
  LOADED = [];
  const app = makeApp([13], [{blog_id:13,topic_id:1,subtopic_id:18}]);
  await app.initPromptModuleLinkingFromData();
  console.log(JSON.stringify({loaded: LOADED}));
})();
""")
    assert data["loaded"] == [13]


def test_category_mode_is_untouched() -> None:
    """카테고리 모드는 블로그 모드 경로를 타지 않는다."""
    data = _run("""
(async () => {
  LOADED = [];
  const app = makeApp([13], [], 'category');
  await app.initPromptModuleLinkingFromData();
  console.log(JSON.stringify({loaded: LOADED}));
})();
""")
    assert data["loaded"] == []


def test_load_targets_come_from_both_sources() -> None:
    """매핑에서만 뽑던 코드로 되돌아가면 안 된다."""
    source = LINKING_JS.read_text(encoding="utf-8")
    block = re.search(
        r"if \(this\.promptModule\.linking\.linkMode === 'blog'\) \{(.*?)\n        \}",
        source, re.S,
    )
    assert block, "블로그 모드 초기화 블록을 찾지 못함"
    body = block.group(1)
    assert "selectedBlogs" in body, "선택된 블로그를 대상에 넣지 않는다"
    assert "blogCategoryMap.map" in body, "저장된 매핑도 대상에 넣어야 한다"
