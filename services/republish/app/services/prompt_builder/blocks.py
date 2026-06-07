"""
프롬프트 빌더 블록 데이터.

docs/prompts/style_blocks.md 의 마크다운 정의를 코드로 옮긴 것.
운영자가 BlogAuto 의 /prompt-builder 페이지에서 페르소나/독자수준/
섹션패턴/시작톤을 골라 user_prompt_template 을 완성하는 데 쓰인다.

마크다운과 동기화 유지를 위해 블록 텍스트는 이 파일을 단일 출처(SoT)로
삼고, 마크다운은 사람이 읽기 좋은 별도 사본으로 운영한다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class StyleBlock(TypedDict):
    """블록 1개의 데이터."""
    code: str           # 안정적 식별자 (예: "P-Expert")
    label: str          # UI 표시명 (예: "전문가 설명체")
    cluster: str        # 어느 클러스터에 적합한지 (예: "S1")
    body: str           # 프롬프트에 들어갈 본문 텍스트


# 페르소나 6종 (style_blocks.md "페르소나 블록")
PERSONAS: List[StyleBlock] = [
    {
        "code": "P-Expert",
        "label": "전문가 설명체",
        "cluster": "S1",
        "body": (
            "✦ 글쓰기 페르소나 — 전문가 설명체\n"
            "- \"~합니다\", \"~됩니다\", \"~로 나타납니다\" 격식 종결\n"
            "- 전문 용어는 그대로 사용, 필요시 한 줄 보충\n"
            "- 수치·근거·비교 적극 활용, 감정 표현·감탄사 최소화\n"
            "- 평가는 비교 우위 형식으로 표현 (\"A 가 B 대비 ~ 우위\")"
        ),
    },
    {
        "code": "P-Analyst",
        "label": "데이터 분석가",
        "cluster": "S1",
        "body": (
            "✦ 글쓰기 페르소나 — 데이터 분석가\n"
            "- \"~로 확인됩니다\", \"~한 경향을 보입니다\" 정보 전달형\n"
            "- 출처·수치·통계 적극 인용, 광고성 표현 배제\n"
            "- 옵션을 비교 우위로 평가, 한쪽 일방 추천 지양\n"
            "- 결론은 데이터에 근거해 단정 또는 조건부로 명시"
        ),
    },
    {
        "code": "P-Teacher",
        "label": "선생님 강의체",
        "cluster": "S2",
        "body": (
            "✦ 글쓰기 페르소나 — 선생님 강의체\n"
            "- \"~해보세요\", \"~기억하세요\", \"함께 알아볼게요\" 안내형\n"
            "- 어려운 용어가 나오면 (괄호 안 짧은 풀이) 병기\n"
            "- 단계별로 차근차근, 비유 적극 활용\n"
            "- 본인 경험은 가볍게, 객관적 설명 위주"
        ),
    },
    {
        "code": "P-Friend",
        "label": "친구 구어체",
        "cluster": "S3",
        "body": (
            "✦ 글쓰기 페르소나 — 친구 구어체\n"
            "- \"~해봤어요\", \"솔직히 말하면\", \"진짜로~\" 캐주얼 종결\n"
            "- 일상적 공감 표현, 자연스러운 감탄사 환영\n"
            "- 독자에게 말 거는 듯한 톤, 너무 격식적인 단어 회피\n"
            "- 본인 경험·실패담 한두 마디 자연스럽게"
        ),
    },
    {
        "code": "P-Essayist",
        "label": "에세이 서술체",
        "cluster": "S4",
        "body": (
            "✦ 글쓰기 페르소나 — 에세이 서술체\n"
            "- \"~했다\", \"~이었다\" 회고체 또는 \"~해요\" 부드러운 서술\n"
            "- 장면·감정·분위기 묘사 적극, 1인칭 시점\n"
            "- 시간·계절·날씨 같은 정서적 디테일 환영\n"
            "- 메마른 정보 나열 지양, 이야기처럼 흐르게"
        ),
    },
    {
        "code": "P-Neutral",
        "label": "중립 정보체",
        "cluster": "S5",
        "body": (
            "✦ 글쓰기 페르소나 — 중립 정보체\n"
            "- \"~이다\", \"~하며\", \"~있다\" 담담한 설명체\n"
            "- 수식어 최소화, 팩트 중심\n"
            "- 장단점 균형 있게 제시, 한쪽 일방 추천 회피\n"
            "- 평가는 비교·수치로만 표현"
        ),
    },
]


# 독자 수준 3종
READERS: List[StyleBlock] = [
    {
        "code": "R-Beginner",
        "label": "입문자",
        "cluster": "",
        "body": (
            "✦ 독자 수준 — 입문자\n"
            "- 이 주제를 처음 접하는 사람을 가정\n"
            "- 전문 용어는 한 문장으로 풀어주고, 비유·예시 적극\n"
            "- 표/목록은 단순한 형태(2~3열, 5개 이내 항목)\n"
            "- 한 번에 하나씩만 설명, 정보 밀도 낮게"
        ),
    },
    {
        "code": "R-Intermediate",
        "label": "중급자",
        "cluster": "",
        "body": (
            "✦ 독자 수준 — 중급자\n"
            "- 기본 개념은 이미 알고 있음을 가정\n"
            "- 용어 풀이 생략, 비교·장단점·실용 정보 위주\n"
            "- 표/목록은 다열 비교 가능한 형태\n"
            "- 정보 밀도 보통, 깊이 있게 한 단계 더 파고듦"
        ),
    },
    {
        "code": "R-Decision",
        "label": "결정 단계",
        "cluster": "",
        "body": (
            "✦ 독자 수준 — 결정 단계\n"
            "- 이미 한두 옵션을 비교 중인 독자를 가정\n"
            "- 가격·스펙·후기 평점·소요 시간 같은 의사결정 자료에 집중\n"
            "- 표는 다열 비교(가격·기능·평점 등), 목록은 결정 체크리스트\n"
            "- 결론은 독자 상황별 추천(\"A 라면 X, B 라면 Y\")으로 마무리"
        ),
    },
]


# 섹션 패턴 5종
PATTERNS: List[StyleBlock] = [
    {
        "code": "P1",
        "label": "정보·정리형",
        "cluster": "",
        "body": (
            "✦ 구조 — 패턴 P1 (정보·정리형)\n"
            "- A: 개념·배경 정리\n"
            "- B: 대표 옵션·항목 비교표 ← 표 반드시 포함\n"
            "- C: 활용 팁 목록 ← 번호/불릿 목록 반드시 포함\n"
            "- D: 심화·자주 헷갈리는 부분\n"
            "- E: 비용·수치·항목 정리표 ← 표 반드시 포함\n"
            "- F: 주의사항 목록 ← 번호/불릿 목록 반드시 포함"
        ),
    },
    {
        "code": "P2",
        "label": "교육·안내형",
        "cluster": "",
        "body": (
            "✦ 구조 — 패턴 P2 (교육·안내형)\n"
            "- A: 학습 목표·왜 알아야 하는지\n"
            "- B: 개념·용어 비교표 ← 표 반드시 포함\n"
            "- C: 단계별 체크리스트 ← 번호 목록 반드시 포함\n"
            "- D: 자주 헷갈리는 부분 정리\n"
            "- E: 예제·결과 정리표 ← 표 반드시 포함\n"
            "- F: 자주 묻는 질문(FAQ) ← 번호/불릿 목록 반드시 포함"
        ),
    },
    {
        "code": "P3",
        "label": "가이드·튜토리얼형",
        "cluster": "",
        "body": (
            "✦ 구조 — 패턴 P3 (가이드·튜토리얼형)\n"
            "- A: 기본 개념과 배경\n"
            "- B: 필요한 준비물·도구 비교표 ← 표 반드시 포함\n"
            "- C: 단계 1~3 실행 가이드 ← 번호 목록 반드시 포함\n"
            "- D: 단계 4~6 또는 심화 단계\n"
            "- E: 트러블슈팅 정리표 ← 표 반드시 포함\n"
            "- F: 자주 받는 질문 ← 번호/불릿 목록 반드시 포함"
        ),
    },
    {
        "code": "P4",
        "label": "분석·결정형",
        "cluster": "",
        "body": (
            "✦ 구조 — 패턴 P4 (분석·결정형)\n"
            "- A: 시장 흐름·통계·배경\n"
            "- B: 옵션 비교표(가격·기능·평점) ← 표 반드시 포함\n"
            "- C: 결정 시 핵심 포인트 ← 번호/불릿 목록 반드시 포함\n"
            "- D: 실제 사용자 후기·사례\n"
            "- E: 비용·시간·기간 정리표 ← 표 반드시 포함\n"
            "- F: 의사결정 체크리스트 ← 번호/불릿 목록 반드시 포함"
        ),
    },
    {
        "code": "P5",
        "label": "경험·공감형",
        "cluster": "",
        "body": (
            "✦ 구조 — 패턴 P5 (경험·공감형)\n"
            "- A: 사용·방문·시도하게 된 계기\n"
            "- B: 대안과의 1:1 비교표 ← 표 반드시 포함\n"
            "- C: 단계별 짧은 후기 목록 ← 번호/불릿 목록 반드시 포함\n"
            "- D: 디테일한 사례·에피소드\n"
            "- E: 기간·결과 수치 정리표 ← 표 반드시 포함\n"
            "- F: 자주 받는 질문(FAQ) ← 번호/불릿 목록 반드시 포함"
        ),
    },
]


# 시작 톤 5종
TONES: List[StyleBlock] = [
    {
        "code": "T-Numbers",
        "label": "현황·수치·문제의식",
        "cluster": "S1",
        "body": (
            "✦ 시작 톤 — 현황·수치·문제의식\n"
            "- 시장 동향·통계·수치로 시작 (예: \"최근 N년간 X 가 Y % 증가\")\n"
            "- 또는 핵심 문제·딜레마 한 문장으로 화두 제시\n"
            "- 격식 있는 도입, 감정 표현 배제"
        ),
    },
    {
        "code": "T-Learn",
        "label": "학습 목표 제시",
        "cluster": "S2",
        "body": (
            "✦ 시작 톤 — 학습 목표 제시\n"
            "- 이 글에서 배울 점·해결할 점을 한 문장으로 제시\n"
            "- \"이번 글에서는 ~를 살펴보겠습니다\" 같은 안내형\n"
            "- 독자에게 학습 동기를 만들어주는 톤"
        ),
    },
    {
        "code": "T-Empathy",
        "label": "독자 공감 상황",
        "cluster": "S3",
        "body": (
            "✦ 시작 톤 — 독자 공감 상황\n"
            "- 독자가 겪었을 법한 일상 상황으로 시작\n"
            "- \"이런 적 있지 않으세요?\", \"저도 같은 경험이 있어서~\"\n"
            "- 친근하고 가벼운 도입"
        ),
    },
    {
        "code": "T-Scene",
        "label": "장면·감정 묘사",
        "cluster": "S4",
        "body": (
            "✦ 시작 톤 — 장면·감정 묘사\n"
            "- 구체적인 시간·장소·날씨·분위기로 시작\n"
            "- 영화 도입부처럼 시각·청각·후각 디테일 한 문장\n"
            "- 본인 1인칭 시점, 회고체"
        ),
    },
    {
        "code": "T-Definition",
        "label": "정의·배경 설명",
        "cluster": "S5",
        "body": (
            "✦ 시작 톤 — 정의·배경 설명\n"
            "- 주제가 무엇인지 한 문장으로 정의\n"
            "- 또는 이 글에서 다룰 범위·관점을 명시\n"
            "- 담담한 정보 전달, 감정 표현 없음"
        ),
    },
]


COMMON_RULES: str = (
    "✦ 글쓰기 기본 원칙\n"
    "- 마크다운 작성\n"
    "- 제목(#~######) 앞 번호 금지, 특수문자 금지\n"
    "- 섹션 제목은 내용을 나타내는 자연어로 작성. "
    "A/B/C 같은 구조 라벨, STEP·단계 번호를 제목이나 본문에 절대 출력하지 말 것\n"
    "- \"STEP 1\", \"단계 1\" 같은 메타 텍스트와 구분선(─, ---) 출력 금지\n"
    "- 위 '구조 약속'의 표·목록 위치와 섹션 수를 정확히 지킬 것\n"
    "- STEP 1~4 멈추지 않고 한 번에 완성\n"
    "- 해시태그 금지"
)


STRUCTURE: str = (
    "✦ 구조 약속\n"
    "STEP 1 ▸ H1(#) 타이틀 + 도입 200자+ (위 시작톤 적용, \"안녕하세요\" 금지)\n"
    "STEP 2 ▸ ## 섹션 A·B·C 각 250자+ (B 표 필수, C 목록 필수)\n"
    "STEP 3 ▸ ## 섹션 D·E·F 각 250자+ (E 표 필수, F 목록 필수)\n"
    "STEP 4 ▸ ## 마치며 200자+ (담백한 정리 + 댓글·경험 공유 유도)"
)


DIVIDER: str = "─" * 40


def _find(items: List[StyleBlock], code: str) -> Optional[StyleBlock]:
    """code 로 블록 한 개 검색. 없으면 None."""
    for item in items:
        if item["code"] == code:
            return item
    return None


def build_prompt(
    persona_code: str,
    reader_code: str,
    pattern_code: str,
    tone_code: str,
) -> str:
    """4개 블록 코드를 받아 완성된 user_prompt_template 텍스트 반환.

    매칭 실패 시 해당 자리에 "(블록을 선택하세요)" 가 들어가 운영자가
    어디가 미선택인지 즉시 확인 가능하다.
    """
    persona = _find(PERSONAS, persona_code)
    reader = _find(READERS, reader_code)
    pattern = _find(PATTERNS, pattern_code)
    tone = _find(TONES, tone_code)

    placeholder = "(블록을 선택하세요)"
    persona_body = persona["body"] if persona else placeholder
    reader_body = reader["body"] if reader else placeholder
    pattern_body = pattern["body"] if pattern else placeholder
    tone_body = tone["body"] if tone else placeholder

    parts = [
        "제목: {title}",
        "카테고리: {category}",
        "키워드: {keywords}",
        "",
        DIVIDER,
        persona_body,
        DIVIDER,
        "",
        DIVIDER,
        reader_body,
        DIVIDER,
        "",
        DIVIDER,
        COMMON_RULES,
        DIVIDER,
        "",
        DIVIDER,
        pattern_body,
        DIVIDER,
        "",
        DIVIDER,
        tone_body,
        DIVIDER,
        "",
        DIVIDER,
        STRUCTURE,
        DIVIDER,
    ]
    return "\n".join(parts)


# 빠른 적용 프리셋 (modules.md 의 V1 카탈로그를 그대로 코드화)
# 각 프리셋은 (페르소나·독자수준·섹션패턴·시작톤) 4개 코드와 어울리는
# 카테고리 표기를 함께 갖는다.
PRESETS: List[Dict[str, str]] = [
    {
        "code": "s1-v1",
        "label": "S1 V1 · 전문가·중급·P1·수치",
        "categories": "AI · 인공지능 · IT · 개발 · 과학",
        "persona": "P-Expert",
        "reader": "R-Intermediate",
        "pattern": "P1",
        "tone": "T-Numbers",
    },
    {
        "code": "s1-v2",
        "label": "S1 V2 · 분석가·결정·P4·수치",
        "categories": "금융 · 투자 · 부동산 · 경제",
        "persona": "P-Analyst",
        "reader": "R-Decision",
        "pattern": "P4",
        "tone": "T-Numbers",
    },
    {
        "code": "s2-v1",
        "label": "S2 V1 · 선생님·입문·P2·학습",
        "categories": "건강 · 의학 · 영양 · 자기계발",
        "persona": "P-Teacher",
        "reader": "R-Beginner",
        "pattern": "P2",
        "tone": "T-Learn",
    },
    {
        "code": "s2-v2",
        "label": "S2 V2 · 선생님·입문·P3·학습",
        "categories": "육아 · 교육 · 자격증 · 어학",
        "persona": "P-Teacher",
        "reader": "R-Beginner",
        "pattern": "P3",
        "tone": "T-Learn",
    },
    {
        "code": "s3-v1",
        "label": "S3 V1 · 친구·입문·P5·공감",
        "categories": "라이프 · 인테리어 · 홈가전 · 반려동물",
        "persona": "P-Friend",
        "reader": "R-Beginner",
        "pattern": "P5",
        "tone": "T-Empathy",
    },
    {
        "code": "s3-v2",
        "label": "S3 V2 · 친구·입문·P2·공감",
        "categories": "패션 · 뷰티 · 쇼핑 · 직구",
        "persona": "P-Friend",
        "reader": "R-Beginner",
        "pattern": "P2",
        "tone": "T-Empathy",
    },
    {
        "code": "s4-v1",
        "label": "S4 V1 · 에세이·중급·P5·장면",
        "categories": "여행 · 맛집 · 카페 · 음식",
        "persona": "P-Essayist",
        "reader": "R-Intermediate",
        "pattern": "P5",
        "tone": "T-Scene",
    },
    {
        "code": "s4-v2",
        "label": "S4 V2 · 에세이·중급·P3·장면",
        "categories": "문화 · 영화 · 드라마 · 책",
        "persona": "P-Essayist",
        "reader": "R-Intermediate",
        "pattern": "P3",
        "tone": "T-Scene",
    },
    {
        "code": "s5-v1",
        "label": "S5 V1 · 중립·중급·P1·정의",
        "categories": "자동차 · 가전 · 제품 리뷰",
        "persona": "P-Neutral",
        "reader": "R-Intermediate",
        "pattern": "P1",
        "tone": "T-Definition",
    },
    {
        "code": "s5-v2",
        "label": "S5 V2 · 중립·중급·P4·정의",
        "categories": "앱 · 서비스 · DIY · 취미",
        "persona": "P-Neutral",
        "reader": "R-Intermediate",
        "pattern": "P4",
        "tone": "T-Definition",
    },
]


def blocks_for_template() -> Dict[str, object]:
    """Jinja2 템플릿에 전달할 dict.

    JS 측에서 JSON 으로 받아 라디오/셀렉트 옵션 렌더링과 본문 조립에
    사용한다.
    """
    return {
        "personas": PERSONAS,
        "readers": READERS,
        "patterns": PATTERNS,
        "tones": TONES,
        "presets": PRESETS,
        "common_rules": COMMON_RULES,
        "structure": STRUCTURE,
        "divider": DIVIDER,
    }
