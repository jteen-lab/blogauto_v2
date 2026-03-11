/**
 * BlogAuto V2: 이미지 미리보기 캔버스 헬퍼
 * File: app/static/js/blog_image_preview.js
 *
 * imageSettingsApp에서 사용하는 캔버스 렌더링 유틸리티.
 * drawPaddingGuide, wrapText, drawText를 mixin으로 제공한다.
 */

const imagePreviewMixin = {
    /**
     * 패딩 경계 점선 가이드 그리기
     */
    drawPaddingGuide(ctx, width, height, padding) {
        ctx.save();

        // 점선 스타일 설정
        ctx.setLineDash([8, 4]);
        ctx.strokeStyle = 'rgba(99, 102, 241, 0.7)'; // 인디고 색상
        ctx.lineWidth = 2;

        // 텍스트 영역 사각형 (패딩 내부)
        const x = padding.left;
        const y = padding.top;
        const w = width - padding.left - padding.right;
        const h = height - padding.top - padding.bottom;

        ctx.strokeRect(x, y, w, h);
        // 코너 마커
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(99, 102, 241, 0.9)';
        const m = 8, hm = m / 2;
        [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].forEach(([cx, cy]) => {
            ctx.fillRect(cx - hm, cy - hm, m, m);
        });
        ctx.restore();
    },

    /**
     * 텍스트를 단어(공백) 단위로 줄바꿈
     * - 단어 중간에서 잘리지 않음
     * - 명시적 줄바꿈(\n) 지원
     * - 단어가 maxWidth보다 길면 문자 단위로 분할 (폴백)
     */
    wrapText(ctx, text, maxWidth) {
        const lines = [];
        text.split('\n').forEach(paragraph => {
            if (!paragraph) { lines.push(''); return; }

            // 단어 단위로 분리 (공백 포함하여 분리)
            const words = paragraph.split(/(\s+)/);
            let currentLine = '';

            for (const word of words) {
                // 공백만 있는 경우 현재 줄에 추가
                if (!word.trim()) {
                    currentLine += word;
                    continue;
                }

                const testLine = currentLine + word;
                const testWidth = ctx.measureText(testLine).width;

                if (testWidth > maxWidth && currentLine.trim()) {
                    // 현재 줄 저장하고 새 줄 시작
                    lines.push(currentLine.trim());
                    currentLine = word;
                } else if (testWidth > maxWidth && !currentLine.trim()) {
                    // 단어 자체가 maxWidth보다 긴 경우 - 문자 단위 폴백
                    let tempLine = '';
                    for (const char of word) {
                        const charTest = tempLine + char;
                        if (ctx.measureText(charTest).width > maxWidth && tempLine) {
                            lines.push(tempLine);
                            tempLine = char;
                        } else {
                            tempLine = charTest;
                        }
                    }
                    currentLine = tempLine;
                } else {
                    currentLine = testLine;
                }
            }

            if (currentLine.trim()) lines.push(currentLine.trim());
        });
        return lines;
    },

    /**
     * 텍스트 한 줄 그리기 (그림자, 외곽선 포함)
     */
    drawText(ctx, text, x, y, config) {
        ctx.save();

        // 그림자
        if (config.shadow_enabled) {
            ctx.shadowColor = config.shadow_color;
            ctx.shadowBlur = config.shadow_blur;
            ctx.shadowOffsetX = config.shadow_offset_x;
            ctx.shadowOffsetY = config.shadow_offset_y;
        }

        // 외곽선
        if (config.stroke_enabled && config.stroke_width > 0) {
            ctx.strokeStyle = config.stroke_color;
            ctx.lineWidth = config.stroke_width * 2;
            ctx.lineJoin = 'round';
            ctx.miterLimit = 2;
            ctx.strokeText(text, x, y);
        }

        if (!config.shadow_enabled) ctx.shadowColor = 'transparent';

        // 텍스트
        ctx.fillStyle = config.text_color;
        ctx.fillText(text, x, y);
        ctx.restore();
    }
};
