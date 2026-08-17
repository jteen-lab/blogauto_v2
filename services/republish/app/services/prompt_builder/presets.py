"""프롬프트 빌더 빠른 적용 프리셋 카탈로그.

blocks.py 500줄 제한 준수를 위해 프리셋 데이터를 분리했다.
각 프리셋은 (페르소나·독자수준·섹션패턴·시작톤) 4개 코드와 어울리는
카테고리 표기를 함께 갖는다(modules.md V1 카탈로그를 코드화).
blocks.py 가 `from .presets import PRESETS` 로 재-export 하므로 공개 API 불변.
"""
from __future__ import annotations

from typing import Dict, List

PRESETS: List[Dict[str, object]] = [
    # F11 애드센스 승인용 고정 프리셋(2026-08-17). 적용 시 정보이득(F7) 토글
    # 자동 ON + 문체·옵션 편집 잠금(승인 테스트용 고정). 프롬프트 빌더에 별도
    # 축을 만들지 않고 이 프리셋 하나로만 제공. 순서도 adsense_f11_prompt_preset.md.
    {
        "code": "adsense-approval",
        "label": "🔒 애드센스 승인용 (고정)",
        "categories": "애드센스 승인 대비 — 근거·비교·출처 강조",
        "persona": "P-Analyst",
        "reader": "R-Intermediate",
        "pattern": "P1",
        "tone": "T-Numbers",
        "info_gain": True,   # 적용 시 정보이득 지시문(F7) 토글 자동 ON
        "locked": True,      # 문체·옵션 편집 잠금(수정 불가)
    },
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
