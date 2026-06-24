/**
 * 스타일 탭 프리셋 정의
 * File: app/static/js/blogs/style-tab-presets.js
 * Last-Updated: 2026-01-24
 */

/**
 * 스타일 프리셋 정의
 */
const STYLE_PRESETS = {
    default: {
        h1: { 'font-size': '28', 'font-weight': 'bold', 'margin-bottom': '16', 'color': '#1a1a1a' },
        h2: { 'font-size': '24', 'font-weight': 'bold', 'margin-bottom': '14', 'color': '#2a2a2a' },
        h3: { 'font-size': '20', 'font-weight': '600', 'margin-bottom': '12', 'color': '#3a3a3a' },
        h4: { 'font-size': '18', 'font-weight': '600', 'margin-bottom': '10', 'color': '#4a4a4a' },
        h5: { 'font-size': '16', 'font-weight': '600', 'margin-bottom': '8', 'color': '#5a5a5a' },
        p: { 'font-size': '16', 'line-height': '1.6', 'margin-bottom': '12', 'color': '#333333' },
        a: { 'color': '#2563eb' },
        'a.button': {
            'color': '#ffffff', 'background-color': '#2563eb', 'padding-top': '10',
            'padding-bottom': '10', 'padding-left': '20', 'padding-right': '20',
            'border-radius': '6'
        },
        li: { 'font-size': '16', 'margin-bottom': '4' },
        blockquote: {
            'padding-left': '16', 'border-left-style': 'solid', 'border-left-width': '4',
            'border-left-color': '#e5e7eb', 'color': '#6b7280', 'font-style': 'italic'
        }
    },
    minimal: {
        h1: { 'font-size': '24', 'font-weight': '500', 'margin-bottom': '12', 'color': '#111827' },
        h2: { 'font-size': '20', 'font-weight': '500', 'margin-bottom': '10', 'color': '#111827' },
        h3: { 'font-size': '18', 'font-weight': '500', 'margin-bottom': '8', 'color': '#111827' },
        p: { 'font-size': '15', 'line-height': '1.7', 'margin-bottom': '10', 'color': '#374151' },
        a: { 'color': '#4b5563' },
        'a.button': { 'color': '#111827', 'border-bottom-style': 'solid', 'border-bottom-width': '2', 'border-bottom-color': '#111827' },
        blockquote: { 'padding-left': '12', 'color': '#9ca3af' }
    },
    modern: {
        h1: { 'font-size': '32', 'font-weight': 'bold', 'margin-bottom': '20', 'color': '#0f172a' },
        h2: { 'font-size': '26', 'font-weight': 'bold', 'margin-bottom': '16', 'color': '#1e293b' },
        h3: { 'font-size': '22', 'font-weight': '600', 'margin-bottom': '14', 'color': '#334155' },
        h4: { 'font-size': '18', 'font-weight': '600', 'margin-bottom': '12' },
        h5: { 'font-size': '16', 'font-weight': '600', 'margin-bottom': '10' },
        p: { 'font-size': '16', 'line-height': '1.8', 'margin-bottom': '16', 'color': '#475569' },
        a: { 'color': '#3b82f6' },
        'a.button': {
            'color': '#ffffff', 'background-color': '#3b82f6', 'padding-top': '12',
            'padding-bottom': '12', 'padding-left': '24', 'padding-right': '24',
            'border-radius': '8', 'font-weight': '600'
        },
        li: { 'font-size': '16', 'margin-bottom': '6' },
        blockquote: {
            'padding-top': '12', 'padding-bottom': '12', 'padding-left': '20',
            'background-color': '#f8fafc', 'border-left-style': 'solid',
            'border-left-width': '4', 'border-left-color': '#3b82f6', 'border-radius': '4'
        },
        table: { 'border-radius': '8' },
        th: { 'background-color': '#f1f5f9', 'font-weight': '600' }
    }
};

/**
 * px 단위가 필요한 CSS 속성 목록
 */
const PIXEL_PROPERTIES = [
    'font-size', 'border-width', 'border-radius',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width'
];

/**
 * 선택자 목록 및 표시명
 */
const STYLE_SELECTORS = [
    'h1', 'h2', 'h3', 'h4', 'h5',
    'p', 'a', 'a:hover', 'a.button', 'a.button:hover', 'li',
    'ul', 'ol',
    'table', 'th', 'td',
    'blockquote'
];

const SELECTOR_LABELS = {
    'h1': 'h1',
    'h2': 'h2',
    'h3': 'h3',
    'h4': 'h4',
    'h5': 'h5',
    'p': 'p',
    'a': 'a (일반 링크)',
    'a:hover': '링크 (마우스오버)',
    'a.button': 'a (버튼 링크)',
    'a.button:hover': '버튼 (마우스오버)',
    'li': 'li',
    'ul': 'ul',
    'ol': 'ol',
    'table': 'table',
    'th': 'th',
    'td': 'td',
    'blockquote': 'blockquote'
};

/**
 * 테이블 스타일 프리셋 정의 (5종)
 */
const TABLE_PRESETS = {
    simple: {
        label: '심플',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        th: {
            'background-color': '#f3f4f6',
            'color': '#1f2937',
            'font-weight': '600',
            'padding-top': '10',
            'padding-right': '12',
            'padding-bottom': '10',
            'padding-left': '12',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        td: {
            'color': '#374151',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#e5e7eb'
        },
        zebra: null
    },
    modern: {
        label: '모던',
        table: {
            'width': '100%',
            'border-collapse': 'separate',
            'border-radius': '8'
        },
        th: {
            'background-color': '#3b82f6',
            'color': '#ffffff',
            'font-weight': '600',
            'padding-top': '12',
            'padding-right': '16',
            'padding-bottom': '12',
            'padding-left': '16'
        },
        td: {
            'color': '#374151',
            'padding-top': '10',
            'padding-right': '16',
            'padding-bottom': '10',
            'padding-left': '16'
        },
        zebra: null
    },
    classic: {
        label: '클래식',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '2',
            'border-color': '#374151'
        },
        th: {
            'background-color': '#e5e7eb',
            'color': '#111827',
            'font-weight': 'bold',
            'padding-top': '10',
            'padding-right': '14',
            'padding-bottom': '10',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '2',
            'border-color': '#374151'
        },
        td: {
            'color': '#1f2937',
            'padding-top': '8',
            'padding-right': '14',
            'padding-bottom': '8',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#9ca3af'
        },
        zebra: null
    },
    minimal: {
        label: '미니멀',
        table: {
            'width': '100%',
            'border-collapse': 'collapse'
        },
        th: {
            'color': '#6b7280',
            'font-weight': '500',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-bottom-style': 'solid',
            'border-bottom-width': '2',
            'border-bottom-color': '#e5e7eb'
        },
        td: {
            'color': '#374151',
            'padding-top': '8',
            'padding-right': '12',
            'padding-bottom': '8',
            'padding-left': '12',
            'border-bottom-style': 'solid',
            'border-bottom-width': '1',
            'border-bottom-color': '#f3f4f6'
        },
        zebra: null
    },
    dark: {
        label: '다크',
        table: {
            'width': '100%',
            'border-collapse': 'collapse',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        th: {
            'background-color': '#1f2937',
            'color': '#ffffff',
            'font-weight': '600',
            'padding-top': '12',
            'padding-right': '14',
            'padding-bottom': '12',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        td: {
            'color': '#e5e7eb',
            'padding-top': '10',
            'padding-right': '14',
            'padding-bottom': '10',
            'padding-left': '14',
            'border-style': 'solid',
            'border-width': '1',
            'border-color': '#374151'
        },
        zebra: {
            even: '#111827',
            odd: '#1f2937'
        }
    }
};

/**
 * 숨겨진 선택자 (좌측 목록에 표시하지 않지만 CSS 생성에 포함)
 */
const HIDDEN_SELECTORS = ['tr:nth-child(even)', 'tr:nth-child(odd)'];

/**
 * 샘플 HTML 콘텐츠
 */
const SAMPLE_CONTENT = `
    <h1>제목 (H1)</h1>
    <h2>소제목 (H2)</h2>
    <h3>섹션 제목 (H3)</h3>
    <h4>서브 섹션 (H4)</h4>
    <h5>작은 제목 (H5)</h5>
    <p>일반 텍스트 단락입니다. 여러 문장이 포함될 수 있습니다.</p>
    <p>두 번째 단락입니다. <a href="#">일반 링크</a>도 포함되어 있습니다.</p>
    <div class="button-link"><a href="#">버튼 링크</a></div>
    <ul>
        <li>순서 없는 목록 1</li>
        <li>순서 없는 목록 2</li>
    </ul>
    <ol>
        <li>순서 있는 목록 1</li>
        <li>순서 있는 목록 2</li>
    </ol>
    <table><thead><tr><th>항목</th><th>값</th><th>비고</th></tr></thead><tbody><tr><td>데이터 A1</td><td>100</td><td>정상</td></tr><tr><td>데이터 A2</td><td>200</td><td>주의</td></tr><tr><td>데이터 A3</td><td>150</td><td>정상</td></tr><tr><td>데이터 A4</td><td>300</td><td>확인</td></tr></tbody></table>
    <blockquote>인용문 텍스트입니다.</blockquote>
`;
