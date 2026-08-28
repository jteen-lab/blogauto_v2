"""니치별 프리셋 카탈로그 — 하위 주제 단위 (2026-08-28 세분화).

설계 원칙
    1. **하위 주제 재고 기준.** 제목이 실제로 쌓여 있는 하위 주제를 덮는다.
       재고 0인 하위 주제만 있는 조합은 별도 프리셋을 만들지 않고 상위에 흡수한다.
    2. **프리셋마다 다른 사람이 쓴 것처럼.** 같은 주제군이라도 화자·시작톤·구조를
       서로 다르게 걸어, 결과물의 문장과 전개가 갈리도록 한다.
       (조합만 재사용하면 26개를 만들어도 비슷한 글이 나온다)
    3. **YMYL 표시.** 돈·건강·안전 주제는 C-YMYL 원칙을 함께 건다.

괄호 안 숫자는 2026-08-28 기준 제목 재고.
"""
from __future__ import annotations

from typing import Dict, List

NICHE_PRESETS: List[Dict[str, object]] = [
    # ── 금융/대출 (951) — 재고 최다라 성격별로 넷으로 나눈다 ──────────
    {
        "code": "n-loan-credit",
        "label": "💳 신용대출·대출정보 · 상담창구/결정·P4·사례",
        "categories": "금융/대출 › 신용대출(255) · 대출 정보(342) · 금리·상환",
        "match_topics": ['금융/대출'],
        "match_subtopics": ['신용대출', '대출 정보', '금리·상환'],
        "persona": "P-Counselor", "reader": "R-Decision",
        "pattern": "P4", "tone": "T-Case", "common": "C-YMYL",
    },
    {
        "code": "n-loan-home",
        "label": "🏠 주택담보·전세자금 · 분석가/결정·P6·오해정정",
        "categories": "금융/대출 › 주택담보대출(53) · 전세자금대출(47)",
        "match_topics": ['금융/대출'],
        "match_subtopics": ['주택담보대출', '전세자금대출'],
        "persona": "P-Analyst", "reader": "R-Decision",
        "pattern": "P6", "tone": "T-Warning", "common": "C-YMYL",
    },
    {
        "code": "n-loan-policy",
        "label": "🏛 정책금융·사업자대출 · 안내자/신청자·P6·자격확인",
        "categories": "금융/대출 › 정책금융(39) · 사업자대출(33)",
        "match_topics": ['금융/대출'],
        "match_subtopics": ['정책금융', '사업자대출'],
        "persona": "P-Guide", "reader": "R-Applicant",
        "pattern": "P6", "tone": "T-Eligibility", "common": "C-YMYL",
    },
    {
        "code": "n-loan-card",
        "label": "💳 카드·리볼빙·신용점수 · 상담창구/입문·P1·오해정정",
        "categories": "금융/대출 › 카드·리볼빙(24) · 신용점수·관리(13) · 금융 정보(138)",
        "match_topics": ['금융/대출'],
        "match_subtopics": ['카드·리볼빙', '신용점수·관리', '금융 정보'],
        "persona": "P-Counselor", "reader": "R-Beginner",
        "pattern": "P1", "tone": "T-Warning", "common": "C-YMYL",
    },

    # ── 보험 (36) ────────────────────────────────────────────
    {
        "code": "n-ins-auto",
        "label": "🚘 자동차·화재보험 · 분석가/결정·P4·선택지대비",
        "categories": "보험 › 자동차보험(19) · 화재·주택보험 · 실손의료보험",
        "match_topics": ['보험'],
        "match_subtopics": ['자동차보험', '화재·주택보험', '실손의료보험'],
        "persona": "P-Analyst", "reader": "R-Decision",
        "pattern": "P4", "tone": "T-Compare", "common": "C-YMYL",
    },
    {
        "code": "n-ins-claim",
        "label": "📄 보험금 청구·해지 · 안내자/신청자·P6·사례",
        "categories": "보험 › 보험금 청구(10) · 해지·환급 · 암·건강보험",
        "match_topics": ['보험'],
        "match_subtopics": ['보험금 청구', '해지·환급', '암·건강보험'],
        "persona": "P-Guide", "reader": "R-Applicant",
        "pattern": "P6", "tone": "T-Case", "common": "C-YMYL",
    },

    # ── 세금/절세 (15) ───────────────────────────────────────
    {
        "code": "n-tax",
        "label": "🧾 연말정산·종합소득세 · 안내자/신청자·P6·오해정정",
        "categories": "세금/절세 › 연말정산(6) · 종합소득세(3) · 사업자 세무(3) · 양도·상속",
        "match_topics": ['세금/절세'],
        "match_subtopics": ['연말정산', '종합소득세', '사업자 세무', '양도·상속'],
        "persona": "P-Guide", "reader": "R-Applicant",
        "pattern": "P6", "tone": "T-Warning", "common": "C-YMYL",
    },

    # ── 재테크/돈관리 (167) ──────────────────────────────────
    {
        "code": "n-invest",
        "label": "📈 주식·ETF·토큰증권 · 분석가/중급·P1·수치",
        "categories": "재테크/돈관리 › 토큰 증권(96) · 주식(21) · ETF투자(18)",
        "match_topics": ['재테크/돈관리'],
        "match_subtopics": ['토큰 증권', '주식', 'ETF투자'],
        "persona": "P-Analyst", "reader": "R-Intermediate",
        "pattern": "P1", "tone": "T-Numbers", "common": "C-YMYL",
    },
    {
        "code": "n-saving",
        "label": "🐷 적금·예금·가계부 · 같은처지선배/입문·P2·사례",
        "categories": "재테크/돈관리 › 적금/예금(23) · 절약·가계부 · 월급 관리 · 앱테크",
        "match_topics": ['재테크/돈관리'],
        "match_subtopics": ['적금/예금', '절약·가계부', '월급 관리', '앱테크'],
        "persona": "P-Peer", "reader": "R-Beginner",
        "pattern": "P2", "tone": "T-Case", "common": "C-YMYL",
    },

    # ── 시니어·부동산 ────────────────────────────────────────
    {
        "code": "n-senior",
        "label": "👵 연금·노후·노인복지 · 같은처지선배/입문·P2·자격확인",
        "categories": "시니어/노후 › 연금(7) · 노인복지(3) · 요양·돌봄",
        "match_topics": ['시니어/노후'],
        "match_subtopics": ['연금', '노인복지', '요양·돌봄'],
        "persona": "P-Peer", "reader": "R-Beginner",
        "pattern": "P2", "tone": "T-Eligibility", "common": "C-YMYL",
    },
    {
        "code": "n-realestate",
        "label": "🏘 부동산 매매·전월세 · 분석가/결정·P4·오해정정",
        "categories": "부동산 › 매매·청약 · 전월세 계약 · 세금·비용 · 전세사기 예방",
        "match_topics": ['부동산'],
        "match_subtopics": ['매매·청약', '전월세 계약', '세금·비용', '전세사기 예방'],
        "persona": "P-Analyst", "reader": "R-Decision",
        "pattern": "P4", "tone": "T-Warning", "common": "C-YMYL",
    },

    # ── 정부지원금/복지 (54) ─────────────────────────────────
    {
        "code": "n-welfare",
        "label": "🏛 정부 정책·지원금 · 취재기자/신청자·P6·자격확인",
        "categories": "정부지원금/복지 › 정부 정책·제도(29) · 육아·소상공인·에너지·청년 지원",
        "match_topics": ['정부지원금/복지'],
        "match_subtopics": ['정부 정책·제도', '육아·소상공인·에너지·청년 지원'],
        "persona": "P-Reporter", "reader": "R-Applicant",
        "pattern": "P6", "tone": "T-Eligibility", "common": "C-YMYL",
    },

    # ── 건강/의학 (260) — 성격이 크게 갈려 셋으로 ─────────────
    {
        "code": "n-health-symptom",
        "label": "🩺 증상·자가진단 · 임상설명자/입문·P7·증상묘사",
        "categories": "건강/의학 › 질병 및 증상(122) · 증상·자가진단(14) · 통증 관리",
        "match_topics": ['건강/의학'],
        "match_subtopics": ['질병 및 증상', '증상·자가진단', '통증 관리'],
        "persona": "P-Clinician", "reader": "R-Beginner",
        "pattern": "P7", "tone": "T-Symptom", "common": "C-YMYL",
    },
    {
        "code": "n-health-care",
        "label": "💊 치료·처방·예방 · 임상설명자/중급·P2·오해정정",
        "categories": "건강/의학 › 치료·처방(44) · 예방·관리 · 병원·진료 · 영양제",
        "match_topics": ['건강/의학'],
        "match_subtopics": ['치료·처방', '예방·관리', '병원·진료', '영양제'],
        "persona": "P-Clinician", "reader": "R-Intermediate",
        "pattern": "P2", "tone": "T-Warning", "common": "C-YMYL",
    },
    {
        "code": "n-health-diet",
        "label": "🏃 다이어트·운동·멘탈 · 친구/입문·P5·공감",
        "categories": "건강/의학 › 비만·다이어트(66) · 운동 · 멘탈 관리",
        "match_topics": ['건강/의학'],
        "match_subtopics": ['비만·다이어트', '운동', '멘탈 관리'],
        "persona": "P-Friend", "reader": "R-Beginner",
        "pattern": "P5", "tone": "T-Empathy", "common": "C-YMYL",
    },

    # ── 출산/육아 (31) ───────────────────────────────────────
    {
        "code": "n-parenting",
        "label": "👶 육아·출산 준비 · 같은처지선배/입문·P5·공감",
        "categories": "출산/육아 › 육아팁(24) · 출산 준비 · 임신·영유아 건강",
        "match_topics": ['출산/육아'],
        "match_subtopics": ['육아팁', '출산 준비', '임신·영유아 건강'],
        "persona": "P-Peer", "reader": "R-Beginner",
        "pattern": "P5", "tone": "T-Empathy", "common": "C-YMYL",
    },

    # ── 취업/자격증 (113) ────────────────────────────────────
    {
        "code": "n-job",
        "label": "🔎 구인구직·취업정보 · 같은처지선배/신청자·P3·사례",
        "categories": "취업/자격증 › 구인구직 사이트(65) · 취업 정보(30) · 연봉·처우",
        "match_topics": ['취업/자격증'],
        "match_subtopics": ['구인구직 사이트', '취업 정보', '연봉·처우'],
        "persona": "P-Peer", "reader": "R-Applicant",
        "pattern": "P3", "tone": "T-Case",
    },
    {
        "code": "n-cert",
        "label": "🎓 자격증·시험 준비 · 선생님/입문·P3·학습",
        "categories": "취업/자격증 › 자격증(14) · 직업 정보 · 면접·자소서",
        "match_topics": ['취업/자격증'],
        "match_subtopics": ['자격증', '직업 정보', '면접·자소서'],
        "persona": "P-Teacher", "reader": "R-Beginner",
        "pattern": "P3", "tone": "T-Learn",
    },

    # ── 생활 정보 (774) — 재고 2위, 성격이 갈려 셋으로 ────────
    {
        "code": "n-life-howto",
        "label": "🧰 생활 노하우·꿀팁 · 중립/입문·P3·장면",
        "categories": "생활 정보 › 노하우/꿀팁(162) · 생활 정보(373)",
        "match_topics": ['생활 정보'],
        "match_subtopics": ['노하우/꿀팁', '생활 정보'],
        "persona": "P-Neutral", "reader": "R-Beginner",
        "pattern": "P3", "tone": "T-Scene",
    },
    {
        "code": "n-life-contact",
        "label": "📞 고객센터·매장 정보 · 정보정리자/입문·P9·결론부터",
        "categories": "생활 정보 › 고객센터·연락처(102) · 매장·시설 정보(50)",
        "match_topics": ['생활 정보'],
        "match_subtopics": ['고객센터·연락처', '매장·시설 정보'],
        "persona": "P-Curator", "reader": "R-Beginner",
        "pattern": "P9", "tone": "T-Answer",
    },
    {
        "code": "n-life-admin",
        "label": "🏢 행정·공과금·교통·통신 · 안내자/신청자·P6·결론부터",
        "categories": "생활 정보 › 행정·증명서 · 공과금·관리비 · 교통·이동 · 통신·인터넷",
        "match_topics": ['생활 정보'],
        "match_subtopics": ['행정·증명서', '공과금·관리비', '교통·이동', '통신·인터넷'],
        "persona": "P-Guide", "reader": "R-Applicant",
        "pattern": "P6", "tone": "T-Answer",
    },

    # ── 여행/관광 (377) ──────────────────────────────────────
    {
        "code": "n-travel-season",
        "label": "🌤 여행 날씨·시기 · 다녀온사람/중급·P1·계절맥락",
        "categories": "여행/관광 › 여행 날씨·시기(160) · 여행 경비·예산 · 준비물",
        "match_topics": ['여행/관광'],
        "match_subtopics": ['여행 날씨·시기', '여행 경비·예산', '준비물'],
        "persona": "P-Traveler", "reader": "R-Intermediate",
        "pattern": "P1", "tone": "T-Season",
    },
    {
        "code": "n-travel-place",
        "label": "✈️ 여행지·숙소·교통 · 에세이/중급·P5·장면",
        "categories": "여행/관광 › 여행 정보(148) · 숙소·호텔(38) · 국내외 여행지 · 여행 교통",
        "match_topics": ['여행/관광'],
        "match_subtopics": ['여행 정보', '숙소·호텔', '국내외 여행지', '여행 교통'],
        "persona": "P-Essayist", "reader": "R-Intermediate",
        "pattern": "P5", "tone": "T-Scene",
    },

    # ── 음식/레시피 (166) ────────────────────────────────────
    {
        "code": "n-food-recipe",
        "label": "🍳 요리 레시피·조리법 · 주방실무자/입문·P8·장면",
        "categories": "음식/레시피 › 요리 레시피(77) · 조리법·손질 · 보관·저장",
        "match_topics": ['음식/레시피'],
        "match_subtopics": ['요리 레시피', '조리법·손질', '보관·저장'],
        "persona": "P-Cook", "reader": "R-Beginner",
        "pattern": "P8", "tone": "T-Scene",
    },
    {
        "code": "n-food-effect",
        "label": "🥬 식재료·음식 효능 · 전문가/입문·P2·정의",
        "categories": "음식/레시피 › 식재료 효능(40) · 음식 효능(34) · 부작용·주의",
        "match_topics": ['음식/레시피'],
        "match_subtopics": ['식재료 효능', '음식 효능', '부작용·주의'],
        "persona": "P-Expert", "reader": "R-Beginner",
        "pattern": "P2", "tone": "T-Definition", "common": "C-YMYL",
    },

    # ── 컴퓨터/IT · AI ───────────────────────────────────────
    {
        "code": "n-pc",
        "label": "🖥 PC·윈도우 문제해결 · 문제해결사/입문·P7·증상묘사",
        "categories": "컴퓨터/IT › PC·윈도우(32) · 주변기기 · 프로그램·오피스 · 인터넷·보안",
        "match_topics": ['컴퓨터/IT'],
        "match_subtopics": ['PC·윈도우', '주변기기', '프로그램·오피스', '인터넷·보안'],
        "persona": "P-Fixer", "reader": "R-Beginner",
        "pattern": "P7", "tone": "T-Symptom",
    },
    {
        "code": "n-ai",
        "label": "🤖 생성형AI·AI 도구 · 전문가/중급·P1·정의",
        "categories": "AI/인공지능 › 생성형AI(19) · AI 도구(14) · AI 기술 이해",
        "match_topics": ['AI/인공지능'],
        "match_subtopics": ['생성형AI', 'AI 도구', 'AI 기술 이해'],
        "persona": "P-Expert", "reader": "R-Intermediate",
        "pattern": "P1", "tone": "T-Definition",
    },

    # ── 자동차 · 쇼핑/리뷰 ───────────────────────────────────
    {
        "code": "n-car",
        "label": "🚗 자동차 구매·정비 · 전문가/결정·P1·수치",
        "categories": "자동차 › 전기·친환경차(8) · 신차·구매(6) · 정비·소모품 · 과태료·법규",
        "match_topics": ['자동차'],
        "match_subtopics": ['전기·친환경차', '신차·구매', '정비·소모품', '과태료·법규'],
        "persona": "P-Expert", "reader": "R-Decision",
        "pattern": "P1", "tone": "T-Numbers",
    },
    {
        "code": "n-shopping",
        "label": "🛒 가격 비교·제품 정보 · 중립/결정·P4·선택지대비",
        "categories": "쇼핑/리뷰 › 가격 비교(15) · 제품 정보(7)",
        "match_topics": ['쇼핑/리뷰'],
        "match_subtopics": ['가격 비교', '제품 정보'],
        "persona": "P-Neutral", "reader": "R-Decision",
        "pattern": "P4", "tone": "T-Compare",
    },

    # ── 지역/업체정보 ────────────────────────────────────────
    {
        "code": "n-local",
        "label": "🌸 지역 업체·서비스 · 중립/결정·P9·선택지대비",
        "categories": "지역/업체정보 › 꽃배달(14) · 장례·예식 · 이사·청소 · 수리·시공",
        "match_topics": ['지역/업체정보'],
        "match_subtopics": ['꽃배달', '장례·예식', '이사·청소', '수리·시공'],
        "persona": "P-Neutral", "reader": "R-Decision",
        "pattern": "P9", "tone": "T-Compare",
    },
]
