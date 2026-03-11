/**
 * 파이프라인 테스트 - 템플릿 이미지 Canvas 렌더링 유틸리티
 * File: app/static/js/modules/prompt-test-image-renderer.js
 *
 * blog_image_settings.js의 렌더링 로직을 재사용 가능한 형태로 추출.
 * 테스트 패널에서 서버 호출 없이 클라이언트 Canvas로 직접 미리보기 생성.
 */

const TemplateImageRenderer = {
    /**
     * 템플릿 이미지 위에 제목 텍스트를 렌더링
     * @param {HTMLCanvasElement} canvas - 렌더링 대상 캔버스
     * @param {HTMLImageElement} templateImage - 배경 템플릿 이미지
     * @param {FontFace|null} loadedFont - 로드된 커스텀 폰트 (없으면 sans-serif)
     * @param {Object} overlayConfig - 오버레이 설정 (blog_image_settings.js와 동일 구조)
     * @param {string} title - 렌더링할 제목 텍스트
     */
    render(canvas, templateImage, loadedFont, overlayConfig, title) {
        if (!canvas || !templateImage) return;

        const ctx = canvas.getContext('2d');
        const img = templateImage;
        const config = overlayConfig;

        // 캔버스 크기 = 원본 이미지 크기
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);

        // 텍스트 영역 계산 (패딩 고려)
        const padding = config.padding || { left: 60, right: 60, top: 80, bottom: 80 };
        const textAreaX = padding.left;
        const textAreaY = padding.top;
        const textAreaWidth = img.width - padding.left - padding.right;
        const textAreaHeight = img.height - padding.top - padding.bottom;

        if (textAreaWidth <= 0 || textAreaHeight <= 0) return;

        // 폰트 설정
        const fontSize = config.font_size || 64;
        const lineHeight = config.line_height || 1.25;
        const fontFamily = loadedFont ? 'CustomFont' : 'sans-serif';
        ctx.font = `${fontSize}px ${fontFamily}`;
        ctx.textAlign = config.text_align || 'center';
        ctx.textBaseline = 'top';

        // 텍스트 줄바꿈 및 높이 계산
        const lines = this._wrapText(ctx, title || '', textAreaWidth);
        const lineHeightPx = fontSize * lineHeight;
        const totalTextHeight = lines.length * lineHeightPx;

        // 세로 정렬
        const verticalAlign = config.vertical_align || 'center';
        let startY = textAreaY;
        if (verticalAlign === 'bottom') {
            startY = textAreaY + textAreaHeight - totalTextHeight;
        } else if (verticalAlign === 'center') {
            startY = textAreaY + (textAreaHeight - totalTextHeight) / 2;
        }

        // 가로 정렬 X 좌표
        const textAlign = config.text_align || 'center';
        let textX = textAreaX;
        if (textAlign === 'right') {
            textX = textAreaX + textAreaWidth;
        } else if (textAlign === 'center') {
            textX = textAreaX + textAreaWidth / 2;
        }

        // 각 줄 그리기 (패딩 가이드 점선은 테스트에서 불필요하므로 제거)
        lines.forEach((line, index) => {
            this._drawText(ctx, line, textX, startY + index * lineHeightPx, config);
        });
    },

    /**
     * 텍스트를 단어(공백) 단위로 줄바꿈
     * - 명시적 줄바꿈(\n) 지원
     * - 단어가 maxWidth보다 길면 문자 단위 분할 (폴백)
     */
    _wrapText(ctx, text, maxWidth) {
        const lines = [];
        text.split('\n').forEach(paragraph => {
            if (!paragraph) { lines.push(''); return; }

            const words = paragraph.split(/(\s+)/);
            let currentLine = '';

            for (const word of words) {
                if (!word.trim()) {
                    currentLine += word;
                    continue;
                }

                const testLine = currentLine + word;
                const testWidth = ctx.measureText(testLine).width;

                if (testWidth > maxWidth && currentLine.trim()) {
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
     * 텍스트 렌더링 (그림자 -> 외곽선 -> 채우기 순서)
     */
    _drawText(ctx, text, x, y, config) {
        ctx.save();

        // 그림자
        if (config.shadow_enabled) {
            ctx.shadowColor = config.shadow_color || '#000000';
            ctx.shadowBlur = config.shadow_blur || 0;
            ctx.shadowOffsetX = config.shadow_offset_x || 0;
            ctx.shadowOffsetY = config.shadow_offset_y || 0;
        }

        // 외곽선
        if (config.stroke_enabled && (config.stroke_width || 0) > 0) {
            ctx.strokeStyle = config.stroke_color || '#000000';
            ctx.lineWidth = (config.stroke_width || 0) * 2;
            ctx.lineJoin = 'round';
            ctx.miterLimit = 2;
            ctx.strokeText(text, x, y);
        }

        // 그림자 제거 후 텍스트 채우기
        if (!config.shadow_enabled) ctx.shadowColor = 'transparent';

        ctx.fillStyle = config.text_color || '#111111';
        ctx.fillText(text, x, y);
        ctx.restore();
    },

    /**
     * 블로그 이미지 설정 로드 및 Canvas 렌더링 전체 플로우
     * @param {HTMLCanvasElement} canvas - 렌더링 대상 캔버스
     * @param {number} blogId - 블로그 ID
     * @param {string} title - 렌더링할 제목 텍스트
     * @returns {Promise<{success: boolean, error?: string}>}
     */
    async renderForBlog(canvas, blogId, title) {
        if (!canvas || !blogId) {
            return { success: false, error: '캔버스 또는 블로그 ID가 없습니다' };
        }

        try {
            // 1) 블로그 이미지 설정 조회
            const settingsResp = await fetch(`/api/v1/blogs/${blogId}/settings/image`);
            if (!settingsResp.ok) {
                return { success: false, error: `이미지 설정 조회 실패 (HTTP ${settingsResp.status})` };
            }
            const settings = await settingsResp.json();
            const overlayConfig = settings.overlay_config || {};

            if (!overlayConfig.template_image) {
                return { success: false, error: '템플릿 이미지가 설정되지 않았습니다' };
            }

            // 2) 템플릿 이미지 로드
            const templateImage = await this._loadImage(
                `/api/v1/blogs/${blogId}/settings/image/file?file_type=template&t=${Date.now()}`
            );

            // 3) 커스텀 폰트 로드 (있으면)
            let loadedFont = null;
            if (overlayConfig.font_file) {
                loadedFont = await this._loadFont(blogId);
            }

            // 4) Canvas 렌더링
            this.render(canvas, templateImage, loadedFont, overlayConfig, title);

            return { success: true };
        } catch (e) {
            console.error('[TemplateImageRenderer] 렌더링 실패:', e);
            return { success: false, error: e.message || '렌더링 중 오류 발생' };
        }
    },

    /**
     * 이미지 로드 (Promise 래핑)
     */
    _loadImage(url) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('템플릿 이미지 로드 실패'));
            img.src = url;
        });
    },

    /**
     * 커스텀 폰트 로드
     */
    async _loadFont(blogId) {
        try {
            const fontUrl = `/api/v1/blogs/${blogId}/settings/image/file?file_type=font&t=${Date.now()}`;
            const font = new FontFace('CustomFont', `url(${fontUrl})`);
            await font.load();
            document.fonts.add(font);
            return font;
        } catch (e) {
            console.warn('[TemplateImageRenderer] 폰트 로드 실패, sans-serif 사용:', e);
            return null;
        }
    }
};

// 전역 노출
window.TemplateImageRenderer = TemplateImageRenderer;
