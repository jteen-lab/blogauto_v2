/**
 * 모듈 테스터 — 미리보기·복사·글 반영.
 *
 * 조립(고지문·표지·버튼)은 서버 한 곳에서 하고, 화면은 그 결과를 보여 준다.
 * **복사는 붙여넣을 곳을 생각해서** 로컬 이미지를 블로그 저장소에 올려
 * 절대주소로 바꾼 본문을 넘긴다(저장분은 그대로 둔다).
 *
 * 순서도: docs/flowcharts/workbench_copy_html.md
 */
function previewPart() {
    return {
        // ── 미리보기·글 반영 ─────────────────────────────────
        async showPreview(item, step = null) {
            this.previewItem = item; this.previewStep = step;
            this.preview = {
                title: item.text, html: item.html || '',
                imageUrl: item.image_url || null, raw: item.html || '',
            };
            this.postMessage = ''; this.editMode = false;
            this.openSheet('preview');
            await this.assemble();
        },
        /** 고지문·표지·버튼을 서버에서 붙인다.
         *  미리보기와 저장이 갈리지 않도록 조립 지점은 여기 하나다. */
        async assemble() {
            if (!this.preview.raw) return;
            if (this.editMode) {
                this.postMessage = '본문을 고치는 중이라 다시 조립하지 않았습니다.';
                return;
            }
            try {
                const got = await this._json('/api/v1/workbench/assemble', {
                    method: 'POST',
                    body: JSON.stringify({
                        html: this.preview.raw, title: this.preview.title,
                        image_url: this.preview.imageUrl,
                        link_id: this.linkAuto ? 'auto' : (this.pickedLink?.id ?? null),
                        blog_id: this.blogs[0]?.id ?? null,
                    }),
                });
                this.preview.html = got.html || this.preview.raw;
                if (got.link_auto) {
                    // 자동은 글마다 다르다 — 무엇이 왜 붙었는지 받아 적는다
                    this.autoPicked = { name: got.link_name || '',
                                        rule: got.link_rule || '', done: true };
                }
            } catch (e) { this.postMessage = '실패: 조립 오류 ' + e.message; }
        },
        previewDoc() {
            const base = 'body{margin:16px;font-family:system-ui,sans-serif;'
                + 'font-size:15px;line-height:1.7;color:#222}'
                + 'img{max-width:100%;height:auto}'
                + 'table{border-collapse:collapse;width:100%}'
                + 'th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px}';
            return '<style>' + base + (this.previewCss || '') + '</style>'
                + '<div class="wb-preview">' + (this.preview.html || '') + '</div>';
        },
        async applyPost(mode) {
            const blog = this.blogs[0];
            if (!blog) { this.postMessage = '실패: 블로그를 먼저 담으세요'; return; }
            if (mode === 'now'
                && !confirm('즉시 발행합니다. 실제 블로그에 올라가며 되돌릴 수 없습니다.\n진행할까요?')) {
                return;
            }
            try {
                const got = await this._json('/api/v1/workbench/apply/post', {
                    method: 'POST',
                    body: JSON.stringify({
                        blog_id: blog.id, title: this.preview.title,
                        html: this.preview.html, image_url: this.preview.imageUrl,
                        link_id: this.linkAuto ? 'auto' : (this.pickedLink?.id ?? null), mode,
                    }),
                });
                if (got.success === false) {
                    this.postMessage = got.message || '실패';
                    return;
                }
                this._dropPreviewed(got.message || '반영됨');
            } catch (e) { this.postMessage = '실패: ' + e.message; }
        },
        /** 반영이 끝난 글은 화면에서 치운다.
         *  남겨 두면 같은 글을 두 번 반영하게 된다. */
        _dropPreviewed(message) {
            const step = this.previewStep, item = this.previewItem;
            if (step && item) {
                const at = (step.items || []).indexOf(item);
                if (at >= 0) step.items.splice(at, 1);
                this._refreshStepOutcome(step, message);
            }
            this.previewItem = null; this.previewStep = null;
            this.preview = { title: '', html: '', imageUrl: null, raw: '' };
            this.postMessage = '';
            // 반영이 끝났으면 고른 질문을 놓아 준다. 체크가 남아 있으면
            // 다음 글을 고를 때 앞의 것이 섞인다.
            this.releaseSources();
            this.closeSheet();
        },
        /** 반영이 끝난 글의 자취를 지운다.
         *
         *  실행 요약에 「제목 … 본문 3724자」가 남아 있으면 이미 내보낸 글이
         *  아직 여기 있는 것처럼 보인다. 남은 글들의 요약만 다시 세운다.
         *  남은 글이 없으면 단계를 비운다.
         */
        _refreshStepOutcome(step, message) {
            const left = (step.items || []).length;
            if (!left) {
                step.outcome = null;
                step.clipped = 0;
                step.filter = 'all';
                step.applyMessage = message;
                return;
            }
            const lines = (step.items || [])
                .map(it => (it.blogName ? it.blogName + ': ' : '') + (it.message || ''))
                .filter(t => t.trim());
            if (step.outcome) {
                step.outcome = {
                    success: true,
                    message: lines.join(' / ') || ('남은 글 ' + left + '건'),
                };
            }
            step.applyMessage = message + ' · 남은 글 ' + left + '건';
        },
        /** 글자를 클립보드에 넣는다. 세 갈래로 시도한다.
         *
         *  `navigator.clipboard` 는 **보안 컨텍스트(https 또는 localhost)에서만**
         *  동작한다. 우리 서버는 http 로 접속하니 이 API 가 아예 없거나 막혀
         *  "복사 권한이 없습니다"만 떴다(2026-09-27 확인).
         *
         *  Returns: 'clipboard' | 'exec' | '' (실패)
         */
        async _copyText(text) {
            const value = String(text || '');
            if (!value) return '';
            try {
                if (navigator.clipboard && window.isSecureContext !== false) {
                    await navigator.clipboard.writeText(value);
                    return 'clipboard';
                }
            } catch (e) { /* 아래 옛 방식으로 내려간다 */ }
            try {
                // http 에서도 되는 옛 방식. 화면 밖에 두고 고른 뒤 복사한다.
                const box = document.createElement('textarea');
                box.value = value;
                box.setAttribute('readonly', '');
                box.style.position = 'fixed';
                box.style.top = '-1000px';
                box.style.opacity = '0';
                document.body.appendChild(box);
                box.select();
                box.setSelectionRange(0, value.length);
                const ok = document.execCommand && document.execCommand('copy');
                document.body.removeChild(box);
                if (ok) return 'exec';
            } catch (e) { /* 마지막 갈래로 */ }
            return '';
        },

        async copyHtml() {
            const html = this.preview.html || '';
            if (!html) { this.postMessage = '복사할 본문이 없습니다.'; return; }

            // 붙여넣을 곳에서도 이미지가 보이게, 로컬 이미지를 블로그 저장소에
            // 올려 절대주소로 바꾼다. 저장된 본문은 그대로 둔다 — 발행 경로가
            // 로컬 경로로 표지 중복을 가려내기 때문이다.
            let text = html, note = '';
            if (html.includes('/static/generated/images/')) {
                this.postMessage = '이미지를 올리는 중…';
                try {
                    const got = await this._json('/api/v1/workbench/copy-html', {
                        method: 'POST',
                        body: JSON.stringify({
                            html, title: this.preview.title || '',
                            blog_id: this.blogs[0]?.id ?? null,
                        }),
                    });
                    if (!got.success) {
                        this.postMessage = '복사하지 않았습니다 — ' + (got.error || '이미지 처리 실패');
                        return;
                    }
                    text = got.html || html;
                    note = got.uploaded
                        ? ` (이미지 ${got.uploaded}개를 올려 주소를 바꿨습니다)` : '';
                } catch (e) {
                    this.postMessage = '복사하지 않았습니다 — 이미지 처리 실패: ' + e.message;
                    return;
                }
            }

            const how = await this._copyText(text);
            if (how) {
                this.postMessage = 'HTML을 복사했습니다.' + note;
                return;
            }
            // 둘 다 막혔으면 직접 고를 수 있게 열어 준다. 주소를 바꾼
            // 본문을 칸에 넣어 둬야 그것을 복사한다.
            this.preview.html = text;
            this.editMode = true;
            this.$nextTick(() => {
                const el = this.$refs.htmlBox;
                if (el) { el.focus(); el.select(); }
            });
            this.postMessage = '브라우저가 자동 복사를 막았습니다 — '
                + 'HTML 칸을 모두 골라 뒀으니 Ctrl+C 로 복사하세요.' + note;
        },
    };
}
