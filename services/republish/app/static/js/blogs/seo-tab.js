/**
 * SEO 설정 Alpine.js 컴포넌트
 * File: app/static/js/blogs/seo-tab.js
 * Last-Updated: 2026-03-30
 *
 * 기능:
 * - WordPress SEO 플러그인 자동 감지
 * - SEO 메타데이터 자동 생성 설정
 *
 * API 엔드포인트:
 * - GET  /api/v1/blogs/{blogId}/settings/seo
 * - POST /api/v1/blogs/{blogId}/settings/seo
 * - POST /api/v1/blogs/{blogId}/settings/seo/detect
 */
function seoSettingsApp() {
    return {
        // 블로그 정보
        blogId: null,
        blogPlatform: null,

        // 상태
        loading: false,
        loaded: false,
        saving: false,
        detecting: false,
        message: '',
        messageType: 'success',

        // SEO 설정 데이터 (method는 고정값: keyphrase=title, slug=title, description=intro)
        seoConfig: {
            detected_plugin: null,
            detected_at: null,
            auto_seo_enabled: false,
            focus_keyphrase_method: 'title',
            slug_method: 'title',
            meta_description_method: 'intro',
            meta_description_length: 200,
        },

        // 플러그인 표시명 매핑
        pluginNames: {
            'yoast': 'Yoast SEO',
            'rankmath': 'Rank Math',
            'aioseo': 'All in One SEO',
            'seopress': 'SEOPress',
        },

        /**
         * 컴포넌트 초기화
         */
        async init() {
            if (this.blogId) {
                await this.loadConfig(this.blogId);
                return;
            }

            const parent = this.$el.closest('#blogSettings');
            if (parent && parent._x_dataStack && parent._x_dataStack[0] && parent._x_dataStack[0].selectedBlog) {
                this.blogId = parent._x_dataStack[0].selectedBlog.id;
                this.blogPlatform = parent._x_dataStack[0].selectedBlog.platform;
                await this.loadConfig(this.blogId);
            }
        },

        /**
         * SEO 설정 로드
         * @param {number} blogId - 블로그 ID
         */
        async loadConfig(blogId) {
            if (!blogId || this.blogPlatform !== 'wordpress') return;

            this.loading = true;

            try {
                const response = await fetch(`/api/v1/blogs/${blogId}/settings/seo`, {
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.seo_config) {
                        this.seoConfig = {
                            detected_plugin: data.seo_config.detected_plugin || null,
                            detected_at: data.seo_config.detected_at || null,
                            auto_seo_enabled: data.seo_config.auto_seo_enabled || false,
                            focus_keyphrase_method: 'title',
                            slug_method: 'title',
                            meta_description_method: 'intro',
                            meta_description_length: data.seo_config.meta_description_length || 140,
                        };
                    }
                    this.loaded = true;
                }
            } catch (error) {
                console.error('SEO 설정 로드 실패:', error);
                this.showMessage('SEO 설정을 불러오는데 실패했습니다', 'error');
            } finally {
                this.loading = false;
            }
        },

        /**
         * SEO 플러그인 감지 실행
         */
        async detectPlugin() {
            if (!this.blogId) return;

            this.detecting = true;

            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/seo/detect`, {
                    method: 'POST',
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.detected_plugin) {
                        this.seoConfig.detected_plugin = data.detected_plugin;
                        this.seoConfig.detected_at = data.detected_at;
                        this.showMessage(
                            `${this.pluginNames[data.detected_plugin] || data.detected_plugin} 감지 완료`,
                            'success'
                        );
                    } else {
                        this.seoConfig.detected_plugin = null;
                        this.seoConfig.detected_at = null;
                        this.showMessage('SEO 플러그인을 찾을 수 없습니다', 'error');
                    }
                } else {
                    const data = await response.json();
                    throw new Error(data.detail || data.message || '감지 실패');
                }
            } catch (error) {
                console.error('SEO 플러그인 감지 실패:', error);
                this.showMessage(error.message || '플러그인 감지 중 오류가 발생했습니다', 'error');
            } finally {
                this.detecting = false;
            }
        },

        /**
         * SEO 설정 저장
         */
        async saveConfig() {
            // blogId 재확인
            if (!this.blogId) {
                const parent = this.$el.closest('#blogSettings');
                if (parent && parent._x_dataStack && parent._x_dataStack[0] && parent._x_dataStack[0].selectedBlog) {
                    this.blogId = parent._x_dataStack[0].selectedBlog.id;
                }
            }

            if (!this.blogId) {
                this.showMessage('블로그 정보를 찾을 수 없습니다', 'error');
                return;
            }

            this.saving = true;

            try {
                const response = await fetch(`/api/v1/blogs/${this.blogId}/settings/seo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({
                        seo_config: this.seoConfig
                    })
                });

                if (response.ok) {
                    this.showMessage('SEO 설정이 저장되었습니다', 'success');
                } else {
                    const data = await response.json();
                    throw new Error(data.detail || data.message || '저장 실패');
                }
            } catch (error) {
                console.error('SEO 설정 저장 실패:', error);
                this.showMessage(error.message || '저장 중 오류가 발생했습니다', 'error');
            } finally {
                this.saving = false;
            }
        },

        /**
         * 날짜 포맷팅
         * @param {string} dateStr - ISO 날짜 문자열
         * @returns {string} 한국어 날짜 형식
         */
        formatDate(dateStr) {
            if (!dateStr) return '';
            try {
                const date = new Date(dateStr);
                return date.toLocaleDateString('ko-KR', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit'
                });
            } catch {
                return dateStr;
            }
        },

        /**
         * 토스트 메시지 표시
         * @param {string} text - 메시지 내용
         * @param {string} type - 메시지 유형 ('success' | 'error')
         */
        showMessage(text, type = 'success') {
            this.message = text;
            this.messageType = type;
            setTimeout(() => {
                this.message = '';
            }, 3000);
        }
    };
}
