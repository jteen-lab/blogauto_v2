/**
 * BlogAuto V2: 블로그 이미지 설정 Alpine.js 컴포넌트
 * File: app/static/js/blog_image_settings.js
 */

function imageSettingsApp() {
    return {
        // 상태
        loading: true,
        saving: false,
        saveSuccess: false,
        saveError: '',
        uploadingTemplate: false,
        uploadingFont: false,
        dragOverTemplate: false,
        dragOverFont: false,

        // 블로그 ID (부모 컴포넌트에서 설정)
        blogId: null,

        // 이미지 모드: template, ai, both
        imageMode: 'template',

        // AI 이미지 서비스: openai (DALL-E), nanobanana (Nano Banana)
        aiImageService: 'openai',

        // 오버레이 설정
        overlayConfig: {
            template_image: null,
            font_file: null,
            font_size: 64,
            line_height: 1.25,
            text_align: 'center',
            vertical_align: 'center',
            text_color: '#111111',
            stroke_enabled: false,
            stroke_color: '#000000',
            stroke_width: 0,
            shadow_enabled: false,
            shadow_color: '#000000',
            shadow_blur: 0,
            shadow_offset_x: 0,
            shadow_offset_y: 0,
            padding: { left: 60, right: 60, top: 80, bottom: 80 }
        },

        // 미리보기
        previewText: '미리보기 텍스트\n두 번째 줄',
        templatePreviewUrl: '',
        loadedFont: null,
        templateImage: null,

        // 메시지 표시 헬퍼
        showMessage(message, type = 'info') {
            // 전역 함수가 있으면 사용, 없으면 alert
            if (type === 'success' && typeof showSuccessMessage === 'function') {
                showSuccessMessage(message);
            } else if (type === 'error' && typeof showErrorMessage === 'function') {
                showErrorMessage(message);
            } else if (typeof showInfoMessage === 'function') {
                showInfoMessage(message);
            } else {
                // 폴백: 간단한 토스트 또는 alert
                console.log(`[${type.toUpperCase()}] ${message}`);
                if (type === 'error') {
                    this.saveError = message;
                    setTimeout(() => { this.saveError = ''; }, 3000);
                } else if (type === 'success') {
                    this.saveSuccess = true;
                    setTimeout(() => { this.saveSuccess = false; }, 3000);
                }
            }
        },

        async init() {
            // 부모 컴포넌트(blogSettingsApp)에서 blogId를 가져옴
            const blogId = this.getBlogId();
            if (blogId) {
                this.blogId = blogId;
                await this.loadSettings();
            } else {
                this.loading = false;
            }

            // MutationObserver로 부모 컴포넌트 변경 감지
            this.setupBlogChangeObserver();
        },

        setupBlogChangeObserver() {
            const parentEl = this.$el.closest('#blogSettings');
            if (!parentEl) return;
            const checkParent = () => {
                const parentData = this.getParentData();
                if (parentData?.selectedBlog?.id && parentData.selectedBlog.id !== this.blogId) {
                    this.blogId = parentData.selectedBlog.id;
                    this.loadSettings();
                }
            };
            checkParent();
            this._parentCheckInterval = setInterval(checkParent, 500);
        },

        getParentData() {
            const parentEl = this.$el.closest('#blogSettings');
            return parentEl?._x_dataStack?.[0] || null;
        },

        getBlogId() {
            if (this.blogId) return this.blogId;
            const parentData = this.getParentData();
            if (parentData?.selectedBlog?.id) {
                this.blogId = parentData.selectedBlog.id;
                return this.blogId;
            }

            // URL에서 추출 시도 (폴백)
            const match = window.location.pathname.match(/\/blogs\/(\d+)/);
            return match ? match[1] : null;
        },

        async loadSettings() {
            const blogId = this.getBlogId();
            if (!blogId) { this.loading = false; return; }

            try {
                const response = await fetch(`/api/v1/blogs/${blogId}/settings/image`);
                if (response.ok) {
                    this.applySettings(await response.json());
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 설정 불러오기 실패:', error);
            } finally {
                this.loading = false;
            }
        },

        applySettings(data) {
            if (data.image_mode) this.imageMode = data.image_mode;
            if (data.ai_image_service) this.aiImageService = data.ai_image_service;

            if (data.overlay_config) {
                const config = data.overlay_config;
                this.overlayConfig = {
                    ...this.overlayConfig,
                    ...config,
                    padding: config.padding || this.overlayConfig.padding
                };
            }

            if (this.overlayConfig.template_image) {
                this.templatePreviewUrl = `/api/v1/blogs/${this.getBlogId()}/settings/image/file?file_type=template&t=${Date.now()}`;
                this.loadTemplateImage();
            }

            if (this.overlayConfig.font_file) {
                this.loadCustomFont();
            }
        },

        loadTemplateImage() {
            if (!this.overlayConfig.template_image) return;

            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => { this.templateImage = img; this.updatePreview(); };
            img.onerror = () => console.error('[IMAGE_SETTINGS] 템플릿 이미지 로드 실패');
            img.src = this.templatePreviewUrl;
        },

        async loadCustomFont() {
            if (!this.overlayConfig.font_file) return;

            try {
                const blogId = this.getBlogId();
                const fontUrl = `/api/v1/blogs/${blogId}/settings/image/file?file_type=font&t=${Date.now()}`;
                const font = new FontFace('CustomFont', `url(${fontUrl})`);
                await font.load();
                document.fonts.add(font);
                this.loadedFont = font;
                this.updatePreview();
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 폰트 로드 실패:', error);
            }
        },

        handleTemplateDrop(event) {
            this.dragOverTemplate = false;
            if (event.dataTransfer.files.length > 0) {
                this.uploadTemplateFile(event.dataTransfer.files[0]);
            }
        },

        handleTemplateUpload(event) {
            if (event.target.files.length > 0) {
                this.uploadTemplateFile(event.target.files[0]);
            }
        },

        async uploadTemplateFile(file) {
            const blogId = this.getBlogId();
            if (!blogId) return;

            const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
            if (!validTypes.includes(file.type)) {
                this.showMessage('PNG, JPG, WEBP 파일만 업로드 가능합니다.', 'error');
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                this.showMessage('파일 크기는 5MB 이하여야 합니다.', 'error');
                return;
            }

            this.uploadingTemplate = true;
            try {
                const formData = new FormData();
                formData.append('file', file);

                const response = await fetch(
                    `/api/v1/blogs/${blogId}/settings/image/upload?file_type=template`,
                    { method: 'POST', body: formData }
                );

                if (response.ok) {
                    const data = await response.json();
                    // API 응답의 file_path 사용
                    this.overlayConfig.template_image = data.file_path || data.filename;
                    this.templatePreviewUrl = `/api/v1/blogs/${blogId}/settings/image/file?file_type=template&t=${Date.now()}`;
                    this.loadTemplateImage();
                    this.showMessage('템플릿 이미지가 업로드되었습니다.', 'success');
                } else {
                    const error = await response.json();
                    this.showMessage(error.detail || '업로드 실패', 'error');
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 템플릿 업로드 오류:', error);
                this.showMessage('업로드 중 오류가 발생했습니다.', 'error');
            } finally {
                this.uploadingTemplate = false;
            }
        },

        handleFontDrop(event) {
            this.dragOverFont = false;
            if (event.dataTransfer.files.length > 0) {
                this.uploadFontFile(event.dataTransfer.files[0]);
            }
        },

        handleFontUpload(event) {
            if (event.target.files.length > 0) {
                this.uploadFontFile(event.target.files[0]);
            }
        },

        async uploadFontFile(file) {
            const blogId = this.getBlogId();
            if (!blogId) return;

            const fileName = file.name.toLowerCase();
            if (!fileName.endsWith('.ttf') && !fileName.endsWith('.otf')) {
                this.showMessage('TTF 또는 OTF 파일만 업로드 가능합니다.', 'error');
                return;
            }

            this.uploadingFont = true;
            try {
                const formData = new FormData();
                formData.append('file', file);

                const response = await fetch(
                    `/api/v1/blogs/${blogId}/settings/image/upload?file_type=font`,
                    { method: 'POST', body: formData }
                );

                if (response.ok) {
                    const data = await response.json();
                    // API 응답의 file_path 사용
                    this.overlayConfig.font_file = data.file_path || data.filename;
                    await this.loadCustomFont();
                    this.showMessage('폰트 파일이 업로드되었습니다.', 'success');
                } else {
                    const error = await response.json();
                    this.showMessage(error.detail || '업로드 실패', 'error');
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 폰트 업로드 오류:', error);
                this.showMessage('업로드 중 오류가 발생했습니다.', 'error');
            } finally {
                this.uploadingFont = false;
            }
        },

        async deleteTemplateFile() {
            const blogId = this.getBlogId();
            if (!blogId || !confirm('템플릿 이미지를 삭제하시겠습니까?')) return;

            try {
                const response = await fetch(
                    `/api/v1/blogs/${blogId}/settings/image/file?file_type=template`,
                    { method: 'DELETE' }
                );

                if (response.ok) {
                    this.overlayConfig.template_image = null;
                    this.templatePreviewUrl = '';
                    this.templateImage = null;
                    this.showMessage('템플릿 이미지가 삭제되었습니다.', 'success');
                } else {
                    this.showMessage('삭제 실패', 'error');
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 템플릿 삭제 오류:', error);
                this.showMessage('삭제 중 오류가 발생했습니다.', 'error');
            }
        },

        async deleteFontFile() {
            const blogId = this.getBlogId();
            if (!blogId || !confirm('폰트 파일을 삭제하시겠습니까?')) return;

            try {
                const response = await fetch(
                    `/api/v1/blogs/${blogId}/settings/image/file?file_type=font`,
                    { method: 'DELETE' }
                );

                if (response.ok) {
                    this.overlayConfig.font_file = null;
                    this.loadedFont = null;
                    this.showMessage('폰트 파일이 삭제되었습니다.', 'success');
                    this.updatePreview();
                } else {
                    this.showMessage('삭제 실패', 'error');
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 폰트 삭제 오류:', error);
                this.showMessage('삭제 중 오류가 발생했습니다.', 'error');
            }
        },

        updatePreview() {
            const canvas = this.$refs.previewCanvas;
            if (!canvas || !this.templateImage) return;

            const ctx = canvas.getContext('2d');
            const img = this.templateImage;
            const config = this.overlayConfig;

            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);

            // 텍스트 영역 계산
            const textAreaX = config.padding.left;
            const textAreaY = config.padding.top;
            const textAreaWidth = img.width - config.padding.left - config.padding.right;
            const textAreaHeight = img.height - config.padding.top - config.padding.bottom;

            // 폰트 설정
            const fontFamily = this.loadedFont ? 'CustomFont' : 'sans-serif';
            ctx.font = `${config.font_size}px ${fontFamily}`;
            ctx.textAlign = config.text_align;
            ctx.textBaseline = 'top';

            // 텍스트 줄 나누기 및 높이 계산
            const lines = this.wrapText(ctx, this.previewText, textAreaWidth);
            const lineHeight = config.font_size * config.line_height;
            const totalTextHeight = lines.length * lineHeight;

            // 세로 정렬
            let startY = textAreaY;
            if (config.vertical_align === 'bottom') {
                startY = textAreaY + textAreaHeight - totalTextHeight;
            } else if (config.vertical_align === 'center') {
                startY = textAreaY + (textAreaHeight - totalTextHeight) / 2;
            }

            // 가로 정렬
            let textX = textAreaX;
            if (config.text_align === 'right') {
                textX = textAreaX + textAreaWidth;
            } else if (config.text_align === 'center') {
                textX = textAreaX + textAreaWidth / 2;
            }

            // 각 줄 그리기
            lines.forEach((line, index) => {
                this.drawText(ctx, line, textX, startY + index * lineHeight, config);
            });

            // 패딩 경계 점선 표시
            this.drawPaddingGuide(ctx, img.width, img.height, config.padding);
        },

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
            const m = 8, hm = m/2;
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
        },

        async saveSettings() {
            const blogId = this.getBlogId();
            if (!blogId) return;

            this.saving = true;
            this.saveSuccess = false;
            this.saveError = '';

            try {
                const payload = {
                    image_mode: this.imageMode,
                    ai_image_service: this.aiImageService,
                    overlay_config: this.overlayConfig
                };

                const response = await fetch(`/api/v1/blogs/${blogId}/settings/image`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    this.saveSuccess = true;
                    setTimeout(() => { this.saveSuccess = false; }, 3000);
                } else {
                    const error = await response.json();
                    this.saveError = error.detail || '저장 실패';
                }
            } catch (error) {
                console.error('[IMAGE_SETTINGS] 저장 오류:', error);
                this.saveError = '저장 중 오류가 발생했습니다.';
            } finally {
                this.saving = false;
            }
        }
    };
}
