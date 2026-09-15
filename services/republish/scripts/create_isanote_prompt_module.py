"""이사노트 생성 모듈을 만든다.

수작업으로 쓰던 1인칭 경험담 방식을 프롬프트로 옮긴 것이다. 기존
블로그들은 전문가 설명체를 쓰지만 이사노트는 겪은 사람이 답하는 글이라
말투와 구조가 다르다.

한 번만 돌리면 된다. 이미 있으면 설정만 갱신한다.

    python3 scripts/create_isanote_prompt_module.py
"""
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import db_manager  # noqa: E402
from app.models.module import Module  # noqa: E402
from app.models.module_type import ModuleType  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MODULE_NAME = "이사노트_구글 블로거"
BLOG_ID = 21
USER_ID = 1

SYSTEM_PROMPT = (
    "당신은 이사와 청소를 직접 여러 번 겪어본 사람입니다. 겪어보고 알게 된 "
    "것을 묻는 사람에게 설명하듯 씁니다. 정보를 나열하지 않고, 왜 그런지와 "
    "무엇을 확인해야 하는지를 함께 말합니다."
)

USER_PROMPT = """제목: {title}
카테고리: {category}
키워드: {keywords}

────────────────────────────────────────
✦ 말투 — 겪어본 사람의 1인칭
- "저는 ~했습니다", "~하더군요", "~라고 생각합니다" 형태로 씁니다
- 자기 경험을 최소 세 번 이상 구체적으로 넣습니다 (금액·시기·상황을 함께)
- 남 얘기처럼 "일반적으로 ~합니다"로만 쓰지 않습니다
- 독자를 "질문자분"이 아니라 상황에 놓인 사람으로 대합니다
- 감탄사·과장·영업 문구는 쓰지 않습니다
────────────────────────────────────────

────────────────────────────────────────
✦ 독자 — 당장 결정해야 하는 사람
- 며칠 안에 실제로 이사나 청소를 앞둔 사람을 가정합니다
- 금액 범위, 기준이 되는 날짜, 확인할 서류를 구체적으로 적습니다
- "상황에 따라 다릅니다"로 끝내지 않고 어떤 상황에서 어떻게 갈리는지 적습니다
────────────────────────────────────────

────────────────────────────────────────
✦ 글쓰기 기본 원칙
- 마크다운으로 작성합니다
- 인용문(>) 을 절대 쓰지 않습니다
- 제목 앞 번호·특수문자를 쓰지 않습니다
- "STEP", "단계 1", 구분선(---) 같은 메타 텍스트를 출력하지 않습니다
- 해시태그를 쓰지 않습니다
- 참고한 곳을 밝히지 않습니다 (지식인·카페 등을 언급하지 않습니다)
- 본문 4500~5500자로 씁니다
- 한 번에 끝까지 완성합니다
────────────────────────────────────────

────────────────────────────────────────
✦ 쓰지 않을 표현
급변하는, 발돋움, 귀추가 주목, 필수적입니다, 중요한 역할을 합니다,
살펴보겠습니다, 알아보겠습니다, ~하시기 바랍니다, 다양한, 효율적인,
혁신적인, 최적화된, 바쁜 현대인, 도움이 되셨길
────────────────────────────────────────

────────────────────────────────────────
✦ 구조
1. 도입 — 어떤 상황에서 이 고민이 생기는지 200자 이상.
   "안녕하세요"로 시작하지 않습니다. 내 경험 한 줄을 함께 넣습니다
2. ## 먼저 결론 — 핵심 답을 한 단락으로 먼저 말합니다
3. ## 갈리는 지점 — ### 소제목 3~4개로 나눠 각 300자 이상.
   비용이나 조건이 나오면 표를 하나 넣습니다
4. ## 기준이 되는 것 — 법·약관·기한 같은 근거를 적습니다.
   근거가 있으면 어느 제도인지, 며칠 이내인지 명시합니다
5. ## 사례 — 실제로 어떻게 갈렸는지 두세 가지를 적습니다
6. ## 정리 — 확인할 것을 목록으로 만듭니다 (7~8개)
7. ## 마지막 문단 — 겪어본 사람으로서의 판단 한 단락
▸ 섹션 제목은 내용을 나타내는 자연어로 짓습니다.
  위 이름을 그대로 쓰지 말고 주제에 맞게 바꿉니다
────────────────────────────────────────"""

SETTINGS = {
    "blogs": [BLOG_ID],
    "link_mode": "blog",
    "categories": [],
    "aeo_enabled": True,
    "adsense_auto": False,
    "adsense_role": "never",
    "niche_enabled": False,
    "info_gain_enabled": True,
    "text_replace_enabled": True,
    "exclude_sibling_titles": True,
    "internal_links": {"enabled": False},
    "reference": {
        "enabled": True,
        "ai_provider": "openai",
        "ai_model": "gpt-4.1-mini",
        "max_search": 30,
        "crawl_target": 10,
        "summary_method": "ai",
        "summary_count": 3,
        "summary_style": "concise",
        "max_length": 500,
        "algorithm_type": "textrank",
    },
    # 근거 체크리스트 — 쟁점을 먼저 세우고 항목별로 나눠 찾는다
    "evidence_checklist": {"enabled": True},
    "quality_gate": {"enabled": True, "trace_blocks": False},
    "title_recombine": {
        "enabled": True,
        "min_length": 25,
        "max_length": 38,
        "styles": ["emotional", "practical", "question"],
        "count_per_style": 3,
        "custom_prompt": (
            "- 이사·청소를 앞둔 사람이 실제로 검색할 말로 재조합\n"
            "- 상황과 금액·기한 중 하나를 넣을 것\n"
            "- 문장 부호 사용 금지"
        ),
        "style_prompts": {
            "emotional": "독자의 상황을 조건절로 시작할 것. "
                         "예: 이사 전날 짐이 안 빠질 때 확인할 것",
            "practical": "금액·기간·개수 중 하나를 반드시 넣을 것. "
                         "예: 퇴거 청소비 15만원과 40만원을 가른 기준",
            "question": "판단을 묻는 형태로 쓸 것. "
                        "예: 퇴거 청소는 세입자가 꼭 해야 하는가",
        },
    },
    "image_generation": {"enabled": False},
    "content_generation": {
        "enabled": True,
        "provider": "openai",
        "max_tokens": 8192,
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 40,
        "presence_penalty": 0.2,
        "frequency_penalty": 0.3,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt_template": USER_PROMPT,
        "renewal_prompt": {"mode": "inherit", "text": ""},
    },
}


async def main() -> None:
    """모듈을 만들거나 설정을 갱신한다."""
    await db_manager.initialize()
    async with db_manager.get_session() as db:
        type_id = (await db.execute(
            select(ModuleType.id).where(ModuleType.code == "prompt")
        )).scalar_one()

        module = (await db.execute(
            select(Module).where(Module.user_id == USER_ID,
                                 Module.name == MODULE_NAME)
        )).scalar_one_or_none()

        if module is None:
            module = Module(
                user_id=USER_ID, module_type_id=type_id, name=MODULE_NAME,
                description="이사노트 — 겪어본 사람의 1인칭 경험담",
                settings=SETTINGS, params={})
            db.add(module)
            action = "만들었습니다"
        else:
            module.settings = SETTINGS
            action = "갱신했습니다"

        await db.commit()
        await db.refresh(module)
        logger.info("%s | id=%s | %s", action, module.id, module.name)
        logger.info("본문 프롬프트 %d자", len(USER_PROMPT))


if __name__ == "__main__":
    asyncio.run(main())
