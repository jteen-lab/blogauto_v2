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

        // AI 이미지 모델
        aiImageModel: 'dall-e-3',

        // 서비스별 사용 가능한 모델 목록
        AI_IMAGE_MODELS: {
            openai: [
                { value: 'dall-e-3', label: 'DALL-E 3 (추천)' },
                { value: 'dall-e-2', label: 'DALL-E 2' },
                { value: 'gpt-image-1', label: 'GPT Image 1' },
            ],
            nanobanana: [
                { value: 'gemini-3-pro-image-preview', label: 'Gemini 3 Pro (추천)' },
                { value: 'gemini-2.5-flash-image', label: 'Gemini 2.5 Flash Image' },
            ],
        },

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

        /**
         * 초기화 - Alpine.js가 자동 호출
         */
        /**
         * 현재 AI 서비스에 맞는 모델 목록 반환
         */
        getAvailableModels() {
            return this.AI_IMAGE_MODELS[this.aiImageService] || [];
        },

        init() {
            // AI 서비스 변경 시 모델을 해당 서비스의 기본값으로 리셋
            this.$watch('aiImageService', (newService) => {
                const models = this.AI_IMAGE_MODELS[newService];
                if (models && models.length > 0) {
                    this.aiImageModel = models[0].value;
                }
            });

            // 전역 이벤트 리스너 등록 - blogSettingsApp에서 setBlog 호출 시
            window.addEventListener('blog-settings-loaded', (e) => {
                if (e.detail && e.detail.blogId) {
                    this.blogId = e.detail.blogId;
                    console.log('[imageSettingsApp] 이벤트로 blogId 수신:', this.blogId);
                    this.loadSettings();
                }
            });

            // $nextTick으로 DOM 준비 후 부모에서 blogId 가져오기 시도
            this.$nextTick(() => {
                this.tryLoadFromParent();
            });
        },

        /**
         * 부모 컴포넌트에서 blogId 가져오기 시도
         */
        tryLoadFromParent() {
            const settingsEl = document.getElementById('blogSettings');
            if (settingsEl && settingsEl._x_dataStack && settingsEl._x_dataStack[0]) {
                const parentData = settingsEl._x_dataStack[0];
                if (parentData.selectedBlog && parentData.selectedBlog.id) {
                    this.blogId = parentData.selectedBlog.id;
                    console.log('[imageSettingsApp] 부모에서 blogId 가져옴:', this.blogId);
                    this.loadSettings();
                    return true;
                }
            }
            // URL에서도 시도
            const urlId = this.getBlogIdFromUrl();
            if (urlId) {
                this.blogId = urlId;
                console.log('[imageSettingsApp] URL에서 blogId 가져옴:', this.blogId);
                this.loadSettings();
                return true;
            }
            this.loading = false;
            return false;
        },

        /**
         * URL에서 블로그 ID 추출
         */
        getBlogIdFromUrl() {
            const match = window.location.pathname.match(/\/blogs\/(\d+)/);
            return match ? match[1] : null;
        },

        /**
         * 블로그 ID 가져오기 (캐시된 값 또는 URL에서)
         */
        getBlogId() {
            if (this.blogId) return this.blogId;
            return this.getBlogIdFromUrl();
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
            if (data.ai_image_model) this.aiImageModel = data.ai_image_model;

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
            // $refs가 아직 바인딩되지 않았을 수 있으므로 안전하게 접근
            if (!this.$refs) return;
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

        // 캔버스 미리보기 헬퍼 (blog_image_preview.js에서 제공)
        drawPaddingGuide: imagePreviewMixin.drawPaddingGuide,
        wrapText: imagePreviewMixin.wrapText,
        drawText: imagePreviewMixin.drawText,

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
                    ai_image_model: this.aiImageModel,
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
