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

# 프리셋 카탈로그는 별도 모듈로 분리(500줄 제한). 재-export 로 공개 API 불변(B.PRESETS).
from .presets import PRESETS  # noqa: F401  (re-export)


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


# 글쓰기 기본 원칙 — 블로그별 문체 차별화를 위해 선택형 축으로 제공.
# 스타일(이모지·어투)만 다르고, 구조 무결성 규칙(자연어 제목·STEP/구분선 미출력·
# 표/목록 위치 준수·한 번에 완성)은 모든 옵션이 공통으로 유지한다.
COMMONS: List[StyleBlock] = [
    {
        "code": "C-Default",
        "label": "기본 (이모지 없음)",
        "cluster": "",
        "body": (
            "✦ 글쓰기 기본 원칙\n"
            "- 마크다운 작성\n"
            "- 제목(#~######) 앞 번호 금지, 특수문자 금지\n"
            "- 섹션 제목은 내용을 나타내는 자연어로 작성. "
            "A/B/C 같은 구조 라벨, STEP·단계 번호를 제목이나 본문에 절대 출력하지 말 것\n"
            "- \"STEP 1\", \"단계 1\" 같은 메타 텍스트와 구분선(─, ---) 출력 금지\n"
            "- 위 '구조 약속'의 표·목록 위치와 섹션 수를 정확히 지킬 것\n"
            "- STEP 1~4 멈추지 않고 한 번에 완성\n"
            "- 해시태그 금지"
        ),
    },
    {
        "code": "C-Emoji",
        "label": "이모지 강조형",
        "cluster": "",
        "body": (
            "✦ 글쓰기 기본 원칙 (이모지 강조형)\n"
            "- 마크다운 작성\n"
            "- 각 ## 섹션 제목 맨 앞에 내용에 어울리는 이모지 1개 배치 (예: \"## 📌 준비물\")\n"
            "- 본문의 핵심 포인트·팁에 이모지를 적절히 사용해 가독성 강조 (남용 금지)\n"
            "- 제목(#~######) 앞 번호 금지, 섹션 제목은 자연어로. "
            "A/B/C 구조 라벨·STEP·단계 번호를 제목이나 본문에 절대 출력하지 말 것\n"
            "- \"STEP 1\", \"단계 1\" 같은 메타 텍스트와 구분선(─, ---) 출력 금지\n"
            "- 위 '구조 약속'의 표·목록 위치와 섹션 수를 정확히 지킬 것\n"
            "- 처음부터 끝까지 멈추지 않고 한 번에 완성\n"
            "- 해시태그 금지"
        ),
    },
    {
        "code": "C-Plain",
        "label": "간결·담백형",
        "cluster": "",
        "body": (
            "✦ 글쓰기 기본 원칙 (간결·담백형)\n"
            "- 마크다운 작성, 이모지·과장 표현 없이 담백하게\n"
            "- 문장은 짧고 명료하게, 군더더기 수식어 배제\n"
            "- 제목(#~######) 앞 번호·특수문자 금지, 섹션 제목은 자연어로. "
            "A/B/C 구조 라벨·STEP·단계 번호를 제목이나 본문에 절대 출력하지 말 것\n"
            "- \"STEP 1\", \"단계 1\" 같은 메타 텍스트와 구분선(─, ---) 출력 금지\n"
            "- 위 '구조 약속'의 표·목록 위치와 섹션 수를 정확히 지킬 것\n"
            "- 처음부터 끝까지 멈추지 않고 한 번에 완성\n"
            "- 해시태그 금지"
        ),
    },
    {
        "code": "C-Story",
        "label": "경험·스토리텔링형",
        "cluster": "",
        "body": (
            "✦ 글쓰기 기본 원칙 (스토리텔링형)\n"
            "- 마크다운 작성, 실제 경험담·구체적 사례를 녹여 친근하게\n"
            "- 독자에게 말을 건네는 대화체 허용 (단, 반말 금지)\n"
            "- 이모지는 감정 강조에만 가볍게 사용 (선택)\n"
            "- 제목(#~######) 앞 번호 금지, 섹션 제목은 자연어로. "
            "A/B/C 구조 라벨·STEP·단계 번호를 제목이나 본문에 절대 출력하지 말 것\n"
            "- \"STEP 1\", \"단계 1\" 같은 메타 텍스트와 구분선(─, ---) 출력 금지\n"
            "- 위 '구조 약속'의 표·목록 위치와 섹션 수를 정확히 지킬 것\n"
            "- 처음부터 끝까지 멈추지 않고 한 번에 완성\n"
            "- 해시태그 금지"
        ),
    },
]

# 품질 블록(F7) — 애드센스 정보이득 지시문. 옵트인(선택/자동주입).
# Q-None 은 "미적용"(기본), Q-AdsenseGain 이 실제 지시문.
QUALITY: List[StyleBlock] = [
    {
        "code": "Q-None",
        "label": "미적용 (기본)",
        "cluster": "",
        "body": "",
    },
    {
        "code": "Q-AdsenseGain",
        "label": "정보이득 지시문 (애드센스 승인 대비)",
        "cluster": "",
        "body": (
            "✦ 정보이득 지시문 (애드센스 승인 대비)\n"
            "- 공개된 정보를 그대로 재배열/요약만 하지 말 것. 각 섹션에 아래 중 최소 "
            "1개 이상 포함:\n"
            "  (a) 서로 다른 조건/상황을 비교한 구체적 판단 기준\n"
            "  (b) 실제 적용 시 흔히 놓치는 주의점·예외 상황\n"
            "  (c) 수치·기간·조건 등 검증 가능한 구체 정보"
            "(예: \"2026년 기준\", \"3개월 이상 유지 시\")\n"
            "- 표·목록은 정보 나열이 아니라 \"무엇을 고를지 판단하는 근거\"가 드러나게 "
            "구성 (예: 단순 스펙 나열 대신 \"이런 경우엔 A, 저런 경우엔 B\")\n"
            "- 가능한 경우 한 문장 이상 출처를 명시 (예: \"OO 기관 발표에 따르면\"). "
            "없는 통계·수치를 지어내지 말 것 — 확인 불가 시 정성적 표현으로 대체\n"
            "- 뻔한 결론/광고성 마무리 문구(\"꼭 확인해보세요!\" 같은 공허한 CTA) 지양, "
            "실행 가능한 다음 행동 하나로 마무리"
        ),
    },
    {
        "code": "Q-AEO",
        "label": "AI 답변 인용 대비 (AEO/GEO)",
        "cluster": "",
        "body": (
            "✦ AI 답변에 인용되도록 쓰기 (AEO/GEO)\n"
            "- **즉답 먼저**: 도입 첫 2~3문장 안에 제목이 묻는 것의 답을 결론부터 제시. "
            "배경 설명·인사말로 시작하지 말 것\n"
            "- **소제목은 질문형 또는 명사구로**: 검색창에 실제로 칠 법한 표현을 쓰고, "
            "각 소제목 바로 아래 첫 문장에서 그 질문에 답할 것\n"
            "- **비교 표 1개 이상**: 단순 나열이 아니라 \"어떤 경우에 무엇을 고르는가\"가 "
            "드러나는 표. 열은 조건/대상/선택 근거 형태로 구성\n"
            "- **수치는 키-값 형태로**: 핵심 사실(금액·기간·조건·대상)은 산문에 묻지 말고 "
            "표나 \"항목: 값\" 줄로 분리할 것. 기계가 값을 그대로 집어가기 쉬워진다\n"
            "- **기준일과 산출 근거를 붙일 것**: 숫자를 쓸 때 언제 기준인지, 무엇으로 "
            "계산했는지 함께 적는다. 예) \"월 최대 24만원(2026년 기준, 소득 4분위 이하)\". "
            "기준 없는 숫자는 인용되지 않는다\n"
            "- **자주 묻는 질문 3~5개**: 위 구조의 마지막 섹션이 이미 FAQ 성격이면 "
            "그 섹션을 이 질문들로 채우고, 아니라면 **위 구조를 바꾸지 말고 맨 뒤에 "
            "FAQ 블록을 따로 덧붙일 것**. 각 질문은 이 글 주제에서 실제로 갈리는 "
            "지점이어야 하며(형식적 질문 금지), 답변은 2~4문장으로 그 자체만 읽어도 "
            "완결되게 작성\n"
            "- **한 문단 한 주장**: 문단을 3~5문장으로 끊고 첫 문장에 요지를 둘 것. "
            "AI가 문단 단위로 인용하기 쉬워진다\n"
            "- 같은 사실을 글 안에서 서로 다르게 서술하지 말 것(수치·조건 일관성)"
        ),
    },
]

# 애드센스 정보이득 지시문 — 자동 주입(content_generator)이 참조하는 SoT.
ADSENSE_GAIN_CODE: str = "Q-AdsenseGain"
# AEO/GEO 지시문 코드
AEO_CODE: str = "Q-AEO"


def adsense_gain_directive() -> str:
    """애드센스 정보이득 지시문 본문 반환(SoT). 없으면 빈 문자열."""
    block = _find(QUALITY, ADSENSE_GAIN_CODE)
    return block["body"] if block else ""


def aeo_directive() -> str:
    """AEO/GEO 지시문 본문 반환(SoT). 없으면 빈 문자열.

    정보이득(Q-AdsenseGain)과 축이 다르다. 정보이득은 **무엇을 쓸지**(고유 관점·
    검증 가능한 정보)를, 이쪽은 **어떤 형태로 쓸지**(즉답·질문형 소제목·표·FAQ)를
    다룬다. 둘을 함께 켜도 지시가 충돌하지 않는다.
    """
    block = _find(QUALITY, AEO_CODE)
    return block["body"] if block else ""


# 니치 특화 블록 병합(2026-08-28). blocks.py 500줄 제한 때문에 별도 파일로 분리했다.
# 운영 방침이 다니치 → 니치 특화 블로그로 바뀌면서 절차·신청형과 YMYL 서술이 필요해졌다.
from .blocks_niche import (  # noqa: E402
    NICHE_COMMONS, NICHE_PATTERNS, NICHE_PERSONAS, NICHE_READERS, NICHE_TONES,
)

# 목소리 확장(2026-08-28). 프리셋을 하위 주제 단위로 세분화하면서, 조합만 바꿔서는
# 글의 분위기가 갈리지 않아 화자·시작톤·구조 자체를 늘렸다.
from .blocks_voice import (  # noqa: E402
    VOICE_PATTERNS, VOICE_PERSONAS, VOICE_TONES,
)

PERSONAS.extend(NICHE_PERSONAS)
PERSONAS.extend(VOICE_PERSONAS)
READERS.extend(NICHE_READERS)
PATTERNS.extend(NICHE_PATTERNS)
PATTERNS.extend(VOICE_PATTERNS)
TONES.extend(NICHE_TONES)
TONES.extend(VOICE_TONES)
COMMONS.extend(NICHE_COMMONS)


# 하위호환 별칭 — build_prompt()·blocks_for_template()·__init__ export 가 참조.
COMMON_RULES: str = COMMONS[0]["body"]


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
    quality_code: Optional[str] = None,
) -> str:
    """블록 코드들을 받아 완성된 user_prompt_template 텍스트 반환.

    매칭 실패 시 해당 자리에 "(블록을 선택하세요)" 가 들어가 운영자가
    어디가 미선택인지 즉시 확인 가능하다. quality_code 는 선택 인자로,
    지정 시(예: Q-AdsenseGain) 정보이득 지시문을 STRUCTURE 앞에 삽입한다.
    미지정/Q-None 이면 기존과 동일 출력(하위호환).
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
    ]

    # 품질 블록(선택) — 정보이득 지시문. 본문이 있을 때만 삽입.
    quality = _find(QUALITY, quality_code) if quality_code else None
    if quality and quality["body"]:
        parts += ["", DIVIDER, quality["body"], DIVIDER]

    parts += ["", DIVIDER, STRUCTURE, DIVIDER]
    return "\n".join(parts)


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
        "commons": COMMONS,
        "quality": QUALITY,
        "presets": PRESETS,
        "common_rules": COMMON_RULES,
        "structure": STRUCTURE,
        "divider": DIVIDER,
    }
