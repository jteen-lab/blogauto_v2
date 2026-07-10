/**
 * 프롬프트 빌더 - 구조 약속 순수 함수
 * File: app/static/js/prompt_builder/structure.js
 *
 * '구조 약속(✦)'과 섹션 파싱을 패턴 본문 단일 진실원천으로 생성한다.
 * app.js(Alpine 컴포넌트)가 이 전역 함수를 호출해 크기를 500줄 이하로 유지.
 */

/**
 * 최종 패턴 본문을 파싱해 섹션을 순서대로 반환.
 * 패턴 본문의 '- A: ... ← 표 반드시 포함' 형식을 읽어 각 섹션의 역할을 판별한다.
 * @param {string} patternBody - 최종 패턴 본문(빌트인 재배치본 또는 커스텀 원문)
 * @returns {Array<{letter:string, role:string}>} role: 'table' | 'list' | 'other'
 */
function pbParsePatternSections(patternBody) {
    const re = /^\s*-\s*([A-Z]):\s*(.+)$/;
    const out = [];
    for (const raw of String(patternBody || '').split('\n')) {
        const m = raw.match(re);
        if (!m) continue;
        let role = 'other';
        if (/←\s*표/.test(raw)) role = 'table';
        else if (/←.*목록/.test(raw)) role = 'list';
        out.push({ letter: m[1], role });
    }
    return out;
}

/**
 * 파싱된 섹션과 글자수 설정으로 '구조 약속' 텍스트를 생성.
 * - 섹션 수·표/목록 위치는 전적으로 파싱된 섹션(=패턴 본문)에서 유도 → 패턴과 항상 일치.
 * - 글자수는 설정값 사용(하드코딩 제거).
 * - 마지막에 정확한 섹션 수를 절대 규칙으로 명시.
 * @param {Array<{letter:string, role:string}>} sections
 * @param {{introChars:number, sectionChars:number, outroChars:number}} opts
 * @returns {string} 구조 약속 텍스트
 */
function pbBuildStructure(sections, opts) {
    const intro = (opts && opts.introChars) || 200;
    const sec = (opts && opts.sectionChars) || 250;
    const outro = (opts && opts.outroChars) || 200;
    const introLine = 'STEP 1 ▸ H1(#) 타이틀 + 도입 ' + intro + '자+ (위 시작톤 적용, "안녕하세요" 금지)';
    const outroLine = (step) => `STEP ${step} ▸ ## 마치며 ${outro}자+ (담백한 정리 + 댓글·경험 공유 유도)`;

    const secs = Array.isArray(sections) ? sections : [];
    if (secs.length === 0) {
        return ['✦ 구조 약속', introLine,
            `STEP 2 ▸ ## 본문 섹션 각 ${sec}자+ (패턴 본문의 각 항목대로 작성)`,
            outroLine(3)].join('\n');
    }

    const note = (slice) => {
        const notes = [];
        slice.forEach(s => {
            if (s.role === 'table') notes.push(`${s.letter} 표 필수`);
            else if (s.role === 'list') notes.push(`${s.letter} 목록 필수`);
        });
        return notes.length ? ` (${notes.join(', ')})` : '';
    };
    const L = (arr) => arr.map(s => s.letter).join('·');
    const mid = Math.ceil(secs.length / 2);
    const front = secs.slice(0, mid), back = secs.slice(mid);

    const lines = ['✦ 구조 약속', introLine,
        `STEP 2 ▸ ## 섹션 ${L(front)} 각 ${sec}자+${note(front)}`];
    if (back.length) {
        lines.push(`STEP 3 ▸ ## 섹션 ${L(back)} 각 ${sec}자+${note(back)}`);
        lines.push(outroLine(4));
    } else {
        lines.push(outroLine(3));
    }
    lines.push(`▸ 절대 규칙: 본문 섹션은 정확히 ${secs.length}개(${L(secs)})만 생성 — 임의 추가·생략·병합 금지`);
    return lines.join('\n');
}
