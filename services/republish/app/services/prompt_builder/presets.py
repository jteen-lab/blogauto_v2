"""프롬프트 빌더 빠른 적용 프리셋 카탈로그.

blocks.py 500줄 제한 준수를 위해 프리셋 데이터를 분리했다.
각 프리셋은 (페르소나·독자수준·섹션패턴·시작톤) 코드와 어울리는 니치 표기를
함께 갖는다. 2026-08-28 재구성: 운영 방침이 **니치 특화 블로그**로 바뀌면서,
프리셋을 실제 니치 체계(주제 18개)에 1:1로 대응시켰다.
이전 프리셋의 추천 니치("패션·뷰티", "영화·드라마" 등)는 현재 카테고리에
존재하지 않는 옛 분류라 전부 교체했다.
blocks.py 가 `from .presets import PRESETS` 로 재-export 하므로 공개 API 불변.
"""
from __future__ import annotations

from typing import Dict, List

# F11 애드센스 승인용 전용 프롬프트(2026-08-17, 사용자 승인).
# 기존 4축(페르소나·독자·패턴·톤) 조합이 아니라, 애드센스 승인에 유리한
# 콘텐츠 특성(정보이득·검색의도 즉답·E-E-A-T·출처·people-first·자연스러움)을
# 담은 독립 프롬프트. 생성 파이프라인이 {title}/{category}/{keywords}/
# {reference_materials}를 치환한다. 순서도 adsense_f11_prompt_preset.md.
ADSENSE_APPROVAL_PROMPT: str = (
    "제목: {title}\n"
    "카테고리: {category}\n"
    "키워드: {keywords}\n"
    "\n"
    "당신은 해당 분야를 오래 다뤄 온 편집자이자 검증자입니다. 위 제목으로,\n"
    "구글 애드센스 심사를 통과할 수 있는 \"사람을 위한(people-first)\" 고품질 블로그\n"
    "글을 작성하세요. 검색엔진·광고가 아니라 실제 독자의 문제 해결을 최우선으로 합니다.\n"
    "\n"
    "■ 최우선 원칙 — 정보이득(Information Gain)\n"
    "- 공개된 정보를 그대로 재배열·요약만 하지 마세요. 다른 곳에도 있는 뻔한 내용이라면\n"
    "  \"그래서 어떻게 판단·선택·적용하는가\"를 한 단계 더 파고들어 고유한 관점을 더합니다.\n"
    "- 각 소주제에 아래 중 최소 하나를 반드시 포함:\n"
    "  (a) 서로 다른 조건·상황을 비교한 구체적 판단 기준\n"
    "  (b) 실제 적용 시 흔히 놓치는 주의점·예외·실수\n"
    "  (c) 수치·기간·조건 등 검증 가능한 구체 정보\n"
    "\n"
    "■ 검색 의도 즉시 충족\n"
    "- 독자가 이 제목을 검색한 이유(무엇을 알고/결정/실행하려는지)를 먼저 파악해,\n"
    "  서두 2~3문장 안에 핵심 답의 방향을 제시하세요. 배경 설명으로 서두를 늘리지 마세요.\n"
    "- 목록·체크리스트가 더 유용한 주제면 장문 설명 대신 그 형식으로 바로 답합니다.\n"
    "\n"
    "■ 깊이와 근거 (E-E-A-T 신호)\n"
    "- 추상적 일반론 대신, 구체적인 상황·사례·적용 시나리오로 설명하세요\n"
    "  (예: \"월 소득이 일정하지 않은 프리랜서라면 …\", \"처음 신청하는 경우 …\").\n"
    "- 판단에는 근거를 답니다. 가능하면 \"○○ 기관 기준\", \"공식 안내에 따르면\"처럼\n"
    "  출처의 성격을 밝히세요. 참고자료가 주어지면 그 내용을 우선 활용하세요:\n"
    "{reference_materials}\n"
    "- ★ 정직 규칙(반드시 준수): 없는 통계·수치·연구 결과를 지어내지 마세요.\n"
    "  확인 불가한 내용은 \"일반적으로\", \"경우에 따라 다르지만\"처럼 정성적으로 표현합니다.\n"
    "  또한 겪지 않은 개인 경험담을 실제처럼 꾸며내지 마세요. 경험은 일반화된\n"
    "  상황 묘사·사례로 대체합니다.\n"
    "\n"
    "■ 구조 (유연 — 형식 강제보다 내용 우선)\n"
    "- 글의 흐름과 검색 의도에 맞는 자연어 소제목(##)으로 3~6개 구획을 나눕니다.\n"
    "  정해진 틀(정보→비교표→팁→…)을 기계적으로 채우지 마세요.\n"
    "- 비교표·번호 목록은 \"무엇을 선택·판단할지 근거가 드러날 때\"에만 사용합니다.\n"
    "  단순 스펙 나열용 표·목록은 넣지 마세요.\n"
    "- 결론은 뻔한 광고성 마무리(\"꼭 확인해보세요!\")를 피하고, 독자가 지금\n"
    "  실행할 수 있는 다음 행동 하나로 맺습니다.\n"
    "\n"
    "■ 분량·문체\n"
    "- 한글 기준 2,000자 이상, 충분한 깊이. 얕은 요약·의미 없는 반복으로 분량을\n"
    "  채우지 마세요.\n"
    "- 자연스럽고 읽기 쉬운 문장. 기계적·번역투·상투적 AI 문체를 피합니다.\n"
    "\n"
    "■ 형식 규칙\n"
    "- 마크다운으로 작성. 제목(#~######) 앞 번호·특수문자 금지, 소제목은 내용을\n"
    "  나타내는 자연어로.\n"
    "- \"STEP 1\", \"단계 1\", A/B/C 같은 구조 라벨과 구분선(─, ---)을 본문에 출력하지 마세요.\n"
    "- 해시태그 금지. 처음부터 끝까지 멈추지 않고 한 번에 완성하세요."
)

# 니치별 프리셋 — 제목 재고가 있는 주제만 다룬다(2026-08-28 실측 기준).
# 재고 절반 이상이 YMYL(금융/대출 951 · 건강/의학 260 · 재테크 167 ·
# 정부지원금 54 · 보험 36 · 세금 15)이라 해당 프리셋은 C-YMYL 원칙을 함께 건다.
PRESETS: List[Dict[str, object]] = [
    # F11 애드센스 승인용 전용 프롬프트(2026-08-17). 4축 조합이 아니라
    # 완성 프롬프트(full_prompt)를 user_prompt_template에 그대로 채운다.
    # 적용 시 정보이득 지시가 프롬프트에 내장돼 있으므로 F7 토글은 끈다(이중 지시 방지).
    {
        "code": "adsense-approval",
        "label": "🔒 애드센스 승인용 (전용 프롬프트)",
        "categories": "승인 심사 대비 — 니치 무관, 정보이득·E-E-A-T 중심",
        "full_prompt": ADSENSE_APPROVAL_PROMPT,
    },

    # ── YMYL 군 ────────────────────────────────────────────
    {
        "code": "n-loan",
        "label": "💳 대출·보험·세금 · 분석가/결정·P4·수치",
        "categories": "금융/대출 · 보험 · 세금/절세",
        "persona": "P-Analyst",
        "reader": "R-Decision",
        "pattern": "P4",
        "tone": "T-Numbers",
        "common": "C-YMYL",
    },
    {
        "code": "n-wealth",
        "label": "📈 재테크·부동산·노후 · 분석가/중급·P1·수치",
        "categories": "재테크/돈관리 · 부동산 · 시니어/노후",
        "persona": "P-Analyst",
        "reader": "R-Intermediate",
        "pattern": "P1",
        "tone": "T-Numbers",
        "common": "C-YMYL",
    },
    {
        "code": "n-welfare",
        "label": "🏛 정부지원금·복지 · 안내자/신청자·P6·자격확인",
        "categories": "정부지원금/복지",
        "persona": "P-Guide",
        "reader": "R-Applicant",
        "pattern": "P6",
        "tone": "T-Eligibility",
        "common": "C-YMYL",
    },
    {
        "code": "n-health",
        "label": "🩺 건강·의학 · 전문가/입문·P2·정의",
        "categories": "건강/의학 · 의료",
        "persona": "P-Expert",
        "reader": "R-Beginner",
        "pattern": "P2",
        "tone": "T-Definition",
        "common": "C-YMYL",
    },
    {
        "code": "n-parenting",
        "label": "👶 출산·육아 · 친구/입문·P5·공감",
        "categories": "출산/육아",
        "persona": "P-Friend",
        "reader": "R-Beginner",
        "pattern": "P5",
        "tone": "T-Empathy",
        "common": "C-YMYL",
    },

    # ── 절차·실행 군 ───────────────────────────────────────
    {
        "code": "n-career",
        "label": "🎓 취업·자격증 · 안내자/신청자·P6·자격확인",
        "categories": "취업/자격증",
        "persona": "P-Guide",
        "reader": "R-Applicant",
        "pattern": "P6",
        "tone": "T-Eligibility",
    },
    {
        "code": "n-life",
        "label": "🏠 생활정보·지역 · 중립/입문·P3·장면",
        "categories": "생활 정보 · 지역/업체정보",
        "persona": "P-Neutral",
        "reader": "R-Beginner",
        "pattern": "P3",
        "tone": "T-Scene",
    },

    # ── 경험·비교 군 ───────────────────────────────────────
    {
        "code": "n-travel",
        "label": "✈️ 여행·음식 · 에세이/중급·P5·장면",
        "categories": "여행/관광 · 음식/레시피",
        "persona": "P-Essayist",
        "reader": "R-Intermediate",
        "pattern": "P5",
        "tone": "T-Scene",
    },
    {
        "code": "n-tech",
        "label": "💻 IT·AI·자동차·리뷰 · 전문가/중급·P1·정의",
        "categories": "컴퓨터/IT · AI/인공지능 · 자동차 · 쇼핑/리뷰",
        "persona": "P-Expert",
        "reader": "R-Intermediate",
        "pattern": "P1",
        "tone": "T-Definition",
    },
]
